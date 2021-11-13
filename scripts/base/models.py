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

This module contains a compilation of data models.
"""

# pylint: disable=too-many-instance-attributes, too-many-arguments
# pylint: disable=unused-argument, too-many-lines, no-member

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
from inspect import ismethod
import os
from typing import (
    Any, Callable, Dict, List,
    Optional, Tuple, Type, Union
)

import discord

from ..base.items import Item, DB_CLIENT  # pylint: disable=cyclic-import


def expire_cache(func: Callable):
    """Decorator to reset User cache.

    :param func: Function which requires cache to be cleared.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        """
        Wrapper function.
        """
        # pylint: disable=import-outside-toplevel, cyclic-import
        from ..commands.basecommand import Commands

        Commands.expire_cache(self.user.id)
        return func(self, *args, **kwargs)
    return wrapper


def to_dict(
    dc_obj: Union[
        discord.User, discord.Guild,
        discord.TextChannel
    ]
) -> Dict[str, Any]:
    """Convert a Discord object into a Dictionary.

    .. note::
        Currently only supports User, Guild, and TextChannel.

    :param dc_obj: Discord object to be converted.
    :type dc_obj: Union[discord.User, discord.Guild, discord.TextChannel]
    :return: Dictionary of Discord object.
    :rtype: Dict[str, Any]
    """
    fields = [
        'name', 'id', 'created_at'
    ]
    if isinstance(dc_obj, discord.Guild):
        fields.extend(['owner', 'large'])
    obj_dict = {
        attr: getattr(dc_obj, attr, None)
        for attr in fields
    }
    if isinstance(dc_obj, discord.Guild):
        obj_dict['owner'] = to_dict(obj_dict['owner'])
    return obj_dict


class NameSetter(type):
    """
    Metaclass to set the mongo collection for the model.
    Useful for DB actions in Classmethods.

    :meta private:
    """
    def __new__(cls, name, bases, dct):
        new_cl = super().__new__(
            cls, name, bases, dct
        )
        new_cl.model_name = new_cl.__name__.lower()
        new_cl.mongo = DB_CLIENT[new_cl.model_name]
        new_cl.no_uinfo = dct.get('no_uinfo', False)
        return new_cl


@dataclass
class Model(metaclass=NameSetter):
    """The Base Model Class which has a corresponding Collection in the DB.

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    """

    def __init__(
        self, user: discord.Member,
        *args, **kwargs
    ) -> None:
        self.user = user

    def __iter__(self):
        for attr in dir(self):
            # Patch for Full_Info being executed before Profile creation.
            if attr in getattr(self, "excludes", []):
                continue
            if attr == 'user' and self.no_uinfo:
                continue
            if all([
                not attr.startswith("_"),
                attr not in [
                    "model_name", "mongo",
                    "excludes", "no_uinfo"
                ],
                not ismethod(getattr(self, attr)),
                not isinstance(
                    getattr(self.__class__, attr, None),
                    (property, staticmethod, classmethod)
                )
            ]):
                res = getattr(self, attr)
                if attr == 'user':
                    attr = 'user_info'
                    res = to_dict(res)
                    res.pop('id')
                yield (attr, res)

    def drop(self):
        """
        Deletes all entries in the Collection for the user.
        """
        self.mongo.delete_many({
            "$or": [
                {"user_id": str(self.user.id)},
                {"played_by": str(self.user.id)}
            ]
        })

    def get(self, param=None) -> Any:
        """Returns the Model object as a dictionary.

        :param param: The attribute to get from the Model.
        :type param: str
        :return: The attribute value.
        :rtype: Any
        """
        if not param:
            return dict(self)
        return dict(self).get(param)

    def save(self):
        """
        Saves the Model object to the Collection.
        """
        self.mongo.insert_one(dict(self))

    @classmethod
    def latest(
        cls: Type[Model],
        limit: Optional[int] = 5
    ) -> List[Dict]:
        """Returns the latest douments from the DB for a model.

        :param limit: The number of documents to return., default 5
        :type limit: Optional[int]
        :return: The documents from the DB.
        :rtype: List[Dict]
        """
        return list(
            cls.mongo.aggregate([
                {"$sort": {"_id": -1}},
                {"$limit": limit},
                {"$unset": "_id"}
            ])
        )

    @classmethod
    def purge(cls):
        """
        Deletes all entries in the Collection.
        """
        cls.mongo.delete_many({})


# region Models

