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

Module which extends Discord.py to allow for custom slash commands.
"""

# pylint: disable=too-many-instance-attributes

from __future__ import annotations
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING, Any, Callable,
    Dict, List, Tuple, Union
)

import asyncio
import discord
from discord.http import Route

from ..helpers.parsers import CustomRstParser
from ..helpers.utils import get_modules

if TYPE_CHECKING:
    from bot import PokeGambler


class CustomInteraction:
    """
    An overrided class of :class:`discord.Interaction` to
    provide hybrid behavior between interaction and Message.

    :param interaction: The original interaction class.
    :type interaction: :class:`discord.Interaction`
    """
    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.author = interaction.user

    def __getattr__(self, item: str) -> Any:
        return self.__dict__.get(
            item, getattr(self.interaction, item)
        )

    async def reply(self, *args, **kwargs):
        """
        :meth:`discord.Message.reply` like behavior for Interactions.
        """
        msg = await self.interaction.followup.send(*args, **kwargs)
        return msg


class SlashCommandOptions(dict):
    """
    A class to hold slash command options.
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
class SlashCommand:
    """
    The model equivalent to a discord Slash Command.
    Has the structure of command input object from discord's api.
    """
    #: | The type of the command.
    #: | Always 1 because this is a slash command.
    type: int = 1
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
    description: str = None
    #: The parameters for the command, max 25
    options: List[SlashCommandOptions] = field(
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
            self.options[idx] = SlashCommandOptions(**opt)
        self.options = sorted(
            self.options,
            key=lambda opt: -opt.required
        )

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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SlashCommand:
        """Populate the SlashCommand from a dictionary.

        :param data: The dictionary to populate the SlashCommand from.
        :type data: Dict
        :return: The SlashCommand instance.
        :rtype: :class:`SlashCommand`
        """
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Return the SlashCommand as a dictionary.

        :return: A dictionary representation of the SlashCommand.
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


class CommandListing(list):
    """An extending hybrid list to hold instances of :class:`SlashCommand`.
    Supports accessing a command by name.

    .. _HTTPClient: https://github.com/Rapptz/discord.py/\
        blob/master/discord/http.py#L159

    :param session: The session object.
    :type session: `HTTPClient`_
    """

    def __init__(self, handler: SlashHandler):
        super().__init__()
        self.handler = handler

    def __iter__(self) -> List[SlashCommand]:
        for item in super().__iter__():
            if isinstance(item, SlashCommand):
                yield item

    def __getitem__(self, item: str) -> SlashCommand:
        for command in self:
            if command.name == item:
                return command
        return None

    def __setitem__(self, key: str, value: SlashCommand) -> None:
        if isinstance(value, dict):
            value = SlashCommand.from_dict(**value)
        super().__setitem__(key, value)

    def __contains__(self, item: Union[SlashCommand, Dict]) -> bool:
        if isinstance(item, dict):
            item = SlashCommand.from_dict(**item)
        return any(
            command.id == item.id
            for command in self
        )

    def append(self, command: Union[SlashCommand, Dict]):
        """Transform/Ensure that the command is a :class:`SlashCommand`
        and append it to the list.

        :param command: The command to add to the list.
        :type command: Union[:class:`SlashCommand`, Dict]
        """
        if isinstance(command, dict):
            command = SlashCommand(**command)
        super().append(command)

    def remove(self, command: Union[str, Dict, SlashCommand]):
        """
        | Remove a command from the list.
        | Supports lookups by name and ID.

        :param command: The command to remove from the list.
        :type command: Union[str, Dict, :class:`SlashCommand`]
        """
        for index, item in enumerate(self):
            if any([
                isinstance(command, str) and item.name == command,
                isinstance(command, dict) and item.id == command['id'],
                isinstance(command, SlashCommand) and item.id == command.id,
            ]):
                del self[index]
                return

    @property
    def names(self) -> List[str]:
        """
        :return: Stored command names.
        :rtype: List
        """
        return [command.name for command in self]

    async def refresh(self, **kwargs):
        """
        Refreshes the command list.
        """
        route = self.handler.get_route('GET', **kwargs)
        commands = await self.handler.http.request(route)
        for command in commands:
            self.append(SlashCommand.from_dict(command))


class SlashHandler:
    """
    | Class which handles custom slash commands.
    | It is an extension of Discord.py's http module.
    """
    def __init__(self, ctx: PokeGambler):
        self.ctx = ctx
        self.http = ctx.http
        self.registered = CommandListing(self)
        self.official_roles = {}
        self.update_counter = 0

    async def add_slash_commands(self, **kwargs):
        """Add all slash commands to the guild/globally.

        :param kwargs: Keyword arguments to pass to the route.
        :type kwargs: Dict
        """
        if not any([
            self.ctx.is_prod,
            self.ctx.is_local
        ]):
            return
        if not self.official_roles:
            self.official_roles = {
                role.name: role.id
                for role in self.ctx.get_guild(
                    self.ctx.official_server
                ).roles
            }
        current_commands = []
        for module in get_modules(self.ctx):
            for attr in dir(module):
                if not attr.startswith("cmd_"):
                    continue
                current_commands.append(
                    getattr(module, attr)
                )
        await self.__sync_commands(current_commands, **kwargs)
        for command in current_commands:
            await self.register_command(command, **kwargs)
            await asyncio.sleep(1.0)
        self.ctx.logger.pprint(
            f"Succesfully synced {len(self.registered)} slash commands.",
            color='green'
        )

    async def delete_command(
        self, command: Union[SlashCommand, str],
        **kwargs
    ):
        """Deletes a Slash command to the guild/globally.

        :param command: The Command object/dictionary to delete.
        :type command: Union[:class:`SlashCommand`, Dict]
        :param kwargs: Keyword arguments to pass to the route.
        :type kwargs: Dict[str, Any]
        """
        if isinstance(command, SlashCommand):
            cmd = command.to_dict()
        route_kwargs = {
            "method": "DELETE",
            "endpoint": cmd['id']
        }
        if self.ctx.is_prod:
            route_kwargs["guild_id"] = self.ctx.official_server
        kwargs.update(route_kwargs)
        route = self.get_route(**kwargs)
        try:
            await self.http.request(route)
            if cmd['name'] in self.registered.names:
                self.registered.remove(command)
            self.ctx.logger.pprint(
                f"Unregistered command: {cmd['name']}",
                color='yellow'
            )
        except discord.HTTPException as excp:
            self.ctx.logger.pprint(
                excp, color='red'
            )

    async def get_command(self, command: str) -> SlashCommand:
        """Gets the Command Object from its name.

        :param command: The command name
        :type command: str
        :return: The corresponding Slash Command object.
        :rtype: :class:`SlashCommand`
        """
        for cmd in self.registered:
            if cmd.name == command:
                return cmd
        return None

    def get_route(self, method="POST", **kwargs):
        """Get the route for the query based on the kwargs.

        :param method: HTTP Method to use.
        :type method: str
        :param kwargs: Keyword arguments to pass to the route.
        :type kwargs: Dict[str, Any]
        """
        path = f"/applications/{self.ctx.user.id}"
        if kwargs.get('guild_id'):
            path += f'/guilds/{kwargs["guild_id"]}'
        path += '/commands'
        if kwargs.get('endpoint'):
            path += f'/{kwargs["endpoint"]}'
        return Route(
            method=method,
            path=path,
            **kwargs
        )

    async def parse_response(
        self, interaction: discord.Interaction
    ) -> Tuple[Callable, Dict[str, Any]]:
        """Parse the response from the server.

        :param interaction: Interaction to parse.
        :type interaction: :class:`discord.Interaction`
        :return: Parsed command method and response.
        :rtype: Tuple[Callable, Dict[str, Any]]
        """
        await interaction.response.defer()
        interaction = CustomInteraction(interaction)
        data = interaction.data
        kwargs = {
            'message': interaction,
            'args': [],
            'mentions': []
        }
        method = None
        cmd = f'cmd_{data["name"]}'
        for com in get_modules(self.ctx):
            if com.enabled:
                method = getattr(com, cmd, None)
                if method:
                    break
        with CustomRstParser() as rst_parser:
            rst_parser.parse(method.__doc__)
            args = rst_parser.params.get('args', [])
        if 'resolved' in data:
            mentions = [
                interaction.guild.get_member(int(uid))
                for uid in data['resolved']['users']
            ]
            kwargs['mentions'] = mentions
        for opt in data.get('options', {}):
            if opt['name'] == 'user-mentions':
                continue
            if opt['name'] in args.variables:
                kwargs['args'].append(opt['value'])
                continue
            kwargs[opt['name']] = opt['value']
        return (method, kwargs)

    async def register_command(
        self, command: Callable,
        **kwargs
    ):
        """Register a Slash command to the guild/globally.

        :param command: Command to register.
        :type command: str
        :param kwargs: Keyword arguments to pass to the route.
        :type kwargs: Dict
        """
        cmd_name = command.__name__.replace('cmd_', '')
        if cmd_name in self.registered.names and self.__params_matched(
            command, cmd_name
        ):
            return {}
        self.update_counter += 1
        self.ctx.logger.pprint(
            f"[{self.update_counter}] Registering the command: {cmd_name}",
            color='blue'
        )
        payload = self.__prep_payload(command)
        if not payload:
            return {}
        route = self.get_route(**kwargs)
        if hasattr(command, "os_only") and self.ctx.is_prod:
            route = self.get_route(guild_id=self.ctx.official_server)
        need_perms = any(
            hasattr(command, perm)
            for perm in (
                'admin_only', 'owner_only',
                'dealer_only'
            )
        ) and self.ctx.is_prod
        if need_perms:
            route = self.get_route(guild_id=self.ctx.official_server)
            payload["default_permission"] = False
        try:
            resp = await self.http.request(route, json=payload)
            self.registered.remove(cmd_name)
            self.registered.append(resp)
            if need_perms:
                await self.__add_permissions(command, resp['id'])
            return resp
        except discord.HTTPException as excp:
            self.ctx.logger.pprint(
                str(excp).splitlines()[-1],
                color='red'
            )
            self.ctx.logger.pprint(
                f"{command}\n{payload}",
                color='red'
            )
            return {}

    def __params_matched(self, command, cmd_name):
        params = {}
        with CustomRstParser() as rst_parser:
            rst_parser.parse(command.__doc__)
            if rst_parser.params:
                for param in rst_parser.params.values():
                    parsed = param.parse()
                    if parsed:
                        for var in parsed:
                            params[var['name']] = (
                                var['type'], var['required']
                            )
        registered_cmd_params = self.registered[cmd_name].parameters
        return params == registered_cmd_params

    async def __add_permissions(self, command: Callable, command_id: int):
        """Add permissions to a command.

        :param command: Command to add permissions to.
        :type command: Callable
        :param command_id: Command ID to add permissions to.
        :type command_id: int
        """
        route_kwargs = {
            "method": "POST",
            "endpoint": f"{command_id}/permissions"
        }
        if self.ctx.is_prod:
            route_kwargs["guild_id"] = self.ctx.official_server
        route = self.get_route(**route_kwargs)
        perms = [
            {
                "id": uid,
                "type": 2,
                "permission": True
            }
            for uid in self.ctx.allowed_users
        ]
        if hasattr(command, "admin_only"):
            perms.append({
                "id": self.official_roles["Admins"],
                "type": 1,
                "permission": True
            })
        elif hasattr(command, "dealer_only"):
            perms.append({
                "id": self.official_roles["Dealers"],
                "type": 1,
                "permission": True
            })
        payload = {"permissions": perms}
        try:
            await self.http.request(route, json=payload)
        except discord.HTTPException as excp:
            self.ctx.logger.pprint(
                excp, color='red'
            )

    @staticmethod
    def __prep_payload(command: Callable) -> Dict:
        """Prepare payload for slash command registration.

        :param command: Command to register.
        :type command: Callable
        :return: Payload for slash command registration.
        :rtype: Dict
        """
        if getattr(command, "disabled", False):
            return {}
        if not command.__doc__:
            return {}
        with CustomRstParser() as rst_parser:
            rst_parser.parse(command.__doc__)
            meta = rst_parser.meta
            params = rst_parser.params
        options = []
        description = command.__doc__.split("\n")[0]
        desc = meta.description
        args = None
        kwargs = None
        for key, param in params.items():
            if key == "args":
                args = param
                options.extend(args.parse())
            elif key == "kwargs":
                kwargs = param
                options.extend(kwargs.parse())
            elif key == "mentions":
                options.append({
                    "name": "user-mentions",
                    "description": "Users to mention",
                    "type": 6,
                    "required": 'Optional' not in param.type
                })
        if len(desc) <= 100:
            description = desc
        options = sorted(options, key=lambda x: -x['required'])
        return {
            "name": command.__name__.replace("cmd_", "").lower(),
            "description": description,
            "type": 1,
            "options": options
        }

    async def __sync_commands(self, current_commands, **kwargs):
        await self.registered.refresh(**kwargs)
        cmds = [
            cmd.__name__.replace('cmd_', '')
            for cmd in current_commands
        ]
        for command in self.registered:
            if command.name not in cmds:
                await self.delete_command(command, **kwargs)
