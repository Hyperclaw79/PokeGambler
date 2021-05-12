"""
This module contains a compilation of data models.
"""

# pylint: disable=too-many-instance-attributes,too-many-arguments

from abc import ABC
from dataclasses import dataclass
from datetime import datetime
from inspect import ismethod

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
                    "model_name", "objects"
                ],
                not ismethod(getattr(self, attr))
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

    def __init_dict(self):
        init_dict = {
            "user_id": str(self.user.id),
            "name": self.user.name,
            "balance": 100,
            "num_matches": 0,
            "num_wins": 0,
            "purchased_chips": 100,
            "won_chips": 0,
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
