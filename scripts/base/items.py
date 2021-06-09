"""
This module contains all the items in the Pokegambler world.
"""

# pylint: disable=no-member, unused-argument
# pylint: disable=too-many-instance-attributes

from __future__ import annotations
import random
import re
from abc import ABC
from dataclasses import dataclass
from functools import total_ordering
from inspect import ismethod
from io import BytesIO
from typing import (
    Dict, List, Optional,
    Tuple, Type, TYPE_CHECKING, Union
)

from PIL import Image

from ..base.dbconn import DBConnector
from ..helpers.utils import dedent, get_embed

if TYPE_CHECKING:
    from aiohttp import ClientSession
    from discord import Embed

# region BaseClasses


@dataclass
class Item(ABC):
    """
    Any object which exists in the world of PokeGambler.
    """
    description: str
    category: str
    asset_url: str
    emoji: str
    buyable: bool = True
    sellable: bool = True
    price: Optional[int] = None
    premium: bool = False

    def __iter__(self) -> Tuple:
        for attr in (
            "name", "description", "category",
            "asset_url", "emoji", "buyable",
            "sellable", "price", "premium"
        ):
            yield (attr, getattr(self, attr))

    def __str__(self) -> str:
        return ' '.join(
            re.findall(
                r'[A-Z](?:[a-z]+|[A-Z]*(?=[A-Z]|$))',
                self.__class__.__name__
            )
        )

    def __repr__(self) -> str:
        attr_str = ',\n    '.join(
            f"{attr}={getattr(self, attr)}"
            for attr in dir(self)
            if (
                not attr.startswith("_")
                and not ismethod(getattr(self, attr))
                and getattr(self, attr)
            )
        )
        return f"{self.__class__.__name__}(\n    {attr_str}\n)"

    def save(self, database: DBConnector):
        """
        Saves the Item to the database.
        Sets the itemid of the Item after saving.
        """
        uid = database.save_item(**dict(self))
        setattr(self, "itemid", f"{uid:0>8X}")

    def delete(self, database: DBConnector):
        """
        Deletes the Item from the database.
        """
        if not hasattr(self, "itemid"):
            raise AttributeError(
                f"{self.name} is not yet saved in the database."
            )
        uid = int(self.itemid, 16)
        database.delete_item(uid)

    @property
    def name(self) -> str:
        """
        Returns the name of the Item.
        """
        return str(self)

    @property
    def details(self) -> Embed:
        """
        Returns a rich embed containing full details of an item.
        """
        emb = get_embed(
            content=f"『{self.emoji}』 **{self.description}**",
            title=f"Information for 『{self.name}』",
            image=self.asset_url,
            footer=f"Item Id: {self.itemid}"
        )
        fields = ["category", "buyable", "sellable"]
        if self.category == "Tradable":
            fields.append("price")
        for field in fields:
            emb.add_field(
                name=field,
                value=f"**`{getattr(self, field)}`**",
                inline=True
            )
        return emb

    async def get_image(self, sess: ClientSession) -> Image.Image:
        """
        Downloads and returns the image of the item.
        """
        byio = BytesIO()
        async with sess.get(self.asset_url) as resp:
            data = await resp.read()
        byio.write(data)
        byio.seek(0)
        return Image.open(byio)

    @classmethod
    def get(
        cls: Type[Item], database: DBConnector,
        itemid: int
    ) -> Union[Dict, None]:
        """
        Get an Item with an ID as a dictionary.
        Returns None if item not in the DB.
        """
        return database.get_item(itemid)

    @classmethod
    def _new_item(cls: Type[Item], item: Dict) -> Item:
        category = cls.get_category(item)
        item.pop('category', None)
        itemid = item.pop('itemid', None)
        new_item = type(
            "".join(
                word.title()
                for word in item.pop("name").split(" ")
            ),
            (category, ),
            item
        )(**item)
        new_item.itemid = f'{itemid:0>8X}'
        return new_item

    @classmethod
    def from_id(
        cls: Type[Item], database: DBConnector,
        itemid: int
    ) -> Item:
        """
        Returns a item of specified ID or None.
        """
        item = database.get_item(itemid)
        if not item:
            return None
        return cls._new_item(item)

    @classmethod
    def from_name(
        cls: Type[Item], database: DBConnector,
        name: str
    ) -> Item:
        """
        Returns a item of specified name or None.
        """
        item = database.get_item_from_name(name)
        if not item:
            return None
        return cls._new_item(item)

    @classmethod
    def get_category(cls: Type[Item], item: Dict) -> Type[Item]:
        """
        Resolves category to handle chests differently.
        Returns the base Category of the Item.
        """
        def catog_crawl(cls, catog_name):
            result = set()
            path = [cls]
            while path:
                parent = path.pop()
                for child in parent.__subclasses__():
                    if '.' not in str(child):
                        # In a multi inheritance scenario, __subclasses__()
                        # also returns interim-classes that don't have all the
                        # methods. With this hack, we skip them.
                        continue
                    if child not in result:
                        if child.__name__ == catog_name:
                            result.add(child)
                        path.append(child)
            return result
        category = item["category"]
        if category == "Chest":
            category = Chest
            item["description"] = item["description"].split(
                "[Daily"
            )[0]
        else:
            category = [
                catog
                for catog in cls.__subclasses__()
                if catog.__name__ == category
            ]
            if not category:
                category = catog_crawl(cls, item["category"].title())
            category = next(iter(category))
        return category

    @classmethod
    def list_items(
        cls: Type[Item],
        database: DBConnector,
        category: str = "Tradable",
        limit: int = 5
    ) -> List:
        """
        Unified Wrapper for the SQL endpoints,
        which fetches items of specified category.
        """
        method_type = f"get_{category.lower()}s"
        method = getattr(database, method_type, None)
        if not method:
            return []
        return method(limit)


