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
    Any, Callable, Dict, Iterable, List,
    Optional, Tuple, Type, Union,
    TYPE_CHECKING
)

import discord
from discord import Guild, Member, TextChannel, User, Role
from pymongo import UpdateOne
from bson import ObjectId

if TYPE_CHECKING:
    from bot import PokeGambler

# pylint: disable=cyclic-import, wrong-import-position
from ..base.items import Item, DB_CLIENT


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
        discord.TextChannel,
        discord.Role
    ]
) -> Dict[str, Any]:
    """Convert a Discord object into a Dictionary.

    .. note::
        Currently only supports User, Guild, and TextChannel.

    :param dc_obj: Discord object to be converted.
    :type dc_obj: Union[
        :class:`discord.User`, :class:`discord.Guild`,
        :class:`discord.TextChannel`,
        :class:`discord.Role`]
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


class MethodNotAllowed(Exception):
    """Exception raised when a method is not allowed."""


class NameSetter(type):
    """
    Metaclass to set the mongo collection for the model.
    Useful for DB actions in Classmethods.
    Also used for setting default class attributes.

    :meta private:
    """
    def __new__(cls, name, bases, dct):
        new_cl = super().__new__(
            cls, name, bases, dct
        )
        new_cl.model_name = new_cl.__name__.lower()
        new_cl.mongo = DB_CLIENT[new_cl.model_name]
        new_cl.no_uinfo = dct.get('no_uinfo', False)
        new_cl._uid_fields = dct.get('uid_fields', [])
        new_cl.sort_order = dct.get('sort_order', [])
        new_cl.read_only = dct.get('read_only', False)
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
        def serialize(obj):
            if isinstance(obj, list):
                return [serialize(item) for item in obj]
            if isinstance(obj, dict):
                return {
                    key: serialize(value)
                    for key, value in obj.items()
                }
            if isinstance(obj, (Model, Item)):
                return dict(obj)
            if isinstance(obj, ObjectId):
                return str(obj)
            return obj

        iterable = dir(self)
        if self.sort_order:
            iterable = sorted(
                iterable,
                key=lambda x: (
                    self.sort_order.index(x)
                    if x in self.sort_order
                    else len(self.sort_order)
                )
            )
        for attr in iterable:
            # Patch for Full_Info being executed before Profile creation.
            if attr in getattr(self, "excludes", []):
                continue
            if attr == 'user' and (
                self.no_uinfo
                or isinstance(self, TaskModel)
            ):
                continue
            if all([
                not attr.startswith("_"),
                attr not in [
                    "model_name", "mongo",
                    "excludes", "no_uinfo",
                    "uid_fields", "classes",
                    "count", "pk_field",
                    "sort_order", "read_only"
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
                res = serialize(res)
                yield (attr, res)

    @classmethod
    @property
    def uid_fields(cls) -> List[str]:
        """
        List of fields containing user IDs.

        :return: List of fields containing user IDs.
        :rtype: List[str]
        """
        if ('user_id', str) not in cls._uid_fields:
            cls._uid_fields.append(('user_id', str))
        return cls._uid_fields

    def drop(self):
        """
        Deletes all entries in the Collection for the user.
        """
        if self.read_only:
            raise MethodNotAllowed("This model is read-only.")
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
        return (
            dict(self) if not param
            else dict(self).get(param)
        )

    def save(self):
        """
        Saves the Model object to the Collection.
        """
        if self.read_only:
            raise MethodNotAllowed("This model is read-only.")
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
        if cls.read_only:
            raise MethodNotAllowed("This model is read-only.")
        cls.mongo.delete_many({})

    @classmethod
    @property
    def classes(cls) -> List[Type[Model]]:
        """
        List of all subclasses of Model.

        :return: List of all subclasses of Model.
        :rtype: List[Type[Model]]
        """
        return [
            cls
            for cls in Model.__subclasses__()
            if cls not in (UnlockedModel, Minigame)
        ] + UnlockedModel.__subclasses__() + Minigame.__subclasses__()

    @classmethod
    def censor_uids(cls, user: discord.User) -> int:
        """
        Censors the user IDs in all the collections.

        :param user: The user to censor.
        :type user: :class:`discord.User`
        :return: The number of documents censored.
        :rtype: int
        """
        def get_filter(user, elem, type_):
            if type_ in (list, dict):
                return {f'{elem}.id': user.id}
            return {elem: str(user.id)}

        def replace_id(id_, record):
            for key, value in record.items():
                if str(value) == str(id_):
                    record[key] = 'REDACTED'
                elif isinstance(value, dict):
                    replace_id(id_, value)
                elif isinstance(value, list):
                    for idx, value_ in enumerate(value):
                        value[idx] = replace_id(id_, value_)
            return record

        num_deleted = 0
        # pylint: disable=not-an-iterable
        for model in cls.classes:
            filter_ = {
                "$or": [
                    get_filter(user, name, type_)
                    for name, type_ in model.uid_fields
                ]
            }
            modified_records = [
                UpdateOne(
                    {'_id': record.pop('_id')},
                    {'$set': replace_id(user.id, record)}
                )
                for record in model.mongo.find(filter_)
            ]
            if modified_records:
                res = model.mongo.bulk_write(modified_records)
                raw = res.bulk_api_result
                if raw.get('nModified', 0) > 0:
                    num_deleted += raw['nModified']
        return num_deleted

    @classmethod
    def count(cls) -> int:
        """
        The number of documents in the collection.

        :return: The number of documents in the collection.
        :rtype: int
        """
        return cls.mongo.estimated_document_count()


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

    uid_fields = [('blacklisted_by', dict)]

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
        if need_to_remove := [
            role
            for role in self.user.roles
            if role.name.title() in titles
        ]:
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

    def save(self):
        """
        Override Save to serialize Discord objects in args or kwargs.
        """
        for idx, arg in enumerate(self.args):
            if isinstance(arg, (Guild, TextChannel, User, Member, Role)):
                self.args[idx] = to_dict(arg)
        for key, value in self.kwargs.items():
            if isinstance(value, (Guild, TextChannel, User, Member, Role)):
                self.kwargs[key] = to_dict(value)
        super().save()

    @classmethod
    def history(cls, limit: Optional[int] = 5, **kwargs) -> List[Dict]:
        """Returns the list of commands used on PG till now.

        :param limit: The number of documents to return., default 5
        :type limit: Optional[int]
        :return: The recorded commands from the DB.
        :rtype: List[Dict]
        """
        return list(cls.mongo.find(kwargs).sort("_id", -1).limit(limit))

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
        return cls.mongo.count_documents({
            "user_id": user_id
        })

    @classmethod
    def clean_guild(cls, guild_id: int) -> int:
        """Replaces the given guild ID in all commands with "REDACTED".

        :param guild_id: The ID of the guild.
        :type guild_id: str
        :return: The number of removed commands.
        :rtype: int
        """
        return cls.mongo.update_many(
            {"guild.id": guild_id},
            {
                "$set": {
                    "guild.id": "REDACTED"
                }
            }
        ).modified_count

    @classmethod
    def trend(
        cls, include_os: bool = True,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Iterable[Dict[str, Union[int, datetime]]]:
        """Returns the number of commands used on PG per day.

        :param include_os: Whether to include commands used on the Official Server.
        :type include_os: bool
        :param start_time: The start time of the period.
        :type start_time: Optional[datetime]
        :param end_time: The end time of the period.
        :type end_time: Optional[datetime]
        :return: The number of commands used on PG.
        :rtype: Iterable[Dict[str, Union[int, datetime]]]
        """
        if include_os:
            match = {}
        else:
            match = {
                '$match': {
                    'guild.id': {
                        '$nin': [
                            int(os.getenv('OFFICIAL_SERVER')),
                            int((
                                os.getenv('BLACKLIST_GUILDS')
                                if os.getenv('IS_PROD') == 'True'
                                else os.getenv('WHITELIST_GUILDS')
                            ).split(', ')[0])
                        ]
                    }
                }
            }
        if start_time is None:
            start_time = datetime(2021, 1, 1)
        if end_time is None:
            end_time = datetime.now()
        match['$match']['used_at'] = {
            '$gte': start_time,
            '$lte': end_time
        }
        return cls.mongo.aggregate([
            match,
            {
                '$group': {
                    '_id': {
                        '$dateToString': {
                            'format': '%Y-%m-%d',
                            'date': '$used_at'
                        }
                    },
                    'count': {
                        '$sum': 1
                    }
                }
            },
            {
                '$sort': {
                    '_id': 1
                }
            },
            {
                '$project': {
                    "date": {
                        "$dateFromString": {
                            "format": "%Y-%m-%d",
                            "dateString": "$_id"
                        }
                    },
                    "_id": 0,
                    "count": 1
                }
            }
        ])


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

    uid_fields = [("created_by", str)]

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
            filter_["user_id"] = user_id
        if not cls.mongo.count_documents(filter_):
            return None
        yield from cls.mongo.find(filter_)


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

    uid_fields = [("admin", dict)]

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
        self.admin = to_dict(admin)
        self.pokebot = to_dict(pokebot)
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
        if result := next(self.mongo.aggregate(pipeline), None):
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
        if self.mongo.find_one({
            "user_id": self.user_id,
            "itemid": itemid
        }):
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
        if self.from_id(itemid):
            new_item = Item.from_id(itemid, force_new=True)
            new_item.save()
            itemid = new_item.itemid
        self.mongo.insert_one({
            "user_id": self.user_id,
            "user": to_dict(self.user),
            "itemid": itemid,
            "obtained_on": datetime.now()
        })

    def bulk_insert(self, items: List[str]):
        """Inserts a list of items to a player's inventory.

        :param items: The list of item ids to insert.
        :type items: List[str]
        """
        new_items = Item.bulk_from_id(items, force_new=True)
        self.mongo.insert_many([
            {
                "user_id": self.user_id,
                "user": to_dict(self.user),
                "itemid": item.itemid,
                "obtained_on": datetime.now()
            }
            for item in new_items
        ])


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
    uid_fields = [
        ('started_by', dict),
        ('participants', list),
        ('winner', dict)
    ]

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
        return self.mongo.count_documents({
            "$or": [
                {
                    "played_by": str(self.user.id)
                },
                {
                    "participants.id": self.user.id
                }
            ]
        })

    @property
    def num_wins(self) -> int:
        """Returns number of gamble matches won.

        :return: Number of matches won.
        :rtype: int
        """
        return self.mongo.count_documents({
            "winner.id": self.user.id
        })

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

    uid_fields = [
        ('traded_by', str),
        ('traded_to', dict)
    ]

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
        self.traded_to = to_dict(traded_to)
        self.given_chips = given_chips
        self.taken_chips = taken_chips
        self.given_items = given_items
        self.taken_items = taken_items


class Transactions(Model):
    """Wrapper for webshop transactions based DB actions.

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    :param created_on: The date and time of the transaction.
    :type created_on: datetime
    :param tx_id: The transaction ID.
    :type tx_id: str
    :param gateway: The gateway used for the transaction.
    :type gateway: str
    :param webitem_id: The ID of the webitem.
    :type webitem_id: str
    :param quantity: The quantity of the webitem purchased.
    :type quantity: int
    :param total_price: The total price of the transaction.
    :type total_price: float
    :param redeemed: Was the webitem redeemed?
    :type redeemed: bool
    """

    sort_order: Optional[List] = [
        'created_at',
        "user",
        "tx_id",
        "gateway",
        "webitem",
        "quantity",
        "total_price",
        "redeemed"
    ]

    def __init__(
        self, user: discord.Member,
        created_at: datetime = None,
        tx_id: str = None,
        gateway: str = None,
        webitem_id: str = None,
        quantity: int = None,
        total_price: float = None,
        redeemed: bool = False
    ):
        super().__init__(user)
        self.created_at = created_at
        self.tx_id = tx_id
        self.gateway = gateway
        self.webitem_id = webitem_id
        self.quantity = quantity
        self.total_price = total_price
        self.redeemed = redeemed

    # pylint: disable=arguments-differ
    def get(self, **kwargs) -> List[Transactions]:
        """Get all transactions for the user.

        :return: List of transactions.
        :rtype: List[Transactions]
        """
        pipeline = [
            {
                '$match': {
                    'user_id': str(self.user.id),
                    **kwargs
                }
            },
            {
                '$addFields': {
                    'webitem_obj_id': {
                        '$toObjectId': '$webitem_id'
                    }
                }
            },
            {
                '$lookup': {
                    'from': 'webshop',
                    'localField': 'webitem_obj_id',
                    'foreignField': '_id',
                    'as': 'webitem'
                }
            },
            {
                '$unwind': {
                    'path': '$webitem'
                }
            }
        ]
        txns = []
        for raw_tx in self.mongo.aggregate(pipeline):
            txn = Transactions(
                user=self.user,
                created_at=raw_tx['created_at'],
                tx_id=raw_tx['tx_id'],
                gateway=raw_tx['gateway'],
                webitem_id=raw_tx['webitem_id'],
                quantity=raw_tx['quantity'],
                total_price=raw_tx['total_price'],
                redeemed=raw_tx['redeemed']
            )
            # pylint: disable=attribute-defined-outside-init
            txn.webitem = Webshop(name=raw_tx['webitem']['name'])
            del txn.webitem_id
            txns.append(txn)
        return txns

    def from_tx_id(self, tx_id: str) -> Transactions:
        """Get the transaction with the given ID.

        :param tx_id: The transaction ID.
        :type tx_id: str
        :return: The transaction.
        :rtype: Transactions
        """
        txs = self.get(tx_id=tx_id)
        return txs[0] if txs else None

    def redeem(self):
        """Redeem the transaction.

        :return: The transaction.
        :rtype: Transactions
        """
        self.mongo.update_one(
            {'tx_id': self.tx_id},
            {'$set': {'redeemed': True}}
        )

# region Submodels


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
            filter_["won"] = True
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


class UnlockedModel(Model):
    """The Base Unlocked Model class which can be modified after creation.

    :param user: The user to map the collection to.
    :type user: :class:`discord.Member`
    """

    #: The name of the primary key.
    pk_field: str = "user_id"

    def __init__(self, user: discord.Member, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        if getattr(self, "_prefetched", False):
            return
        if existing := self._query_existing():
            for key, val in existing.items():
                setattr(self, key, val)
            self._prefetched = True
        else:
            self._default()
            self.save()

    def _query_existing(self):
        """
        Send a MongoDB query to prepopulate the Model if a record exists.
        Can be overridden to implement custom logic. (eg. Lookups)
        """
        return self.mongo.find_one({
            self.pk_field: (
                str(self.user.id) if self.pk_field == 'user_id'
                else getattr(self, self.pk_field)
            )
        })

    @expire_cache
    def reset(self):
        """
        Resets a model for a particular user.
        """
        self._default()
        kwargs = dict(self)
        self.update(**kwargs)

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
                self.pk_field: (
                    str(self.user.id) if self.pk_field == 'user_id'
                    else getattr(self, self.pk_field)
                )
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


class UnboundModel(Model):
    """
    A special subset of Models which don't have a user associated with them.

    :param pk_value: The value of the primary key.
    :type pk_value: Optional[Any]
    """

    #: The name of the primary key.
    pk_field: str = "_id"
    no_uinfo = True
    uid_fields = []

    def __init__(self, *args, **kwargs):
        pk_value = kwargs.get(self.pk_field)
        setattr(self, self.pk_field, pk_value)
        super().__init__(None, *args, **kwargs)
        default_flag = False
        if pk_value is not None and not getattr(self, "_prefetched", False):
            if existing := self._query_existing():
                for key, val in existing.items():
                    setattr(self, key, val)
                self._prefetched = True
            else:
                default_flag = True
        elif getattr(self, "_prefetched", False):
            default_flag = False
        elif hasattr(self, "_default"):
            default_flag = True
        if default_flag:
            self._default()

    def _query_existing(self):
        return self.mongo.find_one({
            self.pk_field: getattr(self, self.pk_field)
        })

    def drop(self):
        """
        Overriden Drop method to disable it.
        """
        raise MethodNotAllowed(
            "Unbound Models are not bound to a user."
        )

    def save(self):
        """
        Overriden Save method to pop the user field.
        """
        save_data = dict(self)
        save_data.pop('user', None)
        self.mongo.insert_one(save_data)


class TaskModel(UnboundModel):
    """
    A special subset of UnboundModels representing automated tasks.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(None, *args, **kwargs)

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
        if 'nick' in dir(self.user) and self.user.nick:
            names.append(self.user.nick)
        self.name = min(
            names,
            key=lambda x: (
                sum(ord(ch) for ch in x),
                len(x)
            )
        )
        if 'guild' in dir(self.user) and self.user.guild.id == int(
            os.getenv('OFFICIAL_SERVER')
        ):
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
        yield from cls.mongo.aggregate([
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

    @classmethod
    @property
    def votes_count(cls: Type[Votes]) -> int:
        """Get the total number of votes.

        :return: The total number of votes.
        :rtype: int
        """
        return next(
            cls.mongo.aggregate([
                {"$group": {"_id": None, "count": {"$sum": "$total_votes"}}}
            ]),
            {"count": 0}
        )["count"]

# endregion


# region Unbound Models

class Webshop(UnboundModel, UnlockedModel):
    """Wrapper for Webshop Model.

    :param name: The name of the item.
    :type name: str
    :param description: The description of the item.
    :type description: str
    :param image: The image of the item.
    :type image: str
    :param price: The price of the item.
    :type price: float
    :param offer_price: Any special offer price for the item.
    :type offer_price: float
    :param reward_pokechips: The amount of Pokechips held by the item.
    :type reward_pokechips: int
    :param reward_pokebonds: The amount of Pokebonds held by the item.
    :type reward_pokebonds: int
    :param reward_items: The ingame Items held by the item.
    :type reward_items: List[:class:`~.items.Item`]
    :param meta: Metadata Dictionary
    :type meta: Dict[str, bool]
    """

    pk_field: str = "name"
    no_uinfo: bool = True
    read_only: bool = True
    uid_fields: List[str] = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # pylint: disable=import-outside-toplevel
        import urllib.parse

        self.image = urllib.parse.urljoin(
            'https://pokegambler.vercel.app/',
            self.image
        )

    def _query_existing(self):
        rwd_itm_query = {
            '$map': {
                'input': '$reward_items',
                'as': 'first',
                'in': {
                    '$mergeObjects': [
                        '$$first', {
                            '$arrayElemAt': [
                                {
                                    '$filter': {
                                        'input': '$items',
                                        'as': 'second',
                                        'cond': {
                                            '$eq': [
                                                '$$second._id',
                                                '$$first.itemid'
                                            ]
                                        }
                                    }
                                }, 0
                            ]
                        }
                    ]
                }
            }
        }

        def to_item(item):
            quantity = item.pop('quantity', None)
            item_item = Item.from_dict(item)
            return {
                "item": item_item,
                "quantity": quantity
            }

        existing = next(self.mongo.aggregate([
            {
                "$match": {
                    "name": self.name
                }
            },
            {
                '$addFields': {
                    'discount': {
                        '$round': [
                            {
                                '$subtract': [
                                    '$price', '$offer_price'
                                ]
                            }, 2
                        ]
                    },
                    'id': '$_id'
                }
            }, {
                '$unset': '_id'
            }, {
                '$lookup': {
                    'from': 'items',
                    'localField': 'reward_items.itemid',
                    'foreignField': '_id',
                    'as': 'items'
                }
            }, {
                '$set': {
                    'reward_items': rwd_itm_query
                }
            }, {
                '$unset': 'items'
            }
        ]), None)
        if existing:
            existing["reward_items"] = [
                to_item(item)
                for item in existing["reward_items"]
            ]
        return existing

    def _default(self):
        self.name: str = ""
        self.description: str = ""
        self.image: str = ""
        self.price: float = 0.0
        self.offer_price: float = 0.0
        self.reward_pokechips: int = 0
        self.reward_pokebonds: int = 0
        self.reward_items: List[Item] = []
        self.meta: Dict[str, bool] = {
            "has_currency": False,
            "is_bundle": False,
            "ready_for_sale": False
        }

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

    uid_fields = [
        ("played_by", str),
        ("opponent", dict)
    ]

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
            filter_["won"] = str(self.user.id)
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

    uid_fields = [("played_by", str)]

    def __init__(
        self, user: discord.Member,
        cost: int = 50, won: bool = False
    ):
        super().__init__(user)
        self.played_at = datetime.now()
        self.played_by = str(user.id)
        self.cost = cost
        self.won = won
        self.uid_fields = ["played_by"]


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

    uid_fields = [("played_by", str)]

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
        self.uid_fields = ["played_by"]

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


# region Tasks

class Checkpoints(TaskModel):
    """Wrapper for Daily Checkpoints Model.

    :param ctx: The PokeGambler client.
    :type ctx: :class:`bot.PokeGambler`
    """

    def __init__(self, ctx: PokeGambler, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.created_on = datetime.now()
        #: The number of profiles created till this checkpoint.
        self.num_profiles = Profiles.count()
        #: The number of guilds the bot is in.
        self.num_guilds = len(ctx.guilds)
        #: The number of commands used till this checkpoint.
        self.num_commands = CommandData.count()
        #: The number of votes received till this checkpoint.
        self.num_votes = Votes.votes_count

    @classmethod
    def get_checkpoints(
        cls,
        start_time: datetime = None,
        end_time: datetime = None
    ) -> List[Dict]:
        """Get the checkpoints between the given times.

        :param start_time: The start time of the checkpoints.
        :type start_time: datetime
        :param end_time: The end time of the checkpoints.
        :type end_time: datetime
        :return: The checkpoints.
        :rtype: List[Dict]
        """
        if start_time is None:
            start_time = datetime(2021, 1, 1)
        if end_time is None:
            end_time = datetime.now()
        return list(cls.mongo.aggregate([
            {
                "$match": {
                    "created_on": {
                        "$gte": start_time,
                        "$lte": end_time
                    }
                }
            },
            {
                "$sort": {
                    "created_on": 1
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "created_on": 1,
                    "num_profiles": 1,
                    "num_guilds": 1,
                    "num_commands": 1,
                    "num_votes": 1
                }
            }
        ]))


class Nitro(TaskModel):
    """Wrapper for Nitro Reward records.

    :param boosters: The list of the nitro boosters.
    :type boosters: List[:class:`discord.Member`]
    :param rewardboxes: The list of IDs of nitro reward boxes.
    :type rewardboxes: List[str]
    """

    uid_fields = [('boosters', list)]

    def __init__(
        self, *args,
        boosters: List[discord.Member] = None,
        rewardboxes: List[str] = None,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
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

# endregion

# endregion