class Blacklist(Model):
    """Wrapper for blacklisted users based DB actions.

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    :param mod: The Admin who used the command.
    :type mod: Optional[:class:`discord.Member`]
    :param reason: The reason for the blacklist.
    :type reason: Optional[str]
    """

    def __init__(
        self, user: discord.Member,
        mod: Optional[discord.Member] = None,
        reason: Optional[str] = ""
    ):
        super().__init__(user)
        self.user_id = str(user.id)
        self.blacklisted_at = datetime.now()
        self.blacklisted_by = to_dict(mod) if mod else None
        self.reason = reason

    @expire_cache
    def pardon(self):
        """
        Pardons a blacklisted user.
        """
        self.mongo.delete_one({"user_id": self.user_id})

    # pylint: disable=invalid-overridden-method
    async def save(self):
        """
        Saves the blacklisted user in the table.
        Also resets their profile.
        """
        # pylint: disable=import-outside-toplevel, cyclic-import
        from .shop import Shop, PremiumShop

        super().save()
        Profiles(self.user).reset()
        Inventory(self.user).drop()
        Boosts(self.user).reset()
        Loots(self.user).reset()
        for cls in Minigame.__subclasses__():
            cls(self.user).drop()
        titles = [
            title.name
            for shop in [Shop, PremiumShop]
            for title in shop.categories["Titles"].items
        ]
        need_to_remove = [
            role
            for role in self.user.roles
            if role.name.title() in titles
        ]
        if need_to_remove:
            await self.user.remove_roles(
                *need_to_remove,
                reason="Blacklisted"
            )
            await self.user.edit(
                nick=None,
                reason="Blacklisted"
            )

    @classmethod
    def is_blacklisted(
        cls: Type[Blacklist],
        user_id: str
    ) -> bool:
        """Checks if a user is blacklisted.

        :param user_id: The ID of the user to check.
        :type user_id: str
        :return: True if blacklisted, False otherwise.
        :rtype: bool
        """
        return cls.mongo.find_one({"user_id": user_id})


class CommandData(Model):
    """Wrapper for command based DB actions

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    :param message: The message which triggered the command.
    :type message: discord.Message
    :param is_interaction: Whether the command is an interaction.
    :type is_interaction: bool
    :param command: The command which was triggered.
    :type command: str
    :param args: The arguments passed to the command.
    :type args: List[str]
    :param kwargs: The keyword arguments passed to the command.
    :type kwargs: Dict[str, Any]
    """

    def __init__(
        self, user: discord.Member,
        message: discord.Message,
        is_interaction: bool,
        command: str, admin_cmd: bool,
        args: List, kwargs: Dict
    ):
        super().__init__(user)
        self.user_id = str(user.id)
        self.admin_cmd = admin_cmd
        self.used_at = datetime.now()
        self.is_interaction = is_interaction
        self.channel = to_dict(message.channel)
        self.guild = to_dict(message.guild)
        self.command = command
        self.args = args
        self.kwargs = kwargs

    @classmethod
    def history(cls, limit: Optional[int] = 5, **kwargs) -> List[Dict]:
        """Returns the list of commands used on PG till now.

        :param limit: The number of documents to return., default 5
        :type limit: Optional[int]
        :return: The recorded commands from the DB.
        :rtype: List[Dict]
        """
        return list(cls.mongo.find().limit(limit))

    @classmethod
    def most_active_channel(cls) -> Dict:
        """Returns the most active channel.

        :return: The most active channel.
        :rtype: Dict
        """
        return next(
            cls.mongo.aggregate([
                {
                    '$match': {
                        'used_at': {
                            '$gte': datetime.today() - timedelta(
                                weeks=1
                            )
                        },
                        'admin_cmd': False
                    }
                }, {
                    '$group': {
                        '_id': '$channel.id',
                        'name': {'$last': '$channel.name'},
                        'num_cmds': {'$sum': 1},
                        'guild': {'$first': '$guild'}
                    }
                }, {
                    '$sort': {'num_cmds': -1}
                }, {
                    '$limit': 1
                }, {
                    '$match': {'num_cmds': {'$gt': 1}}
                }
            ]),
            None
        )

    @classmethod
    def most_used_command(cls) -> Dict:
        """Returns the most used command.

        :return: The most used command.
        :rtype: Dict
        """
        return next(
            cls.mongo.aggregate([
                {
                    '$match': {
                        'used_at': {
                            '$gte': datetime.today() - timedelta(
                                weeks=1
                            )
                        },
                        'admin_cmd': False
                    }
                }, {
                    '$group': {
                        '_id': '$command',
                        'num_cmds': {'$sum': 1}
                    }
                }, {
                    '$sort': {'num_cmds': -1}
                }, {
                    '$limit': 1
                }, {
                    '$match': {'num_cmds': {'$gt': 1}}
                }
            ]),
            None
        )

    @classmethod
    def most_active_user(cls) -> Dict:
        """Returns the most active user.

        :return: The most active user.
        :rtype: Dict
        """
        return next(
            cls.mongo.aggregate([
                {
                    '$match': {
                        'used_at': {
                            '$gte': datetime.today() - timedelta(
                                weeks=1
                            )
                        },
                        'admin_cmd': False
                    }
                }, {
                    '$group': {
                        '_id': '$user_id',
                        'num_cmds': {'$sum': 1}
                    }
                }, {
                    '$sort': {'num_cmds': -1}
                }, {
                    '$limit': 1
                }, {
                    '$match': {'num_cmds': {'$gt': 1}}
                }
            ]),
            None
        )

    @classmethod
    def num_user_cmds(cls, user_id: str) -> int:
        """Returns the number of commands used by a user.

        :param user_id: The ID of the user.
        :type user_id: str
        :return: The number of commands used by the user.
        :rtype: int
        """
        return cls.mongo.find({
            "user_id": user_id
        }).count()


