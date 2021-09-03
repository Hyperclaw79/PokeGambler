"""
PokeGambler - A Pokemon themed gambling bot for Discord.
Copyright (C) 2021 Harshith Thota

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
----------------------------------------------------------------------------

This module is a compilation of all in-game Shop related classes.
"""

# pylint: disable=too-few-public-methods, unused-argument
# pylint: disable=invalid-overridden-method, arguments-differ
# pylint: disable=too-many-instance-attributes

from __future__ import annotations
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from queue import Queue
from typing import (
    Dict, List, Optional,
    TYPE_CHECKING, Type, Union
)

from discord.errors import Forbidden, HTTPException

from ..base.items import Item, DB_CLIENT
from ..base.models import (
    Boosts, Inventory,
    Loots, Profiles
)
from ..helpers.utils import get_embed

if TYPE_CHECKING:
    from discord import Member, Message


class Listing(Queue):
    """A dynamically flowing Queue with the provision
    for pinning items from removal.

    :param items: An optional list of items to be added to the queue.
    :type items: List[ShopItem]
    :param maxsize: The maximum size of the queue., default is 5.
    :type maxsize: Optional[int]
    """
    def __init__(
        self, items: Optional[List[ShopItem]] = None,
        maxsize: Optional[int] = 5
    ):
        if not items:
            items = []
        super().__init__(
            maxsize=max(maxsize, len(items))
        )
        self.register(items)

    def __iter__(self) -> ShopItem:
        """
        Iterator with a LIFO order and lower precedence
        for pinned items.
        """
        def get_rank(item):
            price = item.price
            return (
                getattr(
                    item, "created_on",
                    self.queue.index(item)
                ),
                price
            )

        queue = sorted(
            self.queue,
            key=lambda item: (
                [True, False].index(
                    getattr(item, "pinned", False)
                ),
                get_rank(item)
            ),
            reverse=True
        )
        yield from queue

    def __len__(self) -> int:
        return len(self.queue)

    def __repr__(self) -> str:
        return f"Listing({list(self)})"

    @property
    def name_id_map(self) -> Dict[str, str]:
        """Returns a mapping between item names and their ids.

        :return: A dictionary of item names and their ids.
        :rtype: Dict[str, str]
        """
        return {
            item.name: item.itemid
            for item in self
        }

    def fetch(self) -> ShopItem:
        """Pops out an item in FIFO order.

        :return: The popped item.
        :rtype: :class:`ShopItem`
        """
        return super().get_nowait()

    def register(
        self, items: Union[ShopItem, List[ShopItem]]
    ):
        """Adds an item/list of items to the queue.

        :param items: An item or list of items to be added to the queue.
        :type items: Union[:class:`ShopItem`, List[:class:`ShopItem`]]
        """
        if not items:
            return
        if not isinstance(items, list):
            items = [items]
        for item in items:
            if not self.full():
                super().put_nowait(item)
                continue
            removable = None
            for existing_item in self.queue:
                if not getattr(existing_item, "pinned", False):
                    removable = existing_item
                    break
            if not removable:
                return
            self.queue.remove(removable)
            super().put_nowait(item)


@dataclass
class ShopCategory:
    """The different categories of PokeGambler Shop.

    :param name: The name of the category.
    :type name: str
    :param description: The description for the category.
    :type description: str
    :param emoji: The emoji for the category.
    :type emoji: str
    :param items: A list of items in the category.
    :type items: :class:`Listing`
    """
    name: str
    description: str
    emoji: str
    items: Listing

    def __str__(self) -> str:
        return f"『{self.emoji}』 {self.name}"

    def copy(self) -> ShopCategory:
        """Returns a copy of itself (to prevent mutation).

        :return: A copy of itself.
        :rtype: :class:`ShopCategory`
        """
        return self.__class__(
            name=self.name,
            description=self.description,
            emoji=self.emoji,
            items=Listing(list(self.items))
        )


