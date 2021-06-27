"""
This module is a compilation of all shop related classed.
"""

# pylint: disable=too-few-public-methods, unused-argument
# pylint: disable=invalid-overridden-method, arguments-differ
# pylint: disable=too-many-instance-attributes

from __future__ import annotations
from abc import abstractmethod
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, TYPE_CHECKING, Type, Union

from discord import Member, Message
from discord.errors import Forbidden, HTTPException

from ..base.items import Item
from ..base.models import Boosts, Inventory, Loots, Profile
from .dbconn import DBConnector

if TYPE_CHECKING:
    from bot import PokeGambler


@dataclass
class ShopItem:
    """
    Base class for any item visible in the Shop.
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

    def __str__(self) -> str:
        if not self.emoji:
            return f"{self.name} "
        return f"{self.name} 『{self.emoji}』"

    def debit_player(
        self, database: DBConnector,
        user: Member, quantity: int = 1,
        premium: bool = False
    ):
        """
        Debits the player the price of the item.
        """
        amount = self.price * quantity
        bonds = False
        if premium:
            amount //= 10
            bonds = True
        Profile(database, user).debit(
            amount=amount, bonds=bonds
        )

    @abstractmethod
    def buy(self, **kwargs):
        """
        Every ShopItem should have a buy action.
        """


class TradebleItem(ShopItem):
    """
    This class represents a shop version of [Tradable].
    """
    def buy(
        self, database: DBConnector,
        message: Message, quantity: int,
        **kwargs
    ):
        """
        Buys the Item and places in user's inventory.
        """
        inventory = Inventory(database, message.author)
        for _ in range(quantity):
            inventory.save(self.itemid)
        self.debit_player(
            database=database,
            user=message.author,
            quantity=quantity,
            premium=self.premium
        )
        return "success"


class Title(ShopItem):
    """
    This class represents a purchasable Title.
    """
    async def buy(self, database: DBConnector, message: Message, **kwargs):
        """
        Automatically adds the titled role to the user.
        """
        roles = [
            role
            for role in message.guild.roles
            if role.name.lower() == self.name.lower()
        ]
        if not roles:
            raise ValueError(f"Role {self.name} does not exist!")
        role = roles[0]
        try:
            await message.author.add_roles(role)
            new_nick = message.author.nick or message.author.name
            for title in Shop.categories["Titles"].items:
                if title.name in new_nick:
                    new_nick = new_nick.replace(f"『{title.name}』", '')
            try:
                await message.author.edit(
                    nick=f"『{role.name}』{new_nick}"
                )
            except HTTPException:
                pass
            self.debit_player(database, message.author)
            return "success"
        except Forbidden:
            return str(
                "**You're too OP for me to give you a role.**\n"
                "**Please ask an admin to give you the role.**\n"
            )


class BoostItem(ShopItem):
    """
    This class represents a purchasable temporary boost.
    """
    async def __boost_handler(
        self, ctx: PokeGambler,
        user: Member, quantity: int
    ):
        if user.id not in ctx.boost_dict:
            ctx.boost_dict[user.id] = self.create_boost_dict()
        ctx.boost_dict[user.id][self.itemid]["stack"] += quantity
        ctx.boost_dict[user.id][self.itemid].update({
            "added_on": datetime.now()
        })
        await asyncio.sleep(30 * 60)
        ctx.boost_dict[user.id][self.itemid]["stack"] = 0

    @staticmethod
    def create_boost_dict():
        """
        Returns a new boosts dictionary.
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

    async def buy(
        self, ctx: PokeGambler, database: DBConnector,
        message: Message, quantity: int = 1,
        **kwargs
    ):
        """
        Applies the relevant temporary boost to the user.
        """
        user = message.author
        tier = Loots(database, user).tier
        if (
            user.id not in ctx.boost_dict
            or ctx.boost_dict[user.id][self.itemid]["stack"] == 0
        ):
            ctx.loop.create_task(
                self.__boost_handler(ctx, user, quantity)
            )
        elif any([
            ctx.boost_dict[user.id][self.itemid]["stack"] == 5,
            self._check_lootlust(ctx, database, user, quantity)
        ]):
            return (
                "You've maxed out to 5 stacks for this boost."
                if quantity == 1
                else "You can't puchase that many "
                "as it exceeds max stack of 5."
            )
        else:
            ctx.boost_dict[user.id][self.itemid]["stack"] += quantity
        Profile(database, user).debit(
            amount=((self.price * (10 ** (tier - 1))) * quantity)
        )
        return "success"

    def _check_lootlust(
        self, ctx: PokeGambler, database: DBConnector,
        user: Member, quantity: int
    ):
        if self.itemid not in ["boost_lt_cd", "boost_pr_lt_cd"]:
            return False
        units = [
            Boosts(database, user).get()["loot_lust"],
            quantity,
            ctx.boost_dict.get(
                user.id,
                {"boost_lt_cd": {"stack": 0}}
            )["boost_lt_cd"]["stack"]
        ]
        return sum(units) > 5