class DuelActionsModel(Model):
    """
    Wrapper for duel actions based DB actions

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    :param action: An action which can be used in a duel.
    :type action: Optional[str]
    :param level: The level of the action.
    :type level: Optional[str]
    """

    def __init__(
        self, user: discord.Member,
        action: Optional[str] = None,
        level: Optional[str] = None
    ):
        super().__init__(user)
        self.created_at = datetime.now()
        self.created_by = str(user.id)
        self.action = action
        self.level = level

    # pylint: disable=inconsistent-return-statements
    @classmethod
    def get_actions(
        cls: Type[DuelActionsModel],
        user_id: Optional[str] = None
    ) -> List[Dict]:
        """Get Duel Actions from the DB.

        :param user_id: An optional user_id to get the actions for.
        :type user_id: Optional[str]
        :return: The list of duel actions.
        :rtype: List[Dict]
        """
        filter_ = {}
        if user_id:
            filter_.update({"user_id": user_id})
        if not cls.mongo.count(filter_):
            return None
        results = cls.mongo.find(filter_)
        yield from results


class Exchanges(Model):
    """Wrapper for currency exchanges based DB actions.

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    :param admin: The Admin who performed the exchange.
    :type admin: Optional[:class:`discord.Member`]
    :param pokebot: The Pokemon themed bot.
    :type pokebot: Optional[:class:`discord.Member`]
    :param chips: The amount of chips exchanged.
    :type chips: Optional[int]
    :param mode: The mode of the exchange., default is Deposit.
    :type mode: Optional[str]
    """

    def __init__(
        self, user: discord.Member,
        admin: Optional[discord.Member] = None,
        pokebot: Optional[discord.Member] = None,
        chips: Optional[int] = None,
        mode: Optional[str] = None
    ):
        super().__init__(user)
        self.exchanged_at = datetime.now()
        self.user_id = str(user.id)
        self.admin = admin
        self.pokebot = pokebot
        self.chips = chips
        self.mode = mode

    def get_daily_exchanges(self, mode: str) -> int:
        """Gets the list of exchanges made by the user today.

        :param mode: The mode of the exchange.
        :type mode: str
        :return: The number of chips exchanged.
        :rtype: int
        """
        pipeline = [
            {
                "$match": {
                    "user_id": str(self.user.id),
                    "exchanged_at": {
                        "$gt": datetime.now().replace(
                            hour=0,
                            minute=0,
                            second=0
                        )
                    },
                    "mode": mode
                }
            },
            {
                "$group": {
                    "_id": "$user_id",
                    "total_chips": {"$sum": "$chips"}
                }
            }
        ]
        result = next(
            self.mongo.aggregate(pipeline),
            None
        )
        if result:
            return result["total_chips"]
        return 0

    @classmethod
    def exchanges(cls, **kwargs) -> List[Dict]:
        """Find all completed exchanges based on the provided filters.

        :param kwargs: The filters to use in the query.
        :type kwargs: Dict
        :return: The list of completed exchanges.
        :rtype: List[Dict]
        """
        yield from cls.mongo.find(kwargs)


