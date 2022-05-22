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

Module which contains different discord application command components.
"""

# pylint: disable=too-many-instance-attributes

from __future__ import annotations
from dataclasses import (
    dataclass, field,
    fields, make_dataclass
)
import dataclasses
from datetime import datetime
from enum import Enum
from functools import total_ordering
from typing import (
    Any, Callable, Dict,
    List, Set, Tuple, Union
)

import discord


def from_dict(cls: Any, data: Dict[str, Any]) -> Any:
    """Populate the Dataclass from a dictionary.

    :param data: The dictionary to populate the dataclass from.
    :type data: Dict
    :return: The Dataclass instance.
    :rtype: Any
    """
    if new_fields := [
        (key, type(val), field(default=None))
        for key, val in data.items()
        if key not in (param.name for param in fields(cls))
    ]:
        old_fields = [
            (
                field_.name, field_.type, field(
                    default=field_.default,
                    default_factory=field_.default_factory
                )
            )
            for field_ in fields(cls)
        ]
        new_cls = make_dataclass(
            cls.__name__,
            fields=old_fields+new_fields,
            bases=(cls,)
        )
        new_cls.__subclasses__ = cls.__subclasses__
        return new_cls(**data)
    return cls(**data)


class CommandOptions(dict):
    """
    A class to hold application command options.
    """
    def __init__(self, **kwargs):
        super().__init__(kwargs)
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __getattr__(self, item: str) -> Any:
        return super().get(item, None)

    def __hash__(self) -> int:
        return hash(frozenset(self.to_dict().items()))

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)
        super().__setitem__(key, value)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the options to a dictionary.
        """
        return {
            key: value
            for key, value in self.__dict__.items()
            if not key.startswith('_')
        }


