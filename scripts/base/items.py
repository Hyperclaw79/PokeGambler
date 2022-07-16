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

This module contains schematics for all the items in the Pokegambler world.
"""

# pylint: disable=no-member, unused-argument
# pylint: disable=too-many-instance-attributes

from __future__ import annotations
import os
import random
import re
from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from functools import total_ordering
from hashlib import md5
from io import BytesIO
from typing import (
    Dict, List, Optional,
    Tuple, Type, TYPE_CHECKING
)

import certifi
from dotenv import load_dotenv
from PIL import Image
from pymongo import MongoClient

# pylint: disable=cyclic-import
from ..helpers.utils import dedent, get_embed

if TYPE_CHECKING:
    from aiohttp import ClientSession
    from discord import Embed

load_dotenv()

DB_CLIENT = MongoClient(
    os.getenv("MONGO_CLUSTER_STRING"),
    tlsCAfile=certifi.where()
).pokegambler


# region Base Classes
@dataclass
class Item(ABC):
    """Any object which exists in the world of PokeGambler.

    :param description: A description of the item.
    :type description: str
    :param category: The category of the item.
    :type category: str
    :param asset_url: The URL of the item's asset.
    :type asset_url: str
    :param emoji: The emoji of the item.
    :type emoji: str
    :param buyable: Whether the item can be bought.
    :type buyable: bool
    :param sellable: Whether the item can be sold.
    :type sellable: bool
    :param price: The price of the item.
    :type price: Optional[int]
    :param premium: Whether the item is premium.
    :type premium: bool
    """
    description: str
    category: str
    asset_url: str
    emoji: str
    buyable: bool = True
    sellable: bool = True
    price: Optional[int] = None
    premium: bool = False
    created_on: field(
        default_factory=datetime
    ) = datetime.now()
    # MongoDB Client
    mongo = DB_CLIENT.items

    def __eq__(self, other: Item) -> bool:
        return self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)

    def __iter__(self) -> Tuple:
        for attr in self.attrs:
            yield (attr, getattr(self, attr))

    def __post_init__(self):
        self.itemid = md5(
            str(datetime.utcnow()).encode()
        ).hexdigest()[:8]
        self.attrs = (
            "itemid", "name", "description", "category",
            "asset_url", "emoji", "buyable",
            "sellable", "price", "premium"
        )

    def __repr__(self) -> str:
        attr_str = ',\n    '.join(
            f"{attr}={getattr(self, attr)}"
            for attr in self.attrs
        )
        return f"{self.__class__.__name__}(\n    {attr_str}\n)"

    def __str__(self) -> str:
        return ' '.join(
            re.findall(
                r'[A-Z](?:[a-z]+|[A-Z]*(?=[A-Z]|$))',
                self.__class__.__name__
            )
        )

    async def get_image(self, sess: ClientSession) -> Image.Image:
        """Downloads and returns the image of the item.

        :param sess: An aiohttp ClientSession object.
        :type sess: :class:`aiohttp.ClientSession`
        :return: The image of the item.
        :rtype: :class:`PIL.Image.Image`
        """
        byio = BytesIO()
        async with sess.get(self.asset_url) as resp:
            data = await resp.read()
        byio.write(data)
        byio.seek(0)
        return Image.open(byio)

    def delete(self):
        """
        Deletes the Item from the Collection.
        """
        self.mongo.delete_one({"_id": self.itemid})

    def save(self):
        """
        Saves the Item to the Collection.
        Sets the itemid of the Item after saving.
        """
        attrs = dict(self)
        attrs["_id"] = attrs.pop("itemid")
        attrs["created_on"] = datetime.now()
        self.mongo.insert_one(attrs)

    def update(
        self, modify_all: Optional[bool] = False,
        **kwargs
    ):
        """Updates an existing item.

        :param modify_all: Modify all copies of the item, defaults to False
        :type modify_all: Optional[bool]
        """
        if not kwargs:
            return
        for key, val in kwargs.items():
            setattr(self, key, val)
        filter_ = {'_id': self.itemid}
        if modify_all:
            filter_ = {'name': self.name}
        self.mongo.update_many(
            filter_,
            {'$set': kwargs}
        )

    @property
    def name(self) -> str:
        """Returns the name of the Item.

        :return: The name of the Item.
        :rtype: str
        """
        return getattr(self, "_name", str(self))

    @name.setter
    def name(self, value: str):
        """Sets the name of the Item.

        :param value: The name of the Item.
        :type value: str
        """
        self._name = value

    @property
    def category_class(self) -> Type[Item]:
        """Returns the class of the Item's category.

        :return: The class of the Item's category.
        :rtype: :class:`~scripts.base.items.Item`
        """
        return globals()[self.category.title()]

    @property
    def details(self) -> Embed:
        """Returns a rich embed containing full details of an item.

        :return: Full details of an item.
        :rtype: :class:`discord.Embed`
        """
        emb = get_embed(
            content=f"『{self.emoji}』 **{self.description}**",
            title=f"Information for 『{self.name}』",
            image=self.asset_url,
            footer=f"Item Id: {self.itemid}"
        )
        fields = [
            "category", "buyable",
            "sellable", "premium"
        ]
        if self.category == "Tradable":
            fields.append("price")
        for field_ in fields:
            emb.add_field(
                name=field_.title(),
                value=f"**`{getattr(self, field_)}`**",
                inline=True
            )
        return emb

    @classmethod
    def from_id(
        cls: Type[Item], itemid: int,
        force_new: bool = False
    ) -> Item:
        """Returns an Item from the Collection base on its itemid.

        :param itemid: The id of the Item.
        :type itemid: int
        :param force_new: Force a new Item to be created, defaults to False.
        :type force_new: bool
        :return: The existing/newly created Item.
        :rtype: :class:`Item`
        """
        item = cls.get(itemid)
        if not item:
            return None
        return cls._new_item(item, force_new=force_new)

    @classmethod
    def bulk_from_id(
        cls: Type[Item], itemids: List[str],
        force_new: bool = False
    ) -> List[Item]:
        """Returns a list of Items from the Collection base on their itemids.

        :param itemids: The ids of the Items.
        :type itemids: List[str]
        :param force_new: Force a new Item to be created, defaults to False.
        :type force_new: bool
        :return: The existing/newly created Items.
        :rtype: List[:class:`Item`]
        """
        new_items = []
        item_dict_list = []
        for item in cls.bulk_get(itemids):
            # Bulk Get returns a distinct list of items.
            for _ in range(itemids.count(item['_id'])):
                new_item = cls._new_item(item, force_new=False)
                attrs = dict(new_item)
                attrs.pop("itemid")
                attrs['_id'] = md5(
                    str(datetime.utcnow()).encode()
                    + random.randbytes(16)
                ).hexdigest()[:8]
                attrs["created_on"] = datetime.now()
                new_item.itemid = attrs['_id']
                new_items.append(new_item)
                item_dict_list.append(attrs)
        if force_new:
            cls.insert_many(item_dict_list)
        return new_items

    @classmethod
    def from_name(
        cls: Type[Item], name: str,
        force_new: bool = False
    ) -> Item:
        """Returns an Item from the Collection base on its name.

        :param name: The name of the Item.
        :type name: str
        :param force_new: Force a new Item to be created, defaults to False.
        :type force_new: bool
        :return: The existing/newly created Item.
        :rtype: :class:`Item`
        """
        item = cls.mongo.find_one({
            "name": {
                "$regex": f"^{name}",
                "$options": "i"
            }
        })
        if not item:
            return None
        return cls._new_item(item, force_new=force_new)

    @classmethod
    def from_dict(
        cls: Type[Item],
        data: Dict
    ) -> Item:
        """Returns an Item based on available data.

        :param data: The data of the Item.
        :type data: Dict
        :return: The prepopulated Item.
        :rtype: :class:`Item`
        """
        return cls._new_item(data, force_new=False)

    @classmethod
    def get(cls: Type[Item], itemid: str) -> Dict:
        """Returns an Item from the Collection base on its itemid.

        :param itemid: The id of the Item.
        :type itemid: str
        :return: The dictionary of the Item.
        :rtype: Dict
        """
        return cls.mongo.find_one({"_id": itemid})

    @classmethod
    def bulk_get(cls: Type[Item], itemids: List[str]) -> List[Dict]:
        """Returns a list of Items from the Collection base on their itemids.

        :param itemids: The ids of the Items.
        :type itemids: List[str]
        :return: The list of dictionaries of the Items.
        :rtype: List[Dict]
        """
        return cls.mongo.find({"_id": {"$in": itemids}})

    @classmethod
    def get_category(cls: Type[Item], item: Dict) -> Type[Item]:
        """Resolves category to handle chests differently.
        Returns the base Category of the Item.

        :param item: The Item to get the category from.
        :type item: Dict
        :return: The base Category of the Item.
        :rtype: Type[:class:`Item`]
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
        category = [
            catog
            for catog in cls.__subclasses__()
            if catog.__name__ == item["category"]
        ]
        if not category:
            category = catog_crawl(cls, item["category"].title())
        category = next(iter(category))
        return category

    @classmethod
    def get_unique_items(cls) -> List[Dict]:
        """Gets all items with a unique name.

        :return: A list of all items with a unique name.
        :rtype: List[Dict]
        """
        return list(cls.mongo.aggregate([
            {
                "$match": {
                    "category": {"$ne": "Chest"}
                }
            },
            {
                "$group": {
                    "_id": "$name",
                    "items": {"$first": "$$ROOT"}
                }
            },
            {"$replaceRoot": {"newRoot": "$items"}}
        ]))

    @classmethod
    def latest(
        cls: Type[Item],
        limit: Optional[int] = 5
    ) -> List[Dict]:
        """Returns the latest items added to the Collection.

        :param limit: The maximum number of items to return, defaults to 5.
        :type limit: Optional[int]
        :return: A list of the latest items added to the Collection.
        :rtype: List[Dict]
        """
        return list(
            cls.mongo.aggregate([
                {
                    "$match": {
                        "category": {"$ne": "Chest"}
                    }
                },
                {
                    "$group": {
                        "_id": "$name",
                        "items": {"$first": "$$ROOT"}
                    }
                },
                {"$replaceRoot": {"newRoot": "$items"}},
                {"$set": {"itemid": "$_id"}},
                {"$unset": "_id"},
                {"$sort": {"created_on": -1}},
                {"$limit": limit}
            ])
        )

    @classmethod
    def insert_many(cls, items: List[Dict]):
        """Inserts many items into the Collection.

        :param items: A list of items to insert.
        :type items: List[Dict]
        """
        for item in items:
            if "created_on" not in item:
                item["created_on"] = datetime.now()
        cls.mongo.insert_many(items)

    @classmethod
    def list_items(
        cls: Type[Item],
        category: str = "Tradable",
        limit: Optional[int] = 5,
        premium: Optional[bool] = None
    ) -> List:
        """List items of a certain category.

        :param category: The category of the items to list, defaults to
            "Tradable".
        :type category: str
        :param limit: The maximum number of items to return, defaults to 5.
        :type limit: Optional[int]
        :param premium: If True, only return premium items, defaults to None.
        :type premium: Optional[bool]
        :return: A list of the items of the given category.
        :rtype: List
        """
        filter_ = {
            'category': category.title(),
            'inventory': {'$eq': []}
        }
        if premium is not None:
            filter_['premium'] = premium
        pipeline = [
            {
                "$lookup":
                    {
                        "from": "inventory",
                        "localField": "_id",
                        "foreignField": "itemid",
                        "as": "inventory"
                    }
            },
            {"$match": filter_},
            {
                "$group": {
                    "_id": "$name",
                    "items": {"$first": "$$ROOT"}
                }
            },
            {"$replaceRoot": {"newRoot": "$items"}},
            {"$limit": limit}
        ]
        items = list(
            cls.mongo.aggregate(pipeline)
        )
        modded_items = []
        for item in items:
            item["itemid"] = item.pop("_id")
            modded_items.append(item)
        return modded_items

    @classmethod
    def purge(cls):
        """
        Purges the Items collection.
        """
        cls.mongo.delete_many({})

    @classmethod
    def _new_item(
        cls: Type[Item], existing_item: Dict,
        force_new: bool = False
    ) -> Item:
        old_item = {**existing_item}
        category = cls.get_category(old_item)
        old_item.pop('category', None)
        item_id = old_item.pop('_id', None)
        itemid = old_item.pop('itemid', None)
        itemid = itemid or item_id
        new_item = type(
            "".join(
                word.title()
                for word in old_item.pop("name").split(" ")
            ),
            (category, ),
            old_item
        )(**old_item)
        if force_new:
            new_item.save()
        elif itemid:
            new_item.itemid = itemid
        else:
            new_item.__post_init__()
        return new_item


