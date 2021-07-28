"""
This module contains a compilation of data models.
"""

# pylint: disable=too-many-instance-attributes, too-many-arguments
# pylint: disable=unused-argument, too-many-lines

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from inspect import ismethod
import os
from typing import (
    Any, Dict, List,
    Optional, Tuple, Type
)

import discord

from ..base.items import Item, DB_CLIENT  # pylint: disable=cyclic-import


class NameSetter(type):
    """
    Metaclass to set the mongo collection for the model.
    Useful for DB actions in Classmethods.
    """
    def __new__(cls, name, bases, dct):
        new_cl = super().__new__(
            cls, name, bases, dct
        )
        new_cl.model_name = new_cl.__name__.lower()
        new_cl.mongo = DB_CLIENT[new_cl.model_name]
        return new_cl


@dataclass
class Model(metaclass=NameSetter):
    """
    The Base Model Class which has a corresponding table in the Collection.
    """

    # pylint: disable=no-member

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
            if all([
                not attr.startswith("_"),
                attr not in [
                    "user", "model_name",
                    "mongo", "excludes"
                ],
                not ismethod(getattr(self, attr)),
                not isinstance(
                    getattr(self.__class__, attr, None),
                    (property, staticmethod, classmethod)
                )
            ]):
                yield (attr, getattr(self, attr))

    def get(self, param=None):
        """
        Returns the Model object as a dictionary.
        """
        if not param:
            return dict(self)
        return dict(self).get(param)

    def save(self):
        """
        Saves the Model object to the Collection.
        """
        self.mongo.insert_one(dict(self))

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


class UnlockedModel(Model):
    """
    The Base Unlocked Model class which can be modified after creation.
    """

    # pylint: disable=no-member

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

    def _default(self):
        pass

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


class Profiles(UnlockedModel):
    """
    Wrapper for Profiles based DB actions.
    """

    # pylint: disable=no-member, access-member-before-definition

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

    def get_badges(self) -> List[str]:
        """
        Computes the Badges unlocked by the user.
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

    def debit(self, amount: int, bonds: bool = False):
        """
        Shorthand method to subtract from balance and won_chips.
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

    def credit(self, amount: int, bonds: bool = False):
        """
        Shorthand method to add to balance and won_chips.
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

    @classmethod
    def get_all(
        cls: Type[Profiles],
        ids_only: bool = False
    ) -> List[Dict]:
        """
        Wrapper for the DB query to get all whitelist profiles.
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

    @property
    def full_info(self) -> Dict:
        """
        Wrapper for Get Full Profile DB call.
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
                    "loots.user_id", "boosts.user_id"
                ]
            }
        ]))

    @classmethod
    def get_leaderboard(
        cls: Type[Profiles],
        sort_by: List[str]
    ) -> List[Dict]:
        """
        Wrapper for get_leaderboard DB call.
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

    def get_rank(self) -> int:
        """
        Wrapper for get_rank DB call.
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


class CommandData(Model):
    """
    Wrapper for command based DB actions
    """

    # pylint: disable=no-member

    def __init__(
        self, user: discord.Member,
        message: discord.Message,
        command: str, args: List, kwargs: Dict
    ):
        super().__init__(user)
        self.user_id = str(user.id)
        self.user_is_admin = "admins" in [
            role.name.lower()
            for role in self.user.roles
        ]
        self.used_at = datetime.now()
        self.channel = str(message.channel.id)
        self.guild = str(message.guild.id)
        self.command = command
        self.args = args
        self.kwargs = kwargs

    @classmethod
    def history(cls, limit: Optional[int] = 5, **kwargs):
        """
        Returns the list of commands used on PG till now.
        """
        return list(cls.mongo.find().limit(limit))

    @classmethod
    def num_user_cmds(cls, user_id: str) -> int:
        """
        Returns the number of commands used by a user.
        """
        return cls.mongo.find({
            "user_id": user_id
        }).count()


class Loots(UnlockedModel):
    """
    Wrapper for Loots based DB actions.
    """
    def _default(self):
        self.user_id: str = str(self.user.id)
        self.tier: int = 1
        self.earned: int = 0
        self.daily_claimed_on: datetime = (
            datetime.now() - timedelta(days=1)
        )
        self.daily_streak: int = 0


class Boosts(UnlockedModel):
    """
    Wrapper for Boosts based DB actions.
    """
    def _default(self):
        self.user_id: str = str(self.user.id)
        self.lucky_looter: int = 0
        self.loot_lust: int = 0
        self.fortune_burst: int = 0
        self.flipster: int = 0


class Blacklist(Model):
    """
    Wrapper for blacklisted users based DB actions
    """

    # pylint: disable=no-member

    def __init__(
        self, user: discord.Member,
        mod: Optional[str] = "",
        reason: Optional[str] = ""
    ):
        super().__init__(user)
        self.user_id = str(user.id)
        self.blacklisted_at = datetime.now()
        self.blacklisted_by = mod
        self.reason = reason

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

    def pardon(self):
        """
        Pardons a blacklisted user.
        """
        self.mongo.delete_one({"user_id": self.user_id})

    @classmethod
    def is_blacklisted(
        cls: Type[Blacklist],
        user_id: str
    ) -> bool:
        """
        Wrapper for is_blacklisted DB call.
        """
        return cls.mongo.find_one({"user_id": user_id})


class Trades(Model):
    """
    Wrapper for trades based DB actions
    """

    # pylint: disable=no-member

    def __init__(
        self, user: discord.Member,
        traded_to: Optional[str] = None,
        given_chips: int = None,
        taken_chips: int = None,
        given_items: List[int] = None,
        taken_items: List[int] = None
    ):
        super().__init__(user)
        self.traded_at = datetime.now()
        self.traded_by = str(user.id)
        self.traded_to = str(traded_to)
        self.given_chips = given_chips
        self.taken_chips = taken_chips
        self.given_items = given_items
        self.taken_items = taken_items


class Matches(Model):
    """
    Wrapper for matches based DB actions
    """

    # pylint: disable=no-member

    def __init__(
        self, user: discord.Member,
        started_by: str = "",
        participants: List[str] = None,
        winner: str = "", deal_cost: int = 50,
        lower_wins: bool = False,
        by_joker: bool = False
    ):
        super().__init__(user)
        self.played_at = datetime.now()
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
        return self.mongo.find({
            "$or": [
                {
                    "played_by": str(self.user.id)
                },
                {
                    "participants": str(self.user.id)
                }
            ]
        }).count()

    @property
    def num_wins(self):
        """
        Returns number of gamble matches won.
        """
        return self.mongo.find({
            "winner": str(self.user.id)
        }).count()

    def get_stats(self) -> Tuple[int, int]:
        """
        Get Match num_matches and num_wins as a Tuple.
        """
        return (self.num_matches, self.num_wins)

    @classmethod
    def get_matches(
        cls: Type[Matches],
        limit: Optional[int] = 10
    ) -> bool:
        """
        Wrapper for get_matches DB call.
        """
        pipeline = [
            {"$sort": {"played_at": -1}},
            {"$limit": limit}
        ]
        return list(cls.mongo.aggregate(pipeline))


class Inventory(Model):
    """
    Wrapper for Inventory based DB operations.
    """

    # pylint: disable=no-member

    def __init__(
        self, user: discord.Member
    ) -> None:
        super().__init__(user)
        self.user_id = str(self.user.id)

    # pylint: disable=arguments-differ,arguments-renamed
    def get(
        self, category: Optional[str] = None
    ) -> Tuple[Dict[str, List], int]:
        """
        Returns a list of items in user's Inventory.
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

    def from_name(self, name: str) -> List[str]:
        """
        Returns a list of ItemIDs if they exist in user's Inventory.
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
                    "items.name": name
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

    def from_id(self, itemid: int) -> Item:
        """
        Gets an item using ItemID if it exists in user's inventory.
        """
        item = self.mongo.find_one({
            "user_id": self.user_id,
            "itemid": itemid
        })
        if item:
            return Item.from_id(itemid)
        return None

    # pylint: disable=arguments-differ, no-member
    def save(self, itemid: str):
        """
        Saves an item in a player's inventory.
        """
        item = self.from_id(itemid)
        if item:
            new_item = Item.from_id(itemid, force_new=True)
            new_item.save()
            itemid = new_item.itemid
        self.mongo.insert_one({
            "user_id": self.user_id,
            "itemid": itemid,
            "obtained_on": datetime.now()
        })

    def delete(
        self, item_inp: str,
        quantity: int = -1,
        is_name: bool = False
    ) -> int:
        """
        Deletes an Item from user's Inventory.
        Input can either be a name or List of itemids.
        If item name is given, a quantity can be provided.
        If quantity is -1, all items of the name will be removed.
        Returns number of records deleted.
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