@dataclass
class Treasure(Item):
    """
    Any non-buyable [Item] is considered a Treasure.
    It is unique to the user and cannot be sold either.
    """
    def __init__(self, **kwargs):
        super().__init__(
            category=kwargs.pop(
                "category",
                "Treasure"
            ),
            **kwargs
        )
        self.buyable: bool = False
        self.sellable: bool = False


@dataclass
class Tradable(Item):
    """
    Any sellable [Item] is a Tradeable.
    It should have a fixed base price.
    Tradables can be bought.
    """
    def __init__(self, **kwargs):
        super().__init__(
            category=kwargs.pop(
                "category",
                "Tradable"
            ),
            **kwargs
        )
        self.price: int = kwargs['price']


@dataclass
class Collectible(Item):
    """
    Collectibles are sellable variants of [Treasure].
    They cannot be bought off the market but can be traded among users.
    """
    def __init__(self, **kwargs):
        super().__init__(
            category=kwargs.pop(
                "category",
                "Collectible"
            ),
            **kwargs
        )
        self.buyable: bool = False


@dataclass
class Consumable(Tradable):
    """
    Consumables can be bought from the shop but cannot be sold back.
    """
    def __init__(self, **kwargs):
        super().__init__(
            category=kwargs.pop(
                "category",
                "Consumable"
            ),
            **kwargs
        )
        self.sellable: bool = False

# endregion

# region Chests


@total_ordering
class Chest(Treasure):
    """
    Chests are spawnable [Treasure] which contain Pokechips based on tiers.
    """
    def __init__(
        self, description: str,
        asset_url: str, emoji: str,
        tier: int = 1,
        **kwargs
    ):
        super().__init__(
            description=description,
            asset_url=asset_url,
            emoji=emoji
        )
        self.category = "Chest"
        self.tier: int = tier

    def __eq__(self, other: Chest):
        return self.chips == other.chips

    def __ge__(self, other: Chest):
        return self.chips >= other.chips

    @property
    def chips(self) -> int:
        """
        Get a random amount of tier-scaled pokechips.
        """
        scale = int(5.7735 ** (self.tier + 1))
        rand_val = random.randint(scale, scale * 9)
        # To make sure lower tier chests are always less worthy
        rand_val = max(rand_val, int(5.7735 ** self.tier) * 9)
        rand_val = min(rand_val, int(5.7735 ** (self.tier + 2)))
        return rand_val

    @classmethod
    def get_chest(cls: Type[Chest], tier: int) -> Chest:
        """
        Get a specified tier Chest.
        """
        chests = [CommonChest, GoldChest, LegendaryChest]
        return chests[tier - 1]()

    @classmethod
    def from_id(
        cls: Type[Chest],
        database: DBConnector,
        itemid: int
    ) -> Chest:
        """
        Returns a chest of specified ID or None.
        """
        item = database.get_item(itemid)
        if not item:
            return None
        name = item["name"].replace(" ", '')
        chests = [
            chest
            for chest in cls.__subclasses__()
            if chest.__name__ == name
        ]
        chest = chests[0]()
        chest.itemid = f'{item["itemid"]:0>8X}'
        chest.description = item["description"]
        return chest

    @classmethod
    def get_random_chest(cls: Type[Chest]) -> Chest:
        """
        Get a random tier Chest with weight of (90, 35, 12)
        for common, gold and legendary resp.
        """
        chest_class = random.choices(
            cls.__subclasses__(),
            k=1,
            weights=(90, 35, 12)
        )[0]
        return chest_class()

    def get_random_collectible(self, database: DBConnector) -> Collectible:
        """
        Get a random [Collectible] with chance based on chest tier.
        Common Chest - 0%
        Gold Chest - 25%
        Legendary Chest - 50%
        """
        chance = (self.tier - 1) * 0.25
        proc = random.uniform(0.1, 0.99)
        if proc >= chance:
            return None
        collectibles = database.get_collectibles(limit=20)
        if not collectibles:
            return None
        col_dict = random.choice(collectibles)
        return Item.from_id(database, col_dict["itemid"])