class Inventory(Model):
    """Wrapper for Inventory based DB operations.

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    """

    # pylint: disable=arguments-differ

    def __init__(
        self, user: discord.Member
    ) -> None:
        super().__init__(user)
        self.user_id = str(self.user.id)

    def delete(
        self, item_inp: Union[str, List[str]],
        quantity: int = -1,
        is_name: bool = False
    ) -> int:
        """Deletes an Item from user's Inventory.
        Input can either be a name or List of itemids.
        If item name is given, a quantity can be provided.
        If quantity is -1, all items of the name will be removed.

        :param item_inp: The name or list of item ids to delete.
        :type item_inp: Union[str, List[str]]
        :param quantity: The quantity of items to delete., default is -1.
        :type quantity: int
        :param is_name: Whether the input is a name or list of item ids.
        :type is_name: bool
        :return: The number of items deleted.
        :rtype: int
        """
        ids = self.from_name(item_inp) if is_name else [item_inp]
        if is_name:
            ids = self.from_name(item_inp)
        elif isinstance(item_inp, list):
            ids = item_inp
        else:
            ids = [item_inp]
        if quantity > 0:
            ids = ids[:quantity]
        res = self.mongo.delete_many({
            "user_id": self.user_id,
            "itemid": {
                "$in": ids
            }
        })
        return res.deleted_count

    def from_id(self, itemid: str) -> Item:
        """Gets an item using ItemID if it exists in user's inventory.

        :param itemid: The ItemID of the item.
        :type itemid: str
        :return: The Item object.
        :rtype: :class:`~.items.Item`
        """
        item = self.mongo.find_one({
            "user_id": self.user_id,
            "itemid": itemid
        })
        if item:
            return Item.from_id(itemid)
        return None

    def from_name(self, name: str) -> List[str]:
        """Returns a list of ItemIDs if they exist in user's Inventory.

        :param name: The name of the item.
        :type name: str
        :return: The list of ItemIDs.
        :rtype: List[str]
        """
        items = self.mongo.aggregate([
            {
                "$match": {"user_id": self.user_id}
            },
            {
                "$lookup": {
                    "from": "items",
                    "localField": "itemid",
                    "foreignField": "_id",
                    "as": "items"
                }
            },
            {
                "$match": {
                    "items.name": {
                        "$regex": f"^{name}",
                        "$options": "i"
                    }
                }
            },
            {
                "$unwind": "$items"
            },
            {
                "$group": {
                    "_id": "$items.name",
                    "items": {
                        "$push": "$items"
                    }
                }
            },
            {
                "$unwind": "$items"
            },
            {
                "$replaceRoot": {"newRoot": "$items"}
            },
            {
                "$set": {
                    "itemid": "$_id"
                }
            },
            {"$unset": "_id"}
        ])
        items = list(items)
        return [
            item["itemid"]
            for item in items
        ]

    # pylint: disable=arguments-renamed
    def get(
        self, category: Optional[str] = None
    ) -> Tuple[Dict[str, List], int]:
        """Returns a list of items in user's Inventory and the net worth.

        .. note:: These items are not included for calculating the net worth:

            * :class:`~.items.Chest`
            * :class:`~.items.Lootbag`
            * :class:`~.items.Rewardbox`

        :param category: The category to filter by.
        :type category: Optional[str]
        :return: The list of items and the net worth of the inventory.
        :rtype: Tuple[Dict[str, List], int]
        """
        pipeline = [
            {
                "$match": {"user_id": self.user_id}
            },
            {
                "$lookup": {
                    "from": "items",
                    "localField": "itemid",
                    "foreignField": "_id",
                    "as": "items"
                }
            },
            {
                "$unwind": "$items"
            },
            {
                "$group": {
                    "_id": "$items.category",
                    "items": {
                        "$push": "$items"
                    },
                    "net_worth": {"$sum": "$items.price"}
                }
            },
            {
                "$set": {
                    "category": "$_id"
                }
            },
            {"$unset": "_id"}
        ]
        if category:
            pipeline.insert(2, {
                "$match": {
                    "items.category": category
                }
            })
        categories = self.mongo.aggregate(pipeline)
        net_worth = 0
        item_dict = {}
        for catog in categories:
            category = catog.pop("category")
            if category not in item_dict:
                item_dict[category] = []
            item_dict[category].extend(catog["items"])
            net_worth += catog.pop('net_worth')
        return item_dict, net_worth

    def save(self, itemid: str):
        """Saves an item to a player's inventory.

        :param itemid: The ItemID of the item.
        :type itemid: str
        """
        item = self.from_id(itemid)
        if item:
            new_item = Item.from_id(itemid, force_new=True)
            new_item.save()
            itemid = new_item.itemid
        self.mongo.insert_one({
            "user_id": self.user_id,
            "user": to_dict(self.user),
            "itemid": itemid,
            "obtained_on": datetime.now()
        })


class Minigame(Model):
    """
    Base class for Minigames.
    """

    # pylint: disable=no-self-use

    @property
    def num_plays(self) -> int:
        """Returns number of minigames (of specified type) played.

        :return: Number of minigames played.
        :rtype: int
        """
        return len(self.get_plays())

    @property
    def num_wins(self):
        """Returns number of minigames (of specified type) won.

        :return: Number of minigames won.
        :rtype: int
        """
        return len(self.get_plays(wins=True))

    def get_lb(self) -> List[Dict]:
        """Returns leaderboard for the specified minigame.

        :return: The leaderboard for the minigame.
        :rtype: List[Dict]
        """
        return list(self.mongo.aggregate([
            {
                "$group": self._get_lb_group()
            },
            {
                "$match": {
                    "num_wins": {"$gte": 1}
                }
            },
            {
                "$addFields": {
                    "earned": {
                        "$toInt": {"$multiply": [
                            "$num_wins", {
                                "$divide": [
                                    "$cumm_cost", "$num_matches"
                                ]
                            }
                        ]}
                    }
                }
            },
            {"$sort": self._get_lb_sort()},
            {"$limit": 20}
        ]))

    def get_plays(self, wins: bool = False) -> List[Dict]:
        """Returns list of minigames (of specified type) played.

        :param wins: Whether to include only wins or all plays.
        :type wins: bool
        :return: List of minigames played.
        :rtype: List[Dict]
        """
        filter_ = {
            "played_by": str(self.user.id)
        }
        if wins:
            filter_.update({"won": True})
        return list(self.mongo.aggregate([
            {
                "$match": filter_
            }
        ]))

    @expire_cache
    def save(self):
        super().save()

    def _get_lb_group(self):
        return {
            "_id": "$played_by",
            "num_wins": {
                "$sum": {
                    "$toInt": "$won"
                }
            },
            "num_matches": {"$sum": 1},
            "cumm_cost": {"$sum": "$cost"}
        }

    def _get_lb_sort(self) -> Dict[str, Any]:
        """
        Override it for each Minigame.
        """
        return {
            "num_wins": -1,
            "earned": -1
        }


