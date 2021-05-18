"""
This module contains a compilation of data models.
"""

# pylint: disable=too-many-instance-attributes,too-many-arguments

from abc import ABC
from dataclasses import dataclass
from datetime import datetime
from inspect import ismethod
from typing import List, Tuple

import discord

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

    def save(self):
        """
        Saves the Model object to the database.
        """
        self.database.save_model(self.model_name, **dict(self))

    def get(self):
        """
        Returns the Model object as a dictionary.
        """
        return dict(self)


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


class Profile(Model):
    """
    Wrapper for Profile based DB actions.
    """

    # pylint: disable=no-member

    def __init__(self, database, user):
        super().__init__(database, user, "profile")
        profile = self.database.get_profile(str(user.id))
        if not profile:
            self.__create()
        else:
            for key, val in profile.items():
                setattr(self, key, val)
            if all([
                "dealers" in [
                    role.name.lower()
                    for role in user.roles
                ],
                not profile["is_dealer"]
            ]):
                self.update(is_dealer=True)
            elif all([
                "dealers" not in [
                    role.name.lower()
                    for role in user.roles
                ],
                profile["is_dealer"]
            ]):
                self.update(is_dealer=False)

    def __init_dict(self):
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

    def __create(self):
        self.__init_dict()
        self.save()

    def update(self, **kwargs):
        """
        Updates an existing user profile.
        """
        if not kwargs:
            return
        for key, val in kwargs.items():
            setattr(self, key, val)
        self.database.update_profile(self.user_id, **kwargs)

    def reset(self):
        """
        Resets a user's profile to the default values.
        """
        self.__init_dict()
        kwargs = dict(self)
        kwargs.pop("user_id")
        self.database.update_profile(str(self.user_id), **kwargs)

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
        results = self.database.get_match_stats(str(self.user.id)) or []
        return len(results)

    @property
    def num_wins(self):
        """
        Returns number of gamble matches won.
        """
        results = self.database.get_match_stats(str(self.user.id)) or []
        return results.count(True)

    def get_stats(self) -> Tuple[int, int]:
        """
        Get Match num_matches and num_wins with a single query.
        """
        results = self.database.get_match_stats(str(self.user.id)) or []
        matches = len(results)
        wins = results.count(True)
        return (matches, wins)


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
