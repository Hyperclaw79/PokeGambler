"""
This module contains a compilation of data models.
"""

# pylint: disable=too-many-instance-attributes,too-many-arguments

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from inspect import ismethod
from typing import Dict, List, Tuple

import discord

from ..base.items import Item
from .dbconn import DBConnector


@dataclass
class Model(ABC):
    """
    The Base Model Class which has a corresponding table in the database.
    """
    def __init__(
        self, database: DBConnector,
        user: discord.User, model_name: str
    ) -> None:
        super().__init__()
        self.database = database
        self.user = user
        self.model_name = model_name

    def __iter__(self):
        for attr in dir(self):
            if all([
                not attr.startswith("_"),
                attr not in [
                    "database", "user",
                    "model_name"
                ],
                not ismethod(getattr(self, attr)),
                not isinstance(
                    getattr(self.__class__, attr, None),
                    (property, staticmethod, classmethod)
                )
            ]):
                yield (attr, getattr(self, attr))

    def get(self):
        """
        Returns the Model object as a dictionary.
        """
        return dict(self)

    def save(self):
        """
        Saves the Model object to the database.
        """
        self.database.save_model(self.model_name, **dict(self))


class UnlockedModel(Model, ABC):
    """
    The Base Unlocked Model class which can be modified after creation.
    """

    # pylint: disable=no-member

    def __init__(self, database, user):
        super().__init__(database, user, self.__class__.__name__.lower())
        existing = self.database.get_existing(
            self.model_name, str(self.user.id)
        )
        if not existing:
            self._default()
            self.save()
        else:
            for key, val in existing.items():
                setattr(self, key, val)

    @abstractmethod
    def _default(self):
        pass

    def update(self, **kwargs):
        """
        Updates an existing unfrozen model.
        """
        if not kwargs:
            return
        for key, val in kwargs.items():
            setattr(self, key, val)
        self.database.update_model(
            self.model_name, self.user_id, **kwargs
        )

    def reset(self):
        """
        Resets a model for a particular user.
        """
        self._default()
        kwargs = dict(self)
        kwargs.pop("user_id")
        self.database.update_model(self.model_name, str(self.user_id), **kwargs)


class Minigame(Model, ABC):
    """
    Base class for Minigames.
    """
    def get_plays(self, wins=False):
        """
        Returns list of minigames (of specified type) played.
        """
        method = getattr(
            self.database,
            f"get_{self.model_name}"
        )
        plays = method(str(self.user.id), wins=wins)
        if plays:
            return plays
        return []

    def get_lb(self):
        """
        Returns leaderboard for the specified minigame.
        """
        method = getattr(
            self.database,
            f"get_{self.model_name}_lb"
        )
        plays = method()
        if plays:
            return plays
        return []

    @property
    def num_plays(self):
        """
        Returns number of minigames (of specified type) played.
        """
        return len(self.get_plays())

    @property
    def num_wins(self):
        """
        Returns number of minigames (of specified type) won.
        """
        return len(self.get_plays(wins=True))


class Profile(UnlockedModel):
    """
    Wrapper for Profile based DB actions.
    """

    # pylint: disable=no-member

    def __init__(self, database, user):
        super().__init__(database, user)
        if all([
            "dealers" in [
                role.name.lower()
                for role in user.roles
            ],
            not self.is_dealer
        ]):
            self.update(is_dealer=True)
        elif all([
            "dealers" not in [
                role.name.lower()
                for role in user.roles
            ],
            self.is_dealer
        ]):
            self.update(is_dealer=False)

    def _default(self):
        init_dict = {
            "user_id": str(self.user.id),
            "name": self.user.name,
            "balance": 100,
            "num_matches": 0,
            "num_wins": 0,
            "purchased_chips": 0,
            "won_chips": 100,
            "is_dealer": "dealers" in [
                role.name.lower()
                for role in self.user.roles
            ]
        }
        for key, val in init_dict.items():
            setattr(self, key, val)

    def get_badges(self):
        """
        Computes the Badges unlocked by the user.
        """
        badges = []
        if self.database.is_champion(str(self.user.id)):
            badges.append("champion")
        if self.database.is_emperor(str(self.user.id)):
            badges.append("emperor")
        if self.database.is_top_funder(str(self.user.id)):
            badges.append("funder")
        if self.is_dealer:
            badges.append("dealer")
        return badges

    def debit(self, amount: int):
        """
        Shorthand method to subtract from balance and won_chips.
        """
        self.update(
            balance=self.balance - amount,
            won_chips=self.won_chips - amount
        )

    def credit(self, amount: int):
        """
        Shorthand method to add to balance and won_chips.
        """
        self.update(
            balance=self.balance + amount,
            won_chips=self.won_chips + amount
        )

    @classmethod
    def get_all(
        cls, database: DBConnector,
        ids_only: bool = False
    ) -> List[Dict]:
        """
        Wrapper for the DB query to get all whitelist profiles.
        """
        return database.get_all_profiles(ids_only)

    @property
    def full_info(self):
        """
        Wrapper for Get Full Profile DB call.
        """
        return self.database.get_full_profile(self.user.id)