class CommonChest(Chest):
    """
    Lowest Tier [Chest].
    Chips scale in 100s.
    """
    def __init__(self, **kwargs):
        description: str = dedent(
            """A Tier 1 chest which hs chips in the range of a few hundreds.
            Does not contain any other items."""
        )
        asset_url: str = "https://cdn.discordapp.com/attachments/" + \
            "840469669332516904/844316817593860126/common.png"
        emoji: str = "<:common:844318491745845328>"
        tier: int = 1
        super().__init__(
            description=description,
            asset_url=asset_url,
            emoji=emoji,
            tier=tier
        )


class GoldChest(Chest):
    """
    Mid tier [Chest].
    Chips scale in high-hundreds to low-thousands.
    """
    def __init__(self, **kwargs):
        description: str = dedent(
            """A Tier 2 chest which has chips in the range of
            high-hundreds to low-thousands.
            Does not contain any other items."""
        )
        asset_url: str = "https://cdn.discordapp.com/attachments/" + \
            "840469669332516904/844316818167824424/gold.png"
        emoji: str = "<:gold:844318490885357578>"
        tier: int = 2
        super().__init__(
            description=description,
            asset_url=asset_url,
            emoji=emoji,
            tier=tier
        )


class LegendaryChest(Chest):
    """
    Highest Tier [Chest].
    Chips scale in the thousands.
    Legendary Chests have a small chance of containing [Collectible]s.
    """
    def __init__(self, **kwargs):
        description: str = dedent(
            """A Tier 3 chest which has chips in the range of thousands.
            Has a small chance of containing [Collectible]s."""
        )
        asset_url: str = "https://cdn.discordapp.com/attachments/" + \
            "840469669332516904/844318374217121822/legendary.png"
        emoji: str = "<:legendary:844318490638680135>"
        tier: int = 3
        super().__init__(
            description=description,
            asset_url=asset_url,
            emoji=emoji,
            tier=tier
        )

# endregion


@dataclass
class Gladiator(Consumable):
    """
    Minions that can be bought and used in Gladiator match minigames.
    They can be considered as a [Consumable] but do not stack.
    """
    def __init__(self, **kwargs):
        kwargs.pop('category', None)
        super().__init__(category="Gladiator", **kwargs)


@dataclass
class Lootbag(Treasure):
    """
    Lootbags contain other items inside them.
    Premium Lootbags can also contain Premium Items.
    """
    def __init__(self, items: Optional[List[Item]] = None, **kwargs):
        super().__init__(
            category=kwargs.pop(
                "category",
                "Lootbag"
            ),
            **kwargs
        )

    def get_random_items(
        self, database: DBConnector,
        categories: Optional[List[str]] = None,
        count: Optional[int] = 3
    ) -> Item:
        """
        Retrieves a random existing item of chosen category.
        Returns at most 3 items by default.
        """
        items = database.get_items(
            categories=categories,
            limit=20,
            include_premium=self.premium
        )
        if not items:
            return None
        rand_items = []
        premium_added = False
        while len(rand_items) <= count and len(items) > 0:
            if self.premium and not premium_added:
                itm_dict = random.choices(
                    items, k=1, weights=[
                        int(item["premium"])
                        for item in items
                    ]
                )[0]
                premium_added = True
            else:
                itm_dict = random.choices(
                    items, k=1, weights=[
                        -int(item["premium"])
                        for item in items
                    ]
                )[0]
            items.remove(itm_dict)
            if itm_dict["category"] not in (
                itm["category"]
                for itm in rand_items
            ):
                rand_items.append(itm_dict)
        return [
            Item.from_id(database, itm_dict["itemid"])
            for itm_dict in rand_items
        ]

    @property
    def chips(self) -> int:
        """
        Return random amount of Pokechips in following ranges:
            Normal => [100, 499]
            Premium => [500, 1000]
        """
        limits = [100, 499]
        if self.premium:
            limits = [500, 1000]
        return random.randint(*limits)