class Matches(Model):
    """Wrapper for Gamble matches based DB actions

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    :param started_by: The user who started the match.
    :type started_by: Optional[:class:`discord.Member`]
    :param participants: The list of participants.
    :type participants: Optional[List[:class:`discord.Member`]]
    :param winner: The user who won.
    :type winner: :class:`discord.Member`
    :param deal_cost: The fee of the gamble match., deafult is 50.
    :type deal_cost: int
    :param lower_wins: Was the lower_wins rule in place?
    :type lower_wins: bool
    :param by_joker: Did the match end due to a joker?
    :type by_joker: bool
    """

    no_uinfo = True

    def __init__(
        self, user: discord.Member,
        started_by: Optional[discord.Member] = None,
        participants: Optional[List[discord.Member]] = None,
        winner: Optional[discord.Member] = None,
        deal_cost: int = 50,
        lower_wins: bool = False,
        by_joker: bool = False
    ):
        super().__init__(user)
        self.played_at = datetime.now()
        self.started_by = to_dict(started_by)
        self.participants = [
            to_dict(user)
            for user in participants
        ] if participants else None
        self.winner = to_dict(winner)
        self.deal_cost = deal_cost
        self.lower_wins = lower_wins
        self.by_joker = by_joker

    @property
    def num_matches(self) -> int:
        """Returns number of gamble matches played.

        :return: Number of matches played.
        :rtype: int
        """
        return self.mongo.find({
            "$or": [
                {
                    "played_by": str(self.user.id)
                },
                {
                    "participants.id": self.user.id
                }
            ]
        }).count()

    @property
    def num_wins(self) -> int:
        """Returns number of gamble matches won.

        :return: Number of matches won.
        :rtype: int
        """
        return self.mongo.find({
            "winner.id": self.user.id
        }).count()

    def get_stats(self) -> Tuple[int, int]:
        """Get Match :meth:`num_matches` and :meth:`num_wins` as a Tuple.

        :return: Tuple of num_matches and num_wins.
        :rtype: Tuple[int, int]
        """
        return (self.num_matches, self.num_wins)

    @classmethod
    def get_matches(
        cls: Type[Matches],
        limit: Optional[int] = 10
    ) -> List[Dict]:
        """Get the recently played gamble matches.

        :param limit: The maximum number of matches to return., default 10
        :type limit: Optional[int]
        :return: List of recent matches.
        :rtype: List[Dict]
        """
        pipeline = [
            {"$sort": {"played_at": -1}},
            {"$limit": limit}
        ]
        return list(cls.mongo.aggregate(pipeline))


class Nitro(Model):
    """Wrapper for Nitro Reward records.

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    :param boosters: The list of the nitro boosters.
    :type boosters: List[:class:`discord.Member`]
    :param rewardboxes: The list of IDs of nitro reward boxes.
    :type rewardboxes: List[str]
    """

    no_uinfo = True

    def __init__(
        self, user: discord.Member,
        boosters: List[discord.Member] = None,
        rewardboxes: List[str] = None
    ):
        super().__init__(user)
        self.last_rewarded = datetime.now()
        self.boosters = [
            to_dict(user)
            for user in boosters
        ] if boosters else None
        self.rewardboxes = rewardboxes

    @classmethod
    def get_last_rewarded(cls) -> datetime:
        """Returns the last time the users were rewarded.

        :return: Last time the users were rewarded.
        """
        pipeline = [
            {"$sort": {"last_rewarded": -1}},
            {"$limit": 1}
        ]
        return next(
            cls.mongo.aggregate(pipeline),
            {'last_rewarded': datetime.utcnow() - timedelta(days=31)}
        )['last_rewarded']


