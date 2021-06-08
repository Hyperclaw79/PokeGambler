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
from ..base.models import Inventory, Profile
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

    def __str__(self) -> str:
        if not self.emoji:
            return f"{self.name} "
        return f"{self.name} 『{self.emoji}』"

    def debit_player(self, database, user, quantity=1):
        """
        Debits the player the price of the item.
        """
        Profile(database, user).debit(
            amount=(self.price * quantity)
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
            quantity=quantity
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
    async def buy(
        self, ctx: PokeGambler, database: DBConnector,
        message: Message, quantity: int = 1,
        **kwargs
    ):
        """
        Applies the relevant temporary boost to the user.
        """
        async def __boost_handler(ctx, user):
            if user.id not in ctx.boost_dict:
                ctx.boost_dict[user.id] = {
                    item.itemid: {
                        "stack": 0,
                        "name": item.name,
                        "description": item.description,
                        "added_on": datetime.now()
                    }
                    for item in Shop.categories["Boosts"].items
                }
            ctx.boost_dict[user.id][self.itemid]["stack"] += quantity
            ctx.boost_dict[user.id][self.itemid].update({
                "added_on": datetime.now()
            })
            await asyncio.sleep(30 * 60)
            ctx.boost_dict[user.id][self.itemid]["stack"] = 0
        user = message.author
        if (
            user.id not in ctx.boost_dict
            or ctx.boost_dict[user.id][self.itemid]["stack"] == 0
        ):
            ctx.loop.create_task(
                __boost_handler(ctx, user)
            )
        else:
            if ctx.boost_dict[user.id][self.itemid]["stack"] == 5:
                return "You've maxed out to 5 stacks for this boost."
            ctx.boost_dict[user.id][self.itemid]["stack"] += quantity
        self.debit_player(
            database=database,
            user=message.author,
            quantity=quantity
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

    ids_dict: Dict[str, ShopItem] = {}
    for catog in categories.values():
        for item in catog.items:
            ids_dict[item.itemid] = item

    @classmethod
    def get_item(
        cls: Type[Shop],
        database: DBConnector,
        itemid: str
    ) -> ShopItem:
        """
        Returns the item registered in Shop based on itemID.
        """
        if itemid in cls.ids_dict:
            return cls.ids_dict[itemid]
        item = Item.from_id(database, int(itemid, 16))
        if item.premium:  # pylint: disable=no-member
            return None
        return TradebleItem(
            itemid=int(itemid, 16),
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
            items = [
                TradebleItem(
                    item["itemid"], item["name"],
                    item["description"], item["price"],
                    item["emoji"],
                    pinned="permanent" in item["description"].lower()
                )
                for item in getattr(
                    database,
                    f"get_{item_type.lower()}"
                )(limit=5)
            ]
            cls.update_category(item_type, items)

    @classmethod
    def validate(
        cls: Type[Shop], database: DBConnector,
        user: Member, item: ShopItem
    ) -> str:
        """
        Validates if an item is purchasable and affordable by the user.
        """
        if (
            isinstance(item, TradebleItem)
            and not Item.from_id(database, item.itemid)
        ):
            return "Item does not exist anymore."
        # pylint: disable=no-member
        if Profile(database, user).balance < item.price:
            return "You have Insufficient Balance."
        return "proceed"