@dataclass(eq=False)
class Treasure(Item):
    """
    Any non-buyable :class:`Item` is considered a Treasure.
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


@dataclass(eq=False)
class Tradable(Item):
    """
    Any buyable and sellable :class:`Item` is a Tradeable.
    It should have a fixed base price.
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


@dataclass(eq=False)
class Collectible(Item):
    """
    Collectibles are sellable variants of :class:`Treasure`.
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


@dataclass(eq=False)
class Consumable(Tradable):
    """
    :class:`Item` buyable from Shop but can't be sold back.
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
    Chests are spawnable :class:`Treasure` which contain \
        Pokechips based on tiers.

    :param description: A description of the chest.
    :type description: str
    :param asset_url: The URL of the chest's asset.
    :type asset_url: str
    :param emoji: The emoji of the item.
    :type emoji: str
    :param tier: The tier of the chest.
    :type tier: int
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
        self.attrs += ('tier', )

    def __eq__(self, other: Chest):
        return self.chips == other.chips

    def __ge__(self, other: Chest):
        return self.chips >= other.chips

    @property
    def chips(self) -> int:
        """Get a random amount of tier-scaled pokechips.

        :return: Number of Pokechips.
        :rtype: int
        """
        scale = int(5.7735 ** (self.tier + 1))
        rand_val = random.randint(scale, scale * 9)
        # To make sure lower tier chests are always less worthy
        rand_val = max(rand_val, int(5.7735 ** self.tier) * 9)
        rand_val = min(rand_val, int(5.7735 ** (self.tier + 2)))
        return rand_val

    @classmethod
    def get_chest(cls: Type[Chest], tier: int) -> Chest:
        """Get a specified tier Chest.

        :param tier: The tier of the Chest.
        :type tier: int
        :return: A Chest of the specified tier.
        :rtype: :class:`Chest`
        """
        chests = [CommonChest, GoldChest, LegendaryChest]
        return chests[tier - 1]()

    @classmethod
    def get_random_chest(cls: Type[Chest]) -> Chest:
        """Get a random tier Chest with weight of (90, 35, 12)
        for common, gold and legendary resp.

        :return: A Chest of a random tier.
        :rtype: :class:`Chest`
        """
        chest_class = random.choices(
            cls.__subclasses__(),
            k=1,
            weights=(90, 35, 12)
        )[0]
        return chest_class()

    def get_random_collectible(self) -> Collectible:
        """Get a random :class:`Collectible` with chance based on chest tier.

        .. note::
           * Common Chest - 0%
           * Gold Chest - 25%
           * Legendary Chest - 50%

        :return: A random collectible.
        :rtype: :class:`Collectible`
        """
        chance = (self.tier - 1) * 0.25
        proc = random.uniform(0.1, 0.99)
        if proc >= chance:
            return None
        collectibles = Item.list_items("Collectible", limit=20)
        if not collectibles:
            return None
        col_dict = random.choice(collectibles)
        return Item.from_id(col_dict["itemid"])