class Trades(Model):
    """Wrapper for trades based DB actions.

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    :param traded_to: The user with whom the trade happened.
    :type traded_to: :class:`discord.Member`
    :param given_chips: The number of pokechips given to user.
    :type given_chips: int
    :param taken_chips: The number of pokechips taken from user.
    :type taken_chips: int
    :param given_items: The list of items given to user.
    :type given_items: List[str]
    :param taken_items: The list of items taken from user.
    :type taken_items: List[str]
    """

    def __init__(
        self, user: discord.Member,
        traded_to: Optional[discord.Member] = None,
        given_chips: int = None,
        taken_chips: int = None,
        given_items: List[str] = None,
        taken_items: List[str] = None
    ):
        super().__init__(user)
        self.traded_at = datetime.now()
        self.traded_by = str(user.id)
        self.traded_to = traded_to
        self.given_chips = given_chips
        self.taken_chips = taken_chips
        self.given_items = given_items
        self.taken_items = taken_items


class UnlockedModel(Model):
    """The Base Unlocked Model class which can be modified after creation.

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    """

    def __init__(self, user: discord.Member):
        super().__init__(user)
        existing = self.mongo.find_one(
            {"user_id": str(self.user.id)}
        )
        if not existing:
            self._default()
            self.save()
        else:
            for key, val in existing.items():
                setattr(self, key, val)

    @expire_cache
    def reset(self):
        """
        Resets a model for a particular user.
        """
        self._default()
        kwargs = dict(self)
        kwargs.pop("user_id")
        self.mongo.update_one(
            {
                "user_id": str(self.user.id)
            },
            {
                "$set": {**kwargs}
            }
        )

    @expire_cache
    def save(self):
        super().save()

    @expire_cache
    def update(self, **kwargs):
        """
        Updates an existing unfrozen model.
        """
        if not kwargs:
            return
        self.mongo.update_one(
            {
                "user_id": str(self.user.id)
            },
            {
                "$set": kwargs
            }
        )
        for key, val in kwargs.items():
            setattr(self, key, val)

    def _default(self):
        """
        The default values to be used for init.
        """
        raise NotImplementedError

# endregion


# region Unlocked Models

class Boosts(UnlockedModel):
    """Wrapper for Permanent Boosts based DB actions.

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    """

    def _default(self):
        self.user_id: str = str(self.user.id)
        self.lucky_looter: int = 0
        self.loot_lust: int = 0
        self.fortune_burst: int = 0
        self.flipster: int = 0

    @classmethod
    def reset_all(cls: Type[Boosts]):
        """
        Resets the Boosts collection.
        """
        cls.mongo.update_many(
            {"user_id": {"$exists": True}},
            {"$set": {
                "lucky_looter": 0,
                "loot_lust": 0,
                "fortune_burst": 0,
                "flipster": 0
            }}
        )


class Loots(UnlockedModel):
    """Wrapper for Loots based DB actions.

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    """
    def _default(self):
        self.user_id: str = str(self.user.id)
        self.tier: int = 1
        self.earned: int = 0
        self.daily_claimed_on: datetime = (
            datetime.now() - timedelta(days=1)
        )
        self.daily_streak: int = 0

    @classmethod
    def reset_all(cls: Type[Loots]):
        """
        Resets the Loots collection.
        """
        cls.mongo.update_many(
            {"user_id": {"$exists": True}},
            {"$set": {
                "tier": 1,
                "earned": 0,
                "daily_claimed_on": datetime.now() - timedelta(
                    days=1
                ),
                "daily_streak": 0
            }}
        )