class PremiumBoostItem(BoostItem):
    """
    Permanent Boosts purchasable from Premium Shop
    """
    def buy(
        self, ctx: PokeGambler, database: DBConnector,
        message: Message, quantity: int = 1,
        **kwargs
    ):
        user = message.author
        if self._check_lootlust(ctx, database, user, quantity):
            return (
                "You've maxed out to 5 stacks for this boost."
                if quantity == 1
                else "You can't puchase that many "
                "as it exceeds max stack of 5."
            )
        tier = Loots(database, user).tier
        boost = Boosts(database, user)
        boost_name = self.name.lower().replace(' ', '_')
        curr = boost.get()[boost_name]
        boost.update(**{boost_name: curr + quantity})
        Profile(database, user).debit(
            amount=((self.price * (10 ** (tier - 2))) * quantity),
            bonds=True
        )
        return "success"


@dataclass
class ShopCategory:
    """
    This class holds categories of PokeGambler Shop.
    """
    name: str
    description: str
    emoji: str
    items: List[Union[Title, BoostItem, TradebleItem]]

    def __str__(self) -> str:
        return f"『{self.emoji}』 {self.name}"


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
            [
                Title(
                    "title_dlr",
                    "Dealers",
                    "Get access to the gamble command and other perks.",
                    20_000
                ),
                Title(
                    "title_cnm",
                    "Commoner No More",
                    "You're wealthier than the casuals.",
                    20_000
                ),
                Title(
                    "title_wealthy",
                    "The Wealthy",
                    "You're climbing the ladder towards richness.",
                    50_000
                ),
                Title(
                    "title_duke",
                    "Duke",
                    "You literally own a kingdom at this point.",
                    150_000
                ),
                Title(
                    "title_insane",
                    "Insane",
                    "Dude what the hell?! That's way more than enough chips"
                    " for a lifetime.",
                    1_000_000
                )
            ]
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
            [
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
            ]
        ),
        "Tradables": ShopCategory(
            "Tradables",
            """
            These are the items in the PokeGambler world which can be
            bought, sold and traded with players.
            Might even contain player created Items.
            """,
            "📦",
            []
        ),
        "Consumables": ShopCategory(
            "Consumables",
            """
            These items exists solely for your consumption.
            They cannot be sold back to the shop.
            """,
            "🛒",
            []
        ),
        "Gladiators": ShopCategory(
            "Gladiators",
            """
            These champions of the old have been cloned for you.
            You can buy them to make them fight in brutal gladiator fights.
            """,
            "💀",
            []
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

    @staticmethod
    def _premium_cond(premium: bool):
        return premium

    @classmethod
    def get_item(
        cls: Type[Shop],
        database: DBConnector,
        itemid: str, force_new: bool = False
    ) -> ShopItem:
        """
        Returns the item registered in Shop based on itemID.
        """
        if itemid in cls.ids_dict:
            return cls.ids_dict[itemid]
        if any(
            ch.lower() not in 'abcdef1234567890'
            for ch in itemid
        ):
            return None
        item = Item.from_id(database, int(itemid, 16), force_new=force_new)
        if cls._premium_cond(item.premium):  # pylint: disable=no-member
            return None
        return TradebleItem(
            itemid=int(item.itemid, 16),
            **dict(item)
        )

    @classmethod
    def add_category(cls: Type[Shop], category: ShopCategory):
        """
        Adds a new category to the Shop.
        """
        cls.categories[category.name] = category

    @classmethod
    def update_category(
        cls: Type[Shop], category: str,
        items: List[ShopItem]
    ):
        """
        Updates an existing category in the Shop.
        """
        new_items = [
            item
            for item in items
            if item.name not in (
                itm.name
                for itm in cls.categories[category].items
            )
        ]
        if len(cls.categories[category].items) + len(new_items) <= 5:
            cls.categories[category].items.extend(new_items)
            return
        removables = [
            item
            for item in cls.categories[category].items[::-1]
            if not item.pinned
        ][:len(new_items)]
        num_in_stock = len(cls.categories[category].items) - len(removables)
        num_updatable = len(new_items) - num_in_stock
        updates = new_items[::-1][:num_updatable][::-1]
        for item in removables:
            cls.categories[category].items.remove(item)
        cls.categories[category].items = (
            updates + cls.categories[category].items
        )

    @classmethod
    def refresh_tradables(cls: Type[Shop], database: DBConnector):
        """
        Similar to Shop.update_category, but exclusive for Tradables.
        """
        item_types = ["Tradables", "Consumables", "Gladiators"]
        for item_type in item_types:
            # Check availability of existing items
            cls.categories[item_type].items = [
                item
                for item in cls.categories[item_type].items
                if database.get_item(item.itemid)
            ]
            items = [
                TradebleItem(
                    item["itemid"], item["name"],
                    item["description"], item["price"],
                    item["emoji"],
                    pinned="permanent" in item["description"].lower(),
                    premium=item["premium"]
                )
                for item in getattr(
                    database,
                    f"get_{item_type.lower()}"
                )(limit=5, premium=cls.premium)
            ]
            cls.update_category(item_type, items)

    @classmethod
    def validate(
        cls: Type[Shop], database: DBConnector,
        user: Member, item: ShopItem, quantity: int = 1
    ) -> str:
        """
        Validates if an item is purchasable and affordable by the user.
        """
        if (
            isinstance(item, TradebleItem)
            and not Item.from_id(database, item.itemid)
        ):
            return "Item does not exist anymore."
        price = item.price
        if item.__class__ in [BoostItem, PremiumBoostItem]:
            price *= 10 ** (Loots(database, user).tier - 1)
        curr_attr = "balance"
        if item.premium:
            curr_attr = "pokebonds"
            price //= 10
        if getattr(
            Profile(database, user),
            curr_attr
         ) < price * quantity:
            return "You have Insufficient Balance."
        return "proceed"


class PremiumShop(Shop):
    """
    The subclass of Shop for premium-only items.
    """
    categories: Dict[str, ShopCategory] = {
        "Titles": ShopCategory(
            "Titles",
            """
            Flex your financial status using a special Title.
            Titles will automatically give you a role named as the title.
            """,
            "📜",
            [
                Title(
                    "title_pr",
                    "The Patron",
                    "Dedicated patron of PokeGambler.",
                    2000
                )
            ]
        ),
        "Boosts": ShopCategory(
            "Boosts",
            """
            Give yourself a competitive edge by improving certain stats.
            Boosts purchased through premium shop are permanent.
            Buying new ones increases the effect.
            """,
            "🧬",
            [
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
            ]
        ),
        "Tradables": ShopCategory(
            "Tradables",
            """
            These are the items in the PokeGambler world which can be
            bought, sold and traded with players.
            Might even contain player created Items.
            """,
            "📦",
            []
        ),
        "Consumables": ShopCategory(
            "Consumables",
            """
            These items exists solely for your consumption.
            They cannot be sold back to the shop.
            """,
            "🛒",
            []
        ),
        "Gladiators": ShopCategory(
            "Gladiators",
            """
            These champions of the old have been cloned for you.
            You can buy them to make them fight in brutal gladiator fights.
            """,
            "💀",
            []
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
