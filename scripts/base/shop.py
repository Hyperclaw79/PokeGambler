"""
This module is a compilation of all shop related classed.
"""

# pylint: disable=too-few-public-methods, unused-argument
# pylint: disable=invalid-overridden-method, arguments-differ
# pylint: disable=too-many-instance-attributes

from abc import abstractmethod
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Union

from discord import Member, Message
from discord.errors import Forbidden

from ..base.items import Item
from ..base.models import Inventory, Profile
from .dbconn import DBConnector


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
            await message.author.edit(
                nick=f"『{role.name}』 {message.author.nick or message.author.name}"
            )
            self.debit_player(database, message.author)
        except Forbidden:
            await message.channel.send(
                "**You're too OP for me to give you a role.**\n"
                "**Please ask an admin to give you the role.**\n"
            )


class BoostItem(ShopItem):
    """
    This class represents a purchasable temporary boost.
    """
    async def buy(
        self, ctx, database: DBConnector,
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
            ctx.boost_dict[user.id][self.itemid]["stack"] += quantity
        self.debit_player(
            database=database,
            user=message.author,
            quantity=quantity
        )


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
                    "You're one of the dealers and have access to the gamble command.",
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
                    500, "💰"
                ),
                BoostItem(
                    "boost_lt_cd",
                    "Loot Lust",
                    "Decreases Loot Cooldown by 1 minute.",
                    500, "⌛"
                ),
                BoostItem(
                    "boost_tr",
                    "Fortune Burst",
                    "Increase Treasure Chance while looting by 10%.",
                    1000, "💎"
                ),
                BoostItem(
                    "boost_flip",
                    "Flipster",
                    "Increase reward for QuickFlip minigame by 10%.",
                    1000, "🎲"
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
        )
    }

    ids_dict: Dict[str, ShopItem] = {}
    for catog in categories.values():
        for item in catog.items:
            ids_dict[item.itemid] = item

    @classmethod
    def get_item(cls, database: DBConnector, itemid: str) -> ShopItem:
        """
        Returns the item registered in Shop based on itemID.
        """
        if itemid in cls.ids_dict:
            return cls.ids_dict[itemid]
        return TradebleItem(
            itemid=int(itemid, 16),
            **dict(
                Item.from_id(database, int(itemid, 16))
            )
        )

    @classmethod
    def add_category(cls, category: ShopCategory):
        """
        Adds a new category to the Shop.
        """
        cls.categories[category.name] = category

    @classmethod
    def update_category(
        cls, category: str,
        *items: List[ShopItem]
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
    def refresh_tradables(cls, database: DBConnector):
        """
        Similar to Shop.update_category, but exclusive for Tradables.
        """
        items = [
            TradebleItem(
                item["itemid"], item["name"],
                item["description"], item["price"],
                item["emoji"],
                pinned="permanent" in item["description"].lower()
            )
            for item in database.get_tradables(limit=5)
        ]
        cls.update_category("Tradables", *items)

    @classmethod
    def validate(
        cls, database: DBConnector,
        user: Member, item: ShopItem
    ) -> str:
        """
        Validates if an item is purchasable and affordable by the user.
        In sell mode, validates if it's sellable and exists in user's inventory.
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