@dataclass
class ShopItem:
    """Base class for any item visible in the PokeGambler Shop.

    :param itemid: The id of the item.
    :type itemid: str
    :param name: The name of the item.
    :type name: str
    :param description: The description for the item.
    :type description: str
    :param price: The price of the item.
    :type price: int
    :param emoji: The emoji for the item.
    :type emoji: str
    :param pinned: Whether the item is pinned in the Shop.
    :type pinned: bool
    """
    itemid: str
    name: str
    description: str
    price: int
    emoji: str = ""
    pinned: bool = False
    # Safely ignore these kwargs while casting from Item
    category: field(default_factory=str) = "Tradable"
    asset_url: field(default_factory=str) = ""
    buyable: field(default_factory=bool) = True
    sellable: field(default_factory=bool) = True
    premium: field(default_factory=bool) = False
    max_stack: field(default_factory=int) = 0
    color: field(default_factory=int) = 0

    def __str__(self) -> str:
        if not self.emoji:
            return f"{self.name} "
        return f"{self.name} 『{self.emoji}』"

    @abstractmethod
    def buy(self, **kwargs) -> str:
        """
        Every ShopItem should have a buy action.
        """

    def debit_player(
        self, user: Member,
        quantity: Optional[int] = 1,
        premium: bool = False
    ):
        """Debits from the player, the price of the item.

        :param user: The user to debit from.
        :type user: :class:`discord.Member`
        :param quantity: The quantity of items to debit., default is 1.
        :type quantity: Optional[int]
        :param premium: Whether the item is premium.
        :type premium: bool
        """
        amount = self.price * quantity
        bonds = False
        if premium:
            amount //= 10
            bonds = True
        Profiles(user).debit(
            amount=amount, bonds=bonds
        )


class BoostItem(ShopItem):
    """
    This class represents a purchasable temporary boost.
    """
    async def buy(
        self,  message: Message,
        quantity: int = 1, **kwargs
    ) -> str:
        """Applies the relevant temporary boost to the user.

        :param message: The message which triggered the boost purchase.
        :type message: :class:`discord.Message`
        :param quantity: The number of stacks of boost to buy.
        :type quantity: int
        :return: A success/error message.
        :rtype: str
        """
        user = message.author
        tier = Loots(user).tier
        boost_dict = self._get_tempboosts(user)
        if any([
            boost_dict["stack"] == 5,
            self._check_lootlust(boost_dict, user, quantity)
        ]):
            return (
                "You've maxed out to 5 stacks for this boost."
                if quantity == 1
                else "You can't puchase that many "
                "as it exceeds max stack of 5."
            )
        self.__boost_handler(boost_dict, user, quantity)
        Profiles(user).debit(
            amount=((self.price * (10 ** (tier - 1))) * quantity)
        )
        return "success"

    @classmethod
    def get_boosts(
        cls: Type[BoostItem], user_id: str
    ) -> Dict:
        """Returns a list of all the temporary boosts for the user.

        :param user_id: The id of the user.
        :type user_id: str
        :return: A list of all the temporary boosts for the user.
        :rtype: Dict
        """
        return {
            boost.itemid: DB_CLIENT["tempboosts"].find_one({
                "user_id": user_id,
                "boost_id": boost.itemid
            }) or {
                "stack": 0,
                "name": boost.name,
                "description": boost.description,
                "added_on": datetime.now()
            }
            for boost in Shop.categories["Boosts"].items
        }

    @classmethod
    def default_boosts(cls: Type[BoostItem]) -> Dict:
        """Returns the default temporary boosts dictionary.

        :return: A dictionary of default temporary boosts.
        :rtype: Dict
        """
        return {
            item.itemid: {
                "stack": 0,
                "name": item.name,
                "description": item.description,
                "added_on": datetime.now()
            }
            for item in Shop.categories["Boosts"].items
        }

    def __boost_handler(
        self, boost_dict: Dict,
        user: Member, quantity: int
    ):
        boost_dict["stack"] += quantity
        DB_CLIENT["tempboosts"].create_index(
            "added_on",
            expireAfterSeconds=30 * 60
        )
        DB_CLIENT["tempboosts"].update_one(
            {"user_id": str(user.id), "boost_id": self.itemid},
            {"$set": boost_dict},
            upsert=True
        )

    @staticmethod
    def _check_lootlust(
        boost_dict: Dict,
        user: Member, quantity: int
    ) -> bool:
        if boost_dict["boost_id"] not in (
            "boost_lt_cd", "boost_pr_lt_cd"
        ):
            return False
        return sum([
            Boosts(user).get("loot_lust"),
            quantity,
            boost_dict["stack"]
        ]) > 5

    def _get_tempboosts(self, user: Member) -> Dict:
        boost_dict = DB_CLIENT["tempboosts"].find_one({
            "user_id": str(user.id),
            "boost_id": self.itemid
        })
        if not boost_dict:
            boost_dict = {
                "user_id": str(user.id),
                "boost_id": self.itemid,
                "added_on": datetime.utcnow(),
                "name": self.name,
                "description": self.description,
                "stack": 0,
            }
        return boost_dict