class Profiles(UnlockedModel):
    """Wrapper for Profiles based DB actions.

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    """

    # pylint: disable=access-member-before-definition

    def __init__(self, user: discord.Member):
        self.excludes = ['full_info']
        super().__init__(user)
        names = [self.user.name, self.name]
        if self.user.nick:
            names.append(self.user.nick)
        self.name = min(
            names,
            key=lambda x: (
                sum(ord(ch) for ch in x),
                len(x)
            )
        )
        if self.user.guild.id == int(os.getenv('OFFICIAL_SERVER')):
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

    def __eq__(self, other: Profiles) -> bool:
        return self.user.id == other.user.id

    @property
    def full_info(self) -> Dict:
        """Get the full/consolidated info for the user.

        :return: The full info for the user.
        :rtype: Dict
        """
        for collection in [Loots, Boosts]:
            if not collection(self.user).get():
                collection(self.user).save()
        return next(self.mongo.aggregate([
            {
                "$match": {
                    "user_id": str(self.user.id)
                }
            },
            {
                "$lookup": {
                    "from": "loots",
                    "localField": "user_id",
                    "foreignField": "user_id",
                    "as": "loots"
                }
            },
            {
                "$lookup": {
                    "from": "boosts",
                    "localField": "user_id",
                    "foreignField": "user_id",
                    "as": "boosts"
                },
            },
            {
                "$unset": [
                    "_id", "loots._id", "boosts._id",
                    "loots.user_id", "boosts.user_id",
                    "user_info", "loots.user_info",
                    "boosts.user_info"
                ]
            }
        ]))

    @expire_cache
    def credit(self, amount: int, bonds: bool = False):
        """Shorthand method to credit user\'s balance and won_chips.

        :param amount: The amount to credit to the balance.
        :type amount: int
        :param bonds: Currency type is Pokebonds?
        :type bonds: bool
        """
        if bonds:
            self.update(
                balance=self.balance + (amount * 10),
                pokebonds=self.pokebonds + amount
            )
        else:
            self.update(
                balance=self.balance + amount,
                won_chips=self.won_chips + amount
            )

    @expire_cache
    def debit(self, amount: int, bonds: bool = False):
        """Shorthand method to debit user\'s balance and won_chips.

        :param amount: The amount to debit from the balance.
        :type amount: int
        :param bonds: Currency type is Pokebonds?
        :type bonds: bool
        """
        if bonds:
            self.update(
                balance=self.balance - (amount * 10),
                pokebonds=self.pokebonds - amount
            )
        else:
            self.update(
                balance=self.balance - amount,
                won_chips=self.won_chips - amount
            )

    def get_badges(self) -> List[str]:
        """Computes the Badges unlocked by the user.

        :return: The list of badges unlocked by the user.
        :rtype: List[str]
        """
        definitions = {
            "champion": ("num_wins", 1),
            "emperor": ("balance", 101),
            "funder": ("pokebonds", 1)
        }
        badges = [
            key
            for key, val in definitions.items()
            if next(
                self.mongo.aggregate([
                    {"$sort": {val[0]: -1}},
                    {"$limit": 1},
                    {"$match": {
                        "user_id": str(self.user.id),
                        val[0]: {
                            "$gte": val[1]
                        }
                    }}
                ]),
                False
            )
        ]
        if self.is_dealer:
            badges.append("dealer")
        return badges

    def get_rank(self) -> int:
        """Get the user\'s rank in the leaderboard.

        :return: The user\'s rank in the leaderboard.
        :rtype: int
        """
        res = self.mongo.aggregate([
            {
                "$match": {"num_wins": {"$gte": 1}}
            },
            {
                "$sort": {
                    "num_wins": -1,
                    "num_matches": -1,
                    "balance": -1
                }
            },
            {"$limit": 20},
            {
                "$group": {
                    "_id": 0,
                    "users": {
                        "$push": {
                            "_id": "$user_id",
                            "num_wins": "$num_wins",
                            "num_matches": "$num_matches",
                            "balance": "$balance"
                        }
                    }
                }
            },
            {
                "$unwind": {
                    "path": "$users",
                    "includeArrayIndex": "rank"
                }
            },
            {
                "$match": {
                    "users._id": str(self.user.id)
                }
            },
            {"$project": {
                "rank": {"$add": ["$rank", 1]}
            }}
        ])
        return next(res, {"rank": 0})["rank"]

    @classmethod
    def get_all(
        cls: Type[Profiles],
        ids_only: bool = False
    ) -> List[Dict]:
        """DB query to get all whitelisted profiles.

        :param ids_only: Return only the user IDs?
        :type ids_only: bool
        :return: The list of whitelisted profiles.
        :rtype: List[Dict]
        """
        pipeline = [
            {
                "$lookup": {
                    "from": "blacklist",
                    "localField": "user_id",
                    "foreignField": "user_id",
                    "as": "blacklist"
                }
            },
            {
                "$match": {
                    "blacklist": {"$eq": []}
                }
            }
        ]
        if ids_only:
            pipeline.append({
                "$project": {
                    "user_id": "$user_id"
                }
            })
        for result in cls.mongo.aggregate(pipeline):
            if ids_only:
                yield int(result.get("user_id", 0))
            else:
                yield result

    @classmethod
    def get_leaderboard(
        cls: Type[Profiles],
        sort_by: List[str]
    ) -> List[Dict]:
        """Get the global leaderboard of PokeGambler.

        :param sort_by: The fields to sort the leaderboard by.
        :type sort_by: List[str]
        :return: The leaderboard.
        :rtype: List[Dict]
        """
        res = cls.mongo.aggregate([
            {
                "$match": {"num_wins": {"$gte": 1}}
            },
            {
                "$sort": {
                    field: -1
                    for field in sort_by
                }
            }
        ])
        yield from res

    @classmethod
    def reset_all(cls: Type[Profiles]):
        """
        Resets all the Profiles.
        """
        cls.mongo.update_many(
            {"user_id": {"$exists": True}},
            {"$set": {
                "balance": 100,
                "num_matches": 0,
                "num_wins": 0,
                "pokebonds": 0,
                "won_chips": 100,
                "background": None,
                "embed_color": None
            }}
        )

    def _default(self):
        init_dict = {
            "user_id": str(self.user.id),
            "name": self.user.name,
            "balance": 100,
            "num_matches": 0,
            "num_wins": 0,
            "pokebonds": 0,
            "won_chips": 100,
            "is_dealer": "dealers" in [
                role.name.lower()
                for role in self.user.roles
            ],
            "background": None,
            "embed_color": None
        }
        for key, val in init_dict.items():
            setattr(self, key, val)