class CommonChest(Chest):
    """
    Lowest Tier :class:`Chest`.
    Chips scale in 100s.
    """
    def __init__(self, **kwargs):
        description: str = dedent(
            """A Tier 1 chest which hs chips in the range of a few hundreds.
            Does not contain any other items."""
        )
        asset_url: str = "https://cdn.discordapp.com/attachments/" + \
            "874623706339618827/874628500437467196/common.png"
        emoji: str = "<:common:874626457438158868>"
        tier: int = 1
        super().__init__(
            description=description,
            asset_url=asset_url,
            emoji=emoji,
            tier=tier
        )


class GoldChest(Chest):
    """
    Mid tier :class:`Chest`.
    Chips scale in high-hundreds to low-thousands.
    """
    def __init__(self, **kwargs):
        description: str = dedent(
            """A Tier 2 chest which has chips in the range of
            high-hundreds to low-thousands.
            Does not contain any other items."""
        )
        asset_url: str = "https://cdn.discordapp.com/attachments/" + \
            "874623706339618827/874628501876137984/gold.png"
        emoji: str = "<:gold:874626456993534042>"
        tier: int = 2
        super().__init__(
            description=description,
            asset_url=asset_url,
            emoji=emoji,
            tier=tier
        )


class LegendaryChest(Chest):
    """
    Highest Tier :class:`Chest`.
    Chips scale in the thousands.
    Legendary Chests have a small chance of containing :class:`Collectible`.
    """
    def __init__(self, **kwargs):
        description: str = dedent(
            """A Tier 3 chest which has chips in the range of thousands.
            Has a small chance of containing [Collectible]s."""
        )
        asset_url: str = "https://cdn.discordapp.com/attachments/" + \
            "874623706339618827/874628502924693584/legendary.png"
        emoji: str = "<:legendary:874626456918061096>"
        tier: int = 3
        super().__init__(
            description=description,
            asset_url=asset_url,
            emoji=emoji,
            tier=tier
        )