class CommandData(Model):
    """
    Wrapper for command based DB actions
    """

    # pylint: disable=no-member

    def __init__(
        self, database, user, message,
        command, args, kwargs
    ):
        super().__init__(database, user, "commands")
        self.user_id = str(user.id)
        self.user_is_admin = "admins" in [
            role.name.lower()
            for role in self.user.roles
        ]
        self.used_at = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.channel = str(message.channel.id)
        self.guild = str(message.guild.id)
        self.command = command
        self.args = args
        self.kwargs = kwargs


class Blacklist(Model):
    """
    Wrapper for blacklisted users based DB actions
    """

    # pylint: disable=no-member

    def __init__(
        self, database, user, mod, reason: str = ""
    ):
        super().__init__(database, user, "blacklists")
        self.user_id = str(user.id)
        self.blacklisted_at = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.blacklisted_by = str(mod.id)
        self.reason = reason

    def save(self):
        """
        Saves the blacklisted user in the table.
        Also resets their profile.
        """
        Profile(self.database, self.user).reset()
        super().save()

    def pardon(self):
        """
        Pardons a blacklisted user.
        """
        self.database.pardon_user(self.user_id)


class Matches(Model):
    """
    Wrapper for matches based DB actions
    """

    # pylint: disable=no-member

    def __init__(
        self, database, user,
        started_by: str = "",
        participants: List[str] = None,
        winner: str = "", deal_cost: int = 50,
        lower_wins: bool = False,
        by_joker: bool = False
    ):
        super().__init__(database, user, "matches")
        self.played_at = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.started_by = started_by
        self.participants = participants
        self.winner = winner
        self.deal_cost = deal_cost
        self.lower_wins = lower_wins
        self.by_joker = by_joker

    @property
    def num_matches(self):
        """
        Returns number of gamble matches played.
        """
        items = self.database.get_match_stats(str(self.user.id)) or []
        return len(items)

    @property
    def num_wins(self):
        """
        Returns number of gamble matches won.
        """
        items = self.database.get_match_stats(str(self.user.id)) or []
        return items.count(True)

    def get_stats(self) -> Tuple[int, int]:
        """
        Get Match num_matches and num_wins with a single query.
        """
        items = self.database.get_match_stats(str(self.user.id)) or []
        matches = len(items)
        wins = items.count(True)
        return (matches, wins)


class Inventory(Model):
    """
    Wrapper for Inventory based DB operations.
    """
    def __init__(
        self, database: DBConnector, user: discord.User
    ) -> None:
        super().__init__(database, user, "inventory")
        self.user_id = str(self.user.id)

    # pylint: disable=arguments-differ
    def get(self, counts_only=False) -> Tuple[Dict[str, List], int]:
        """
        Returns a list of items in user's Inventory.
        """
        items = self.database.get_inventory_items(
            self.user_id, counts_only
        )
        if not items:
            return ({}, 0)
        net_worth = 0
        item_dict = {}
        for item in items:
            category = item.pop("category")
            if category not in item_dict:
                item_dict[category] = []
            item_dict[category].append(item)
            net_worth += item.pop('Net Worth')
        return item_dict, net_worth

    def get_ids(self, name: str) -> List:
        """
        Returns a list of ItemIDs if they exist in user's Inventory.
        """
        itemids = self.database.get_inv_ids(
            self.user_id, name
        )
        if not itemids:
            return None
        return [
            f'{itemid:0>8X}'
            for itemid in itemids
        ]

    # pylint: disable=arguments-differ, no-member
    def save(self, itemid: int):
        """
        Saves an item in a player's inventory.
        """
        item = self.database.item_in_inv(itemid)
        if item:
            for attr in ('user_id', 'itemid'):
                item.pop(attr)
            name = item.pop('name')
            cls_name = ''.join(name.split(' '))
            category = Item.get_category(item)
            new_item = type(
                cls_name,
                (category, ),
                item
            )(**item)
            new_item.save(self.database)
            itemid = int(new_item.itemid, 16)
        self.database.save_model(
            self.model_name,
            user_id=self.user_id,
            itemid=itemid,
            obtained_on=datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

    def destroy(self):
        """
        Wrapper for clean_inv DB query.
        Completely resets a user's inventory.
        """
        self.database.clear_inv(self.user_id)


class Loots(UnlockedModel):
    """
    Wrapper for Loots based DB actions.
    """
    def _default(self):
        self.user_id: str = str(self.user.id)
        self.tier: int = 1
        self.loot_boost: int = 1
        self.treasure_boost: int = 1
        self.earned: int = 0
        self.daily_claimed_on: str = (
            datetime.now() - timedelta(days=1)
        ).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.daily_streak: int = 0


class Flips(Minigame):
    """
    Wrapper for flips based DB actions
    """

    # pylint: disable=no-member

    def __init__(
        self, database, user,
        cost: int = 50, won: bool = False
    ):
        super().__init__(database, user, "flips")
        self.played_at = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.played_by = str(user.id)
        self.cost = cost
        self.won = won


class Moles(Minigame):
    """
    Wrapper for moles based DB actions
    """

    # pylint: disable=no-member

    def __init__(
        self, database, user,
        cost: int = 50, level: int = 1,
        won: bool = False
    ):
        super().__init__(database, user, "moles")
        self.played_at = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.played_by = str(user.id)
        self.cost = cost
        self.level = level
        self.won = won
