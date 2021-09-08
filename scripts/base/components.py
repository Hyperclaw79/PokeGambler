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
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Dict,
    List, Tuple
)

import discord


class CommandOptions(dict):
    """
    A class to hold application command options.
    """
    def __init__(self, **kwargs):
        super().__init__(kwargs)
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __getattr__(self, item: str) -> Any:
        return super().get(item)

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
    #: Whether the command is enabled by default for everyone
    default_permission: bool = True
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
    def from_dict(cls, data: Dict[str, Any]) -> AppCommand:
        """Populate the AppCommand from a dictionary.

        :param data: The dictionary to populate the AppCommand from.
        :type data: Dict
        :return: The AppCommand instance.
        :rtype: :class:`AppCommand`
        """
        return cls(**data)

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
            ],
            "default_permission": self.default_permission,
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

    @property
    def parameters(self) -> Dict[str, Tuple[int, bool]]:
        """
        The parameters of the command.

        :return: The function parameters, along with type and required.
        :rtype:
        """
        return {
            opt.name: (opt.type, opt.required or False)
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