class PremiumBoostItem(BoostItem):
    """
    Permanent Boosts purchasable from Premium Shop
    """
    def buy(
        self, message: Message,
        quantity: Optional[int] = 1,
        **kwargs
    ) -> str:
        """Applies the relevant permanent boost to the user.

        :param message: The message which triggered the boost purchase.
        :type message: :class:`discord.Message`
        :param quantity: The number of stacks of boost to buy.
        :type quantity: int
        :return: A success/error message.
        :rtype: str
        """
        user = message.author
        if self._check_lootlust(
            self._get_tempboosts(user),
            user, quantity
        ):
            return (
                "You've maxed out to 5 stacks for this boost."
                if quantity == 1
                else "You can't puchase that many "
                "as it exceeds max stack of 5."
            )
        tier = Loots(user).tier
        boost = Boosts(user)
        boost_name = self.name.lower().replace(' ', '_')
        curr = boost.get(boost_name)
        boost.update(**{boost_name: curr + quantity})
        Profiles(user).debit(
            amount=((self.price * (10 ** (tier - 2))) * quantity),
            bonds=True
        )
        return "success"


class TradebleItem(ShopItem):
    """
    This class represents a shop version of \
        :class:`~scripts.base.items.Tradable`.
    """
    def buy(
        self, message: Message,
        quantity: int, **kwargs
    ) -> str:
        """Buys the Item and places in user's inventory.

        :param message: The message that triggered this action.
        :type message: :class:`discord.Message`
        :param quantity: The number of items to buy.
        :type quantity: int
        :return: A success/error message.
        :rtype: str
        """
        inventory = Inventory(message.author)
        for _ in range(quantity):
            inventory.save(self.itemid)
        self.debit_player(
            user=message.author,
            quantity=quantity,
            premium=self.premium
        )
        return "success"


class Title(ShopItem):
    """
    This class represents a purchasable Title.
    """
    async def buy(
        self, message: Message,
        **kwargs
    ) -> str:
        """Automatically adds the titled role to the user.
        Also edits their nickname if possible.

        :param message: The message that triggered this action.
        :type message: :class:`discord.Message`
        :return: A success/error message.
        :rtype: str
        """
        if self.name in (
            role.name.title()
            for role in message.author.roles
        ):
            return str(
                "**You already have this title"
                " bestowed upon you.**"
            )
        roles = [
            role
            for role in message.guild.roles
            if role.name.lower() == self.name.lower()
        ]
        if not roles:
            try:
                roles = [
                    await message.guild.create_role(
                        name=self.name.title(),
                        color=self.color,
                        hoist=True
                    )
                ]
            except Forbidden:
                return str(
                    "**Need [Manage Server] permission to "
                    "create title roles.**"
                )
        role = roles[0]
        change_nick = True
        try:
            await message.author.add_roles(role)
            new_nick = message.author.nick or message.author.name
            for title in Shop.categories["Titles"].items:
                if title.name in new_nick:
                    if title.price < self.price:
                        new_nick = new_nick.replace(f"『{title.name}』", '')
                    else:
                        change_nick = False
            try:
                if change_nick:
                    await message.author.edit(
                        nick=f"『{role.name}』{new_nick}"
                    )
            except HTTPException:
                await message.channel.send(
                    embed=get_embed(
                        f"Unable to edit {message.author.name}'s nickname.",
                        embed_type="warning",
                        title="Unexpected Error"
                    )
                )
            self.debit_player(message.author)
            return "success"
        except Forbidden:
            return str(
                "**You're too OP for me to give you a role.**\n"
                "**Please ask an admin to give you the role.**\n"
            )


