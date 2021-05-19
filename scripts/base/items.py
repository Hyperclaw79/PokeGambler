"""
This module contains all the items in the Pokegambler world.
"""

# pylint: disable=no-member

import random
import re
from abc import ABC
from dataclasses import dataclass
from functools import total_ordering
from inspect import ismethod
from typing import Dict, Optional, Tuple, Union

from scripts.base.dbconn import DBConnector

from ..helpers.utils import dedent

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

    def __iter__(self) -> Tuple:
        for attr in (
            "name", "description", "category",
            "asset_url", "emoji", "buyable",
            "sellable", "price"
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
        uid = self.itemid
        database.delete_item(uid)

    @classmethod
    def get(
        cls, database: DBConnector, itemid: int
    ) -> Union[Dict, None]:
        """
        Get an Item with an ID as a dictionary.
        Returns None if item not in the DB.
        """
        return database.get_item(itemid)

    @property
    def name(self) -> str:
        """
        Returns the name of the Item.
        """
        return str(self)


class Treasure(Item, ABC):
    """
    Any non-buyable [Item] is considered a Treasure.
    It is unique to the user and cannot be sold either.
    """
    def __init__(
        self, description: str,
        asset_url: str, emoji: str
    ):
        super().__init__(
            description=description,
            category="Treasure",
            asset_url=asset_url,
            emoji=emoji
        )
        self.buyable: bool = False
        self.sellable: bool = False


class Tradable(Item, ABC):
    """
    Any sellable [Item] is a Tradeable.
    It should have a fixed base price.
    Tradables can be bought.
    """
    def __init__(
        self, description: str,
        asset_url: str, emoji: str,
        price: int
    ):
        super().__init__(
            description=description,
            category="Tradable",
            asset_url=asset_url,
            emoji=emoji
        )
        self.price: int = price


class Collectible(Item, ABC):
    """
    Collectibles are sellable variants of [Treasure].
    They cannot be bought off the market but can be traded among users.
    """
    def __init__(
        self, description: str,
        asset_url: str, emoji: str,
    ):
        super().__init__(
            description=description,
            category="Collectible",
            asset_url=asset_url,
            emoji=emoji
        )
        self.buyable: bool = False

#endregion

# region Chests

@total_ordering
class Chest(Treasure):
    """
    Chests are spawnable [Treasure] which usually contain Pokechips based on tiers.
    """
    def __init__(
        self, description: str,
        asset_url: str, emoji: str,
        tier: int = 1
    ):
        super().__init__(
            description=description,
            asset_url=asset_url,
            emoji=emoji
        )
        self.category = "Chest"
        self.tier: int = tier

    def __eq__(self, other):
        return self.chips == other.chips

    def __ge__(self, other):
        return self.chips >= other.chips

    @property
    def chips(self):
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
    def get_chest(cls, tier: int):
        """
        Get a specified tier Chest.
        """
        chests = [CommonChest, GoldChest, LegendaryChest]
        return chests[tier - 1]()

    @classmethod
    def get_random_chest(cls):
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

    @classmethod
    def from_id(cls, database: DBConnector, itemid: int):
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


class CommonChest(Chest):
    """
    Lowest Tier [Chest].
    Chips scale in 100s.
    """
    def __init__(self):
        description: str = dedent(
            """This is a Tier 1 chest which contains gold in the range of a few hundreds.
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
    def __init__(self):
        description: str = dedent(
            """This is a Tier 2 chest which contains gold in the range of
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
    def __init__(self):
        description: str = dedent(
            """This is a Tier 3 chest which contains gold in the range of thousands.
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

    @classmethod
    def get_random_collectible(cls, chance: float = 0.1):
        """
        Get a random collectible with a specified chance.
        Defaults to 10%.
        """
        proc = random.uniform(0.1, 0.99)
        if proc >= chance:
            return None
        return random.choice(Collectible.__subclasses__())[0]()

#endregion