class Votes(UnlockedModel):
    """
    .. _Votes: https://top.gg/bot/873569713005953064/vote

    Wrapper for `Votes`_ based DB actions.

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    """

    def _default(self):
        self.user_id: str = str(self.user.id)
        self.last_voted: datetime = (
            datetime.now() - timedelta(days=1)
        )
        self.total_votes: int = 0
        self.vote_streak: int = 0
        self.reward_claimed: bool = False

    @classmethod
    def most_active_voter(cls: Type[Votes]) -> Dict:
        """Get the most active voter.

        :return: The most active voter.
        :rtype: Dict
        """
        res = cls.mongo.aggregate([
            {
                "$sort": {"total_votes": -1}
            },
            {"$limit": 1},
            {
                "$project": {
                    "_id": "$user_id",
                    "total_votes": "$total_votes"
                }
            }
        ])
        return next(res, None)

    @classmethod
    def reset_all(cls: Type[Votes]):
        """
        Resets the Votes collection.
        """
        cls.mongo.update_many(
            {"user_id": {"$exists": True}},
            {"$set": {
                "last_voted": datetime.now() - timedelta(
                    days=1
                ),
                "total_votes": 0,
                "vote_streak": 0,
                "reward_claimed": False
            }}
        )

# endregion


# region Minigames

class Duels(Minigame):
    """Wrapper for duels based DB actions

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    :param gladiator: The gladiator used by the user.
    :type gladiator: Optional[str]
    :param opponent: The opponent for the Duel.
    :type opponent: Optional[:class:`discord.Member`]
    :param opponent_gladiator: The gladiator of the opponent.
    :type opponent_gladiator: Optional[str]
    :param won: The ID of the winner of the Duel.
    :type won: Optional[str]
    :param cost: The cost of the Duel., default is 50.
    :type cost: Optional[int]
    """

    def __init__(
        self, user: discord.Member,
        gladiator: Optional[str] = None,
        opponent: Optional[discord.Member] = None,
        opponent_gladiator: Optional[str] = None,
        won: Optional[str] = None,
        cost: int = 50
    ):
        super().__init__(user)
        self.played_at = datetime.now()
        self.played_by = str(user.id)
        self.gladiator = gladiator
        self.opponent = to_dict(opponent)
        self.opponent_gladiator = opponent_gladiator
        self.cost = cost
        self.won = won

    def get_plays(self, wins: bool = False) -> List[Dict]:
        """Returns list of duels played/won by the user.

        :param wins: Whether to get the list of wins or plays.
        :type wins: bool
        :return: The list of plays.
        :rtype: List[Dict]
        """
        filter_ = {
            "played_by": str(self.user.id)
        }
        if wins:
            filter_.update({"won": str(self.user.id)})
        return list(self.mongo.aggregate([
            {
                "$match": filter_
            }
        ]))

    def _get_lb_group(self):
        return {
            "_id": "$played_by",
            "num_wins": {
                "$sum": {
                    "$toInt": {"$eq": ["$won", "$played_by"]}
                }
            },
            "num_matches": {"$sum": 1},
            "cumm_cost": {"$sum": "$cost"}
        }


class Flips(Minigame):
    """Wrapper for Quickflips based DB actions.

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    :param cost: The cost of the flip.
    :type cost: int
    :param won: Did the user win the flip?
    :type won: bool
    """

    def __init__(
        self, user: discord.Member,
        cost: int = 50, won: bool = False
    ):
        super().__init__(user)
        self.played_at = datetime.now()
        self.played_by = str(user.id)
        self.cost = cost
        self.won = won


class Moles(Minigame):
    """Wrapper for Whackamole based DB actions.

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    :param cost: The cost of the mole.
    :type cost: int
    :param level: The level of the mole.
    :type level: int
    :param won: Did the user win the mole?
    :type won: bool
    """

    def __init__(
        self, user: discord.Member,
        cost: int = 50, level: int = 1,
        won: bool = False
    ):
        super().__init__(user)
        self.played_at = datetime.now()
        self.played_by = str(user.id)
        self.cost = cost
        self.level = level
        self.won = won

    def _get_lb_group(self) -> Dict[str, Any]:
        return {
            **super()._get_lb_group(),
            "avg_lvl": {"$avg": "level"}
        }

    def _get_lb_sort(self) -> Dict[str, Any]:
        return {
            **super()._get_lb_sort(),
            "avg_lvl": -1
        }

# endregion