class Shop:
    """
    The main class containing all Shop related data and functionality.
    """
    categories: Dict[str, ShopCategory] = {
        "Titles": ShopCategory(
            "Titles",
            """
            Flex your financial status using a special Title.
            Titles will automatically give you a role named as the title.
            """,
            "📜",
            Listing([
                Title(
                    "title_dlr",
                    "Dealers",
                    "Get access to the gamble command and other perks.",
                    20_000,
                    color=16765440
                ),
                Title(
                    "title_cnm",
                    "Commoner No More",
                    "You're wealthier than the casuals.",
                    20_000,
                    color=16757504
                ),
                Title(
                    "title_wealthy",
                    "The Wealthy",
                    "You're climbing the ladder towards richness.",
                    50_000,
                    color=13729044
                ),
                Title(
                    "title_duke",
                    "Duke",
                    "You literally own a kingdom at this point.",
                    150_000,
                    color=16722176
                ),
                Title(
                    "title_insane",
                    "Insane",
                    "Dude what the hell?! That's way more than enough chips"
                    " for a lifetime.",
                    1_000_000,
                    color=13504512
                )
            ])
        ),
        "Boosts": ShopCategory(
            "Boosts",
            """
            Give yourself a competitive edge by improving certain stats.
            Boosts purchased through ingame shop are temporary.
            Buying new ones increases the effect. They can stack up to 5 times.
            Entire stack expires after the time period (30 minutes) ends.
            For permenant boosts, contact an admin to purchase PokeBonds.
            """,
            "🧬",
            Listing([
                BoostItem(
                    "boost_lt",
                    "Lucky Looter",
                    "Increases your loot by 5%.",
                    100, "💰"
                ),
                BoostItem(
                    "boost_lt_cd",
                    "Loot Lust",
                    "Decreases Loot Cooldown by 1 minute.",
                    100, "⌛"
                ),
                BoostItem(
                    "boost_tr",
                    "Fortune Burst",
                    "Increase Treasure Chance while looting by 10%.",
                    500, "💎"
                ),
                BoostItem(
                    "boost_flip",
                    "Flipster",
                    "Increase reward for QuickFlip minigame by 10%.",
                    200, "🎲"
                )
            ])
        ),
        "Tradables": ShopCategory(
            "Tradables",
            """
            These are the items in the PokeGambler world which can be
            bought, sold and traded with players.
            Might even contain player created Items.
            """,
            "📦",
            Listing()
        ),
        "Consumables": ShopCategory(
            "Consumables",
            """
            These items exists solely for your consumption.
            They cannot be sold back to the shop.
            """,
            "🛒",
            Listing()
        ),
        "Gladiators": ShopCategory(
            "Gladiators",
            """
            These champions of the old have been cloned for you.
            You can buy them to make them fight in brutal gladiator fights.
            """,
            "💀",
            Listing()
        )
    }
    alias_map: Dict[str, str] = {
        "Title": "Titles",
        "Titles": "Titles",
        "Boost": "Boosts",
        "Boosts": "Boosts",
        "Trade": "Tradables",
        "Trades": "Tradables",
        "Tradable": "Tradables",
        "Tradables": "Tradables",
        "Consumable": "Consumables",
        "Consumables": "Consumables",
        "Consume": "Consumables",
        "Consumes": "Consumables",
        "Gladiator": "Gladiators",
        "Gladiators": "Gladiators",
        "Glad": "Gladiators",
        "Glads": "Gladiators",
        "Minion": "Gladiators",
        "Minions": "Gladiators",
        "Pet": "Gladiators",
        "Pets": "Gladiators",
    }
    premium = False
    ids_dict: Dict[str, ShopItem] = {}
    for catog in categories.values():
        for item in catog.items:
            ids_dict[item.itemid] = item

    @classmethod
    def add_category(cls: Type[Shop], category: ShopCategory):
        """Adds a new category to the Shop.

        :param category: The new ShopCategory to add.
        :type category: :class:`ShopCategory`
        """
        cls.categories[category.name] = category

    @classmethod
    def from_name(cls: Type[Shop], name: str) -> str:
        """Returns the itemid of the item with given name.

        :param name: The name of the item.
        :type name: str
        :return: The itemid of the item.
        :rtype: str
        """
        for catog in cls.categories.values():
            if catog.items.name_id_map.get(name) is not None:
                return catog.items.name_id_map[name]
        return None

    @classmethod
    def get_item(
        cls: Type[Shop], itemid: str,
        force_new: bool = False
    ) -> ShopItem:
        """Returns the item registered in Shop based on itemID.

        :param itemid: The itemid of the item.
        :type itemid: str
        :param force_new: If True, a new Item is created.
        :type force_new: bool
        :return: The item registered in Shop.
        :rtype: :class:`ShopItem`
        """
        if itemid in cls.ids_dict:
            return cls.ids_dict[itemid]
        if any(
            ch.lower() not in 'abcdef1234567890'
            for ch in itemid
        ):
            return None
        item = Item.from_id(itemid, force_new=force_new)
        # pylint: disable=no-member
        if cls._premium_cond(item.premium):
            return None
        return TradebleItem(**dict(item))

    @classmethod
    def refresh_tradables(cls: Type[Shop]):
        """
        Similar to :func:`update_category`, \
            but exclusive for :class:`~scripts.base.items.Tradable`.
        """
        item_types = ["Tradables", "Consumables", "Gladiators"]
        for item_type in item_types:
            # Check availability of existing items
            for item in cls.categories[item_type].items:
                db_item = Item.from_id(item.itemid)
                # pylint: disable=no-member
                if not db_item or db_item.premium is not cls.premium:
                    cls.categories[item_type].items.queue.remove(
                        item
                    )
                    cls.ids_dict.pop(item.itemid, None)
            items = [
                TradebleItem(
                    item["itemid"], item["name"],
                    item["description"], item["price"],
                    item["emoji"],
                    pinned="permanent" in item["description"].lower(),
                    premium=item["premium"]
                )
                for item in Item.list_items(
                    category=item_type[::-1].replace('s', '', 1)[::-1],
                    limit=5,
                    premium=cls.premium
                )
            ]
            cls.update_category(item_type, items)

    @classmethod
    def update_category(
        cls: Type[Shop], category: str,
        items: List[ShopItem]
    ):
        """Updates an existing category in the Shop.

        :param category: The name of the category.
        :type category: str
        :param items: The items to add to the category.
        :type items: list[:class:`ShopItem`]
        """
        new_items = [
            item
            for item in items
            if item.name not in (
                itm.name
                for itm in cls.categories[category].items
            )
        ]
        cls.categories[category].items.register(new_items)

    @classmethod
    def validate(
        cls: Type[Shop], user: Member,
        item: ShopItem, quantity: int = 1
    ) -> str:
        """Validates if an item is purchasable and affordable by the user.

        :param user: The user to check the item for.
        :type user: :class:`discord.Member`
        :param item: The item to check.
        :type item: :class:`ShopItem`
        :param quantity: The quantity of the item.
        :type quantity: int
        :return: The error message if the item is not purchasable.
        :rtype: str
        """
        if (
            isinstance(item, TradebleItem)
            and not Item.from_id(item.itemid)
        ):
            return "Item does not exist anymore."
        price = item.price
        if item.__class__ in [BoostItem, PremiumBoostItem]:
            price *= 10 ** (Loots(user).tier - 1)
        curr_attr = "balance"
        if item.premium:
            curr_attr = "pokebonds"
            price //= 10
        if getattr(
            Profiles(user),
            curr_attr
         ) < price * quantity:
            return "You have Insufficient Balance."
        return "proceed"

    @staticmethod
    def _premium_cond(premium: bool):
        return premium