class Minigame(Model):
    """
    Base class for Minigames.
    """

    # pylint: disable=no-member

    def get_plays(self, wins: bool = False):
        """
        Returns list of minigames (of specified type) played.
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

    def get_lb(self):
        """
        Returns leaderboard for the specified minigame.
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

    # pylint: disable=no-self-use
    def _get_lb_sort(self) -> Dict[str, Any]:
        """
        Override it for each Minigame.
        """
        return {
            "num_wins": -1,
            "earned": -1
        }

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


class Flips(Minigame):
    """
    Wrapper for flips based DB actions
    """

    # pylint: disable=no-member

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
    """
    Wrapper for moles based DB actions
    """

    # pylint: disable=no-member

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


class Duels(Minigame):
    """
    Wrapper for duels based DB actions
    """

    # pylint: disable=no-member

    def __init__(
        self, user: discord.Member,
        gladiator: Optional[str] = None,
        opponent: Optional[str] = None,
        opponent_gladiator: Optional[str] = None,
        won: Optional[str] = None,
        cost: int = 50
    ):
        super().__init__(user)
        self.played_at = datetime.now()
        self.played_by = str(user.id)
        self.gladiator = gladiator
        self.opponent = opponent
        self.opponent_gladiator = opponent_gladiator
        self.cost = cost
        self.won = won

    def get_plays(self, wins: bool = False):
        """
        Returns list of minigames (of specified type) played.
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


class DuelActionsModel(Model):
    """
    Wrapper for duel actions based DB actions
    """

    # pylint: disable=no-member

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
        """
        Wrapper for get_actions DB call.
        """
        filter_ = {}
        if user_id:
            filter_.update({"user_id": user_id})
        if not cls.mongo.count(filter_):
            return None
        results = cls.mongo.find(filter_)
        yield from results