# endregion


# region Inherited Classes
@dataclass(eq=False)
class Gladiator(Consumable):
    """
    Minions that can fight in Gladiator matches.
    """
    def __init__(self, **kwargs):
        kwargs.pop('category', None)
        super().__init__(category="Gladiator", **kwargs)

    def rename(self, name: str):
        """Rename a :class:`Gladiator`.

        :param name: The new name of the :class:`Gladiator`.
        :type name: str
        """
        self.name = name
        self.update(name=name)


@dataclass(eq=False)
class Lootbag(Treasure):
    """
    Lootbags contain other items inside them.
    Premium Lootbags can also contain Premium Items.
    """
    def __init__(
        self, **kwargs
    ):
        super().__init__(
            category=kwargs.pop(
                "category",
                "Lootbag"
            ),
            **kwargs
        )

    @property
    def chips(self) -> int:
        """Return random amount of Pokechips in following ranges:

        .. note::
           * Normal => [100, 499]
           * Premium => [500, 1000]

        :return: An amount of Pokechips.
        :rtype: int
        """
        limits = [500, 1000] if self.premium else [100, 499]
        return random.randint(*limits)

    def get_random_items(
        self, categories: Optional[List[str]] = None,
        count: Optional[int] = 3
    ) -> List[Item]:
        """Get a random :class:`Item` from a list of categories.

        :param categories: A list of categories to choose from.
        :type categories: Optional[List[str]]
        :param count: The amount of items to choose., default is 3.
        :type count: Optional[int]
        :return: A list of items.
        :rtype: List[:class:`Item`]
        """
        pipeline = [
            {
                "$group": {
                    "_id": "$name",
                    "items": {
                        "$last": "$$ROOT"
                    }
                }
            },
            {
                "$group": {
                    "_id": "$items.category",
                    "items": {
                        "$push": "$items"
                    }
                }
            }
        ]
        matches = {
            "category": {
                "$nin": ["Chest", "Lootbag", "Rewardbox"]
            }
        }
        if categories:
            matches["category"] = {
                "$in": categories
            }
        if not self.premium:
            matches["premium"] = False
        if matches:
            pipeline.insert(0, {"$match": matches})
        results = list(self.mongo.aggregate(pipeline))
        random.shuffle(results)
        rand_items = []
        premium_added = False
        num_misses = 0
        while len(rand_items) <= count:
            for catog in results:
                try:
                    if self.premium and not premium_added:
                        itm_dict = random.choices(
                            catog["items"], k=1, weights=[
                                int(item["premium"])
                                for item in catog["items"]
                            ]
                        )[0]
                        premium_added = True
                    else:
                        itm_dict = random.choices(
                            catog["items"], k=1, weights=[
                                -int(item["premium"])
                                for item in catog["items"]
                            ]
                        )[0]
                    rand_items.append(itm_dict)
                    catog["items"].remove(itm_dict)
                except IndexError:
                    if num_misses < len(results):
                        num_misses += 1
                        continue
                    break
        return [
            Item.from_id(itm_dict["_id"])
            for itm_dict in rand_items
        ]


@dataclass(eq=False)
class Rewardbox(Treasure):
    """
    :class:`Lootbag` with fixed items and pokechips.
    """
    def __init__(
        self, chips: Optional[int] = None,
        items: Optional[List[int]] = None,
        **kwargs
    ):
        super().__init__(
            category=kwargs.pop(
                "category",
                "Rewardbox"
            ),
            **kwargs
        )
        self.items = items
        self.chips = chips
        self.attrs += ("chips", "items")

    @classmethod
    def get_items(cls, boxid: int) -> List[Item]:
        """Get items stored in a :class:`Rewardbox`.

        :param boxid: The itemid of the :class:`Rewardbox`.
        :type boxid: int
        :return: A list of stored items.
        :rtype: List[:class:`Item`]
        """
        return [
            Item.from_id(item, force_new=True)
            for item in Item.from_id(boxid).items
        ]

# endregion