class PremiumShop(Shop):
    """
    The subclass of Shop for premium-only items.
    """
    categories: Dict[str, ShopCategory] = {
        **{
            key: catog.copy()
            for key, catog in Shop.categories.items()
        },
        "Titles": ShopCategory(
            "Titles",
            """
            Flex your financial status using a special Title.
            Titles will automatically give you a role named as the title.
            """,
            "📜",
            Listing([
                Title(
                    "title_pr",
                    "The Patron",
                    "Dedicated patron of PokeGambler.",
                    2000,
                    color=14103594
                )
            ])
        ),
        "Boosts": ShopCategory(
            "Boosts",
            """
            Give yourself a competitive edge by improving certain stats.
            Boosts purchased through premium shop are permanent.
            Buying new ones increases the effect.
            """,
            "🧬",
            Listing([
                PremiumBoostItem(
                    "boost_pr_lt",
                    "Lucky Looter",
                    "Permanently increases your loot by 5%.",
                    100, "💰", premium=True
                ),
                PremiumBoostItem(
                    "boost_pr_lt_cd",
                    "Loot Lust",
                    "Permanently decreases Loot Cooldown by 1 minute."
                    "\n(Max Stack of 5)",
                    100, "⌛", premium=True
                ),
                PremiumBoostItem(
                    "boost_pr_tr",
                    "Fortune Burst",
                    "Permanently increases Treasure Chance "
                    "while looting by 10%.",
                    500, "💎", premium=True
                ),
                PremiumBoostItem(
                    "boost_pr_flip",
                    "Flipster",
                    "Permanently increases reward for QuickFlip "
                    "minigame by 10%.",
                    200, "🎲", premium=True
                )
            ])
        )
    }
    premium = True
    ids_dict: Dict[str, ShopItem] = {}
    for catog in categories.values():
        for item in catog.items:
            ids_dict[item.itemid] = item

    @staticmethod
    def _premium_cond(premium: bool):
        return not premium