@dataclass(repr=True)
class AppCommand:
    """
    The model equivalent to a generic discord Application Command.
    """
    #: The type of the command.
    type: int = 0
    # pylint: disable=invalid-name
    #: Unique id of the command
    id: str = None
    # pylint: enable=invalid-name
    #: Unique id of the application to which the command belongs.
    application_id: str = None
    #: Guild id of the command, if not global
    guild_id: str = None
    #: Command name, must be between 1 and 32 characters.
    #:
    #: .. warning::
    #:
    #:     The cmd\_ prefix must be removed before assigning.
    name: str = None
    #: A description with a length between 1 and 100 characters.
    description: str = ""
    #: The parameters for the command, max 25
    options: List[CommandOptions] = field(
        default_factory=list
    )
    version: int = None

    def __post_init__(self):
        """
        Convert Options to a List of :class:`SlashCommandOptions`
        """
        for idx, opt in enumerate(self.options):
            required = opt.get('required', False)
            opt.update({
                'required': required
            })
            self.options[idx] = CommandOptions(**opt)
        self.options = sorted(
            self.options,
            key=lambda opt: -opt.required
        )

    @classmethod
    def types(cls) -> Set[int]:
        """
        Return the command types of parent and children commands.

        :return: The command types of parent and children commands.
        :rtype: Set[int]
        """
        return (cls.type,) + tuple(
            cmd.type
            for cmd in cls.__subclasses__()
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AppCommand:
        """Populate the AppCommand from a dictionary.

        :param data: The dictionary to populate the AppCommand from.
        :type data: Dict
        :return: The AppCommand instance.
        :rtype: :class:`AppCommand`
        """
        return from_dict(cls, data)

    def to_dict(self) -> Dict[str, Any]:
        """Return the AppCommand as a dictionary.

        :return: A dictionary representation of the AppCommand.
        :rtype: Dict[str, Any]
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "options": [
                opts.to_dict()
                for opts in self.options
            ]
        }


@dataclass(repr=True)
class SlashCommand(AppCommand):
    """
    The model equivalent to a discord Slash Command.
    Has the structure of command input object from discord's api.
    """
    #: | The type of the command.
    #: | Always 1 because this is a slash command.
    type: int = 1

    def __hash__(self) -> int:
        return int(
            ''.join(
                str(ord(c))
                for c in self.name
            )
        )

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, SlashCommand) and
            self.name == other.name
        )

    @property
    def parameters(self) -> Dict[str, Tuple[int, bool]]:
        """
        The parameters of the command.

        :return: The function parameters, along with type and required.
        :rtype:
        """
        return {
            opt.name: {
                field: val
                for field, val in opt.items()
                if val is not None
            }
            for opt in self.options
            if opt.name is not None
        }


@dataclass(repr=True)
class ContextMenu(AppCommand):
    """
    The model equivalent to a discord Context Menu.

    .. note::

        This is intended to be only used for simple
        :class:`~scripts.commands.normalcommands.NormalCommands`.
        There's no scope of args and kwargs here.
    """
    #: | The type of the command.
    type: int = 2  # User Command by default
    #: A callback which gets executed upon interaction.
    callback: Callable = None
    #: Holder for all the created context menu commands.
    registered: Dict[str, ContextMenu] = field(default_factory=dict)

    async def execute(self, interaction: discord.Interaction):
        """Executes the registered callback.

        :param interaction: The interaction which triggered the callback.
        :type interaction: :class:`discord.Interaction`
        """
        await self.callback(message=interaction)


@dataclass(repr=True)
class UserCommand(ContextMenu):
    """
    The model equivalent to a discord Context Menu.
    """
    #: | The type of the command.
    #: | Always 2 because this is a user command.
    type: int = 2


@dataclass(repr=True)
class MessageCommand(ContextMenu):
    """
    The model equivalent to a discord Message Command.
    """
    #: | The type of the command.
    #: | Always 3 because this is a message command.
    type: int = 3


@total_ordering
class IsoTimeStamp:
    """
    A class which represents an ISO 8601 timestamp.
    """
    def __init__(self, time_obj: Union[datetime, str]):
        """
        :param time_obj: The time object to convert to an ISO timestamp.
        :type time_obj: Union[datetime, str]
        """
        if isinstance(time_obj, datetime):
            self.datetime = time_obj
            self.timestamp = time_obj.isoformat()
        else:
            self.timestamp = time_obj
            self.datetime = datetime.fromisoformat(time_obj)

    def __str__(self):
        return self.timestamp

    def __repr__(self):
        return f"<IsoTimeStamp: {self.timestamp}>"

    def __eq__(self, other):
        return self.datetime == other.datetime

    def __lt__(self, other):
        return self.datetime < other.datetime

    def parse(self):
        """
        Parses the timestamp and returns a datetime object.

        :return: The parsed datetime object.
        :rtype: datetime
        """
        return self.datetime

    def iso(self):
        """
        Returns the timestamp as an ISO 8601 string.

        :return: The timestamp as an ISO 8601 string.
        :rtype: str
        """
        return self.timestamp

    @classmethod
    def from_datetime(cls, datetime_: datetime) -> str:
        """
        Convert a datetime to an ISO 8601 timestamp.

        :param datetime_: The datetime to convert.
        :type datetime_: datetime
        :return: The ISO 8601 timestamp.
        :rtype: str
        """
        return datetime_.isoformat()


class GuildEventPrivacyLevels(Enum):
    """
    The privacy levels of the bot.
    """
    GUILD_ONLY = 2


class GuildEventStatus(Enum):
    """
    The status of a guild event.
    """
    SCHEDULED = 1
    ACTIVE = 2
    COMPLETED = 3
    CANCELLED = 4


class GuildEventType(Enum):
    """
    The type of a guild event.
    """
    STAGE_INSTANCE = 1
    VOICE = 2
    EXTERNAL = 3


@dataclass(repr=True)
class GuildEvent:
    """
    The model equivalent to a discord Guild Scheduled Event.
    """
    # pylint: disable=invalid-name
    #: Unique id of the event
    id: str = None
    # pylint: enable=invalid-name
    #: Id of the guild to which the event belongs.
    guild_id: str = None
    #: Id of the channel to which the event belongs.
    channel_id: str = None
    #: The name of the event.
    #: .. note::
    #:
    #:     Must be between 1 and 100 characters.
    name: str = None
    #: The description of the event.
    #: .. note::
    #:
    #:     Must be between 1 and 1000 characters.
    description: str = ""
    #: The time at which the event will start.
    scheduled_start_time: IsoTimeStamp = None
    #: The time at which the event will end.
    scheduled_end_time: IsoTimeStamp = None
    #: The privacy level of the scheduled event
    privacy_level: int = GuildEventPrivacyLevels.GUILD_ONLY
    #: The status of the event.
    status: int = GuildEventStatus.SCHEDULED
    #: The type of the scheduled event.
    entity_type: int = GuildEventType.EXTERNAL
    #: The id of the entity to which the event belongs.
    entity_id: str = None
    #: The metadata for the event entity.
    entity_metadata: Dict = field(default_factory=dict)
    #: The event creator object.
    creator: Dict = field(default_factory=dict)
    #: Number of users who have subscribed to the event.
    user_count: int = 0

    @classmethod
    def from_dict(cls, data: Dict) -> GuildEvent:
        """
        Creates a GuildEvent object from a dictionary.

        :param data: The dictionary to create the object from.
        :type data: Dict
        :return: The created GuildEvent object.
        :rtype: :class:`GuildEvent`
        """
        event_cls = from_dict(cls, data)
        event_cls.scheduled_start_time = IsoTimeStamp(
            event_cls.scheduled_start_time
        )
        if event_cls.scheduled_end_time is not None:
            event_cls.scheduled_end_time = IsoTimeStamp(
                event_cls.scheduled_end_time
            )
        return event_cls

    def to_dict(self) -> Dict:
        """
        Converts the event to a dict.

        :return: The event as a dict.
        :rtype: Dict
        """
        dict_obj = dataclasses.asdict(self)
        dict_obj["scheduled_start_time"] = self.scheduled_start_time.parse()
        dict_obj["scheduled_end_time"] = self.scheduled_end_time.parse()
        privacy_name = GuildEventPrivacyLevels(self.privacy_level).name
        dict_obj["privacy_level"] = f"{privacy_name} ({self.privacy_level})"
        status_name = GuildEventStatus(self.status).name
        dict_obj["status"] = f"{status_name} ({self.status})"
        entity_type_name = GuildEventType(self.entity_type).name
        dict_obj["entity_type"] = f"{entity_type_name} ({self.entity_type})"
        return dict_obj

    def to_payload(self) -> Dict:
        """
        Converts the event to a payload.

        :return: The event as a payload.
        :rtype: Dict
        """
        return {
            "channel_id": self.channel_id,
            "entity_metadata": self.entity_metadata,
            "name": self.name,
            "privacy_level": self.privacy_level.value,
            "scheduled_end_time": self.scheduled_end_time.iso(),
            "scheduled_start_time": self.scheduled_start_time.iso(),
            "description": self.description,
            "entity_type": self.entity_type.value
        }

    def set_text_channel(self, channel_id: str):
        """
        Sets the text channel of the event.

        :param channel_id: The id of the text channel.
        :type channel_id: str
        """
        self.entity_metadata["location"] = f"<#{channel_id}>"

    def set_voice_channel(self, channel_id: str):
        """
        Sets the voice channel of the event.

        :param channel_id: The id of the voice channel.
        :type channel_id: str
        """
        self.channel_id = channel_id
