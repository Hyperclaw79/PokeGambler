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

Module which extends Discord.py to allow for custom application commands.
"""

# pylint: disable=no-member

from __future__ import annotations
from typing import (
    TYPE_CHECKING, Any, Callable,
    Dict, List, Optional, Tuple, Type, Union
)

import discord
from discord.http import Route

from .components import AppCommand, ContextMenu, SlashCommand

from ..helpers.parsers import CustomRstParser
from ..helpers.utils import get_modules

if TYPE_CHECKING:
    from bot import PokeGambler


class OverriddenChannel:
    """
    A modified version of :class:`discord.TextChannel` which
    overrides :meth:`discord.TextChannel.send` to
    suppress stray deferred ephemeral messages.

    :param parent: The original interaction class.
    :type parent: :class:`discord.Interaction`
    """
    def __init__(self, parent: discord.Interaction):
        self.parent = parent
        self.channel = parent.channel

    def __getattr__(self, item: str) -> Any:
        return self.__dict__.get(
            item, getattr(self.channel, item)
        )

    async def send(self, *args, **kwargs):
        """
        :meth:`discord.TextChannel.send` like behavior for
        :class:`discord.TextChannel`.
        """
        msg = await self.channel.send(*args, **kwargs)
        # Hack to silence the stray deferred ephemeral message.
        await self.parent.followup.send(content='\u200B')
        return msg


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
        self.channel = OverriddenChannel(interaction)

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

    async def add_reaction(self, reaction: str):
        """
        :meth:`discord.Message.add_reaction` like behavior for Interactions.
        :param reaction: The reaction to add.
        :type reaction: :class:`str`
        """
        # pylint: disable=import-outside-toplevel
        from ..base.views import EmojiButton

        emoji_btn = EmojiButton(reaction)
        await self.interaction.followup.send(
            content='\u200B',
            view=emoji_btn,
            ephemeral=True
        )


class CommandListing(list):
    """An extending hybrid list to hold instances of
    :class:`~.components.AppCommand`.
    Supports accessing a command by name.

    :param handler: The command handler object.
    :type session: Union[SlashHandler, ContextHandler]
    """

    def __init__(self, handler: Union[SlashHandler, ContextHandler]):
        list.__init__(self)
        self.handler = handler

    def __iter__(self) -> List[AppCommand]:
        for item in super().__iter__():
            if isinstance(item, AppCommand):
                yield item

    def __getitem__(self, item: str) -> AppCommand:
        for command in self:
            if command.name == item:
                return command
        return None

    def __setitem__(self, key: str, value: AppCommand) -> None:
        if isinstance(value, dict):
            value = AppCommand.from_dict(**value)
        super().__setitem__(key, value)

    def __contains__(self, item: Union[AppCommand, Dict]) -> bool:
        if isinstance(item, dict):
            item = self.Component.from_dict(**item)
        return any(
            command.id == item.id
            for command in self
        )

    # pylint: disable=invalid-name
    @property
    def Component(self) -> Type[AppCommand]:
        """Returns the component class of the handler.

        :return: The component class of the handler.
        :rtype: Type[AppCommand]
        """
        return self.handler.component_class

    def append(self, command: Union[AppCommand, Dict]):
        """Transform/Ensure that the command is a
        :class:`~.components.AppCommand` and append it to the list.

        :param command: The command to add to the list.
        :type command: Union[:class:`~.components.AppCommand`, Dict]
        """
        if isinstance(command, dict):
            command = self.Component(**command)
        super().append(command)

    def remove(self, command: Union[str, Dict, AppCommand]):
        """
        | Remove a command from the list.
        | Supports lookups by name and ID.

        :param command: The command to remove from the list.
        :type command: Union[str, Dict, :class:`~.components.AppCommand`]
        """
        for index, item in enumerate(self):
            if any([
                isinstance(command, str) and item.name == command,
                isinstance(command, dict) and item.id == command['id'],
                isinstance(
                    command, AppCommand
                ) and item.id == command.id,
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
            if command['type'] in self.Component.types():
                self.append(
                    self.handler.component_class.from_dict(command)
                )


class SlashHandler:
    """
    | Class which handles custom slash commands.
    | It is an extension of Discord.py's http module.
    """
    def __init__(self, ctx: PokeGambler):
        self.ctx = ctx
        self.http = ctx.http
        self.component_class = SlashCommand
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
        msg = f"Succesfully synced {len(self.registered)} slash commands."
        if not self.update_counter:
            msg = 'No commands require sync.'
        self.ctx.logger.pprint(msg, color='green')

    async def delete_command(
        self, command: Union[SlashCommand, Dict],
        **kwargs
    ):
        """Deletes a Slash command to the guild/globally.

        :param command: The Command object/dictionary to delete.
        :type command: Union[:class:`~.components.SlashCommand`, Dict]
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
                self.registered.remove(cmd['name'])
            self.ctx.logger.pprint(
                f"Unregistered command: {cmd['name']}",
                color='yellow'
            )
        except discord.HTTPException as excp:
            self.ctx.logger.pprint(
                excp, color='red'
            )

    async def get_command(self, command: str) -> AppCommand:
        """Gets the Command Object from its name.

        :param command: The command name
        :type command: str
        :return: The corresponding Slash Command object.
        :rtype: :class:`~.components.SlashCommand`
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
        :return: Parsed command method and additional details.
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
        if self.ctx.is_local:
            cmd = cmd.rstrip('_')
        for com in get_modules(self.ctx):
            if com.enabled:
                method = getattr(com, cmd, None)
                if method:
                    break
        with CustomRstParser() as rst_parser:
            rst_parser.parse(method.__doc__)
            args = rst_parser.params.get('args', None)
        if 'resolved' in data:
            mentions = [
                interaction.guild.get_member(int(uid))
                for uid in data['resolved']['users']
            ]
            kwargs['mentions'] = mentions
        for opt in data.get('options', {}):
            if opt['name'] == 'user-mentions':
                continue
            if args and opt['name'] in args.variables:
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
        if self.ctx.is_local:
            cmd_name += '_'
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

    async def sync_permissions(
        self, commands: List[Callable],
        user: discord.Member, allow: bool = True
    ):
        """Sync permissions for a list of commands for a user.

        :param commands: List of commands to sync permissions for.
        :type commands: List[Callable]
        :param user: User to sync permissions for.
        :type user: :class:`discord.Member`
        :param allow: Whether to allow or deny the user for the commands.
        :type allow: bool
        """
        for command in commands:
            cmd_name = command.__name__.replace('cmd_', '')
            if self.ctx.is_local:
                cmd_name += '_'
            cmd_obj = self.registered[cmd_name]
            perms = [{
                'id': user.id,
                'type': 1,
                'permission': allow
            }]
            success = await self.__update_permissions(cmd_obj.id, perms)
            if success:
                state = 'allowed' if allow else 'denied'
                self.ctx.logger.pprint(
                    f"{user.mention} is now {state} "
                    f"to use {cmd_name}",
                    color='blue'
                )

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
        perms = [
            {
                "id": uid,
                "type": 2,
                "permission": True
            }
            for uid in set(
                self.ctx.allowed_users + [self.ctx.owner.id]
            )
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
        await self.__update_permissions(command_id, perms)

    async def __update_permissions(self, command_id, perms):
        route_kwargs = {
            "method": "PUT",
            "endpoint": f"{command_id}/permissions"
        }
        if self.ctx.is_prod:
            route_kwargs["guild_id"] = self.ctx.official_server
        route = self.get_route(**route_kwargs)
        payload = {"permissions": perms}
        try:
            await self.http.request(route, json=payload)
            return True
        except discord.HTTPException as excp:
            self.ctx.logger.pprint(
                excp, color='red'
            )
            return False

    def __prep_payload(self, command: Callable) -> Dict:
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
        cmd_name = command.__name__.replace("cmd_", "")
        if self.ctx.is_local:
            cmd_name += "_"
        return {
            "name": cmd_name,
            "description": description,
            "type": 1,
            "options": options
        }

    async def __sync_commands(self, current_commands, **kwargs):
        if not self.ctx.is_local:
            await self.registered.refresh()
        await self.registered.refresh(**kwargs)
        pad = '' if not self.ctx.is_local else '_'
        cmds = [
            cmd.__name__.replace('cmd_', '') + pad
            for cmd in current_commands
        ]
        for command in self.registered:
            if command.name not in cmds:
                await self.delete_command(command, **kwargs)


class ContextHandler:
    """Class which handles context menus.

    .. warning::

        Currently does not support autosync.

    :param ctx: The pokegambler client.
    :type ctx: :class:`bot.PokeGambler`
    """
    def __init__(self, ctx: PokeGambler):
        self.ctx = ctx
        self.http = ctx.http
        self.component_class = ContextMenu
        self.registered = CommandListing(self)
        self.update_counter = 0

    async def delete_command(
        self, command: Union[ContextMenu, Dict],
        **kwargs
    ):
        """Deletes a Context Menu command.

        :param command: The Command object/dictionary to delete.
        :type command: Union[:class:`~.components.ContextMenu`, Dict]
        :param kwargs: Keyword arguments to pass to the route.
        :type kwargs: Dict[str, Any]
        """
        if isinstance(command, ContextMenu):
            cmd = command.to_dict()
        route_kwargs = {
            "method": "DELETE",
            "endpoint": cmd['id']
        }
        kwargs.update(route_kwargs)
        route = self.get_route(**kwargs)
        try:
            await self.http.request(route)
            if cmd['name'] in self.registered.names:
                self.registered.remove(cmd['name'])
            self.ctx.logger.pprint(
                f"Unregistered command: {cmd['name']}",
                color='yellow'
            )
        except discord.HTTPException as excp:
            self.ctx.logger.pprint(
                excp, color='red'
            )

    async def execute(
        self, interaction: discord.Interaction
    ) -> Callable:
        """Parse the data into :class:`.components.ContextMenu`
        and executes its callback.

        :param interaction: Interaction to parse.
        :type interaction: :class:`discord.Interaction`
        :return: Parsed command method.
        :rtype: Callable
        """
        await interaction.response.defer()
        interaction = CustomInteraction(interaction)
        command = self.registered[interaction.data['name']]
        await command.callback(message=interaction)

    def get_route(self, method="POST", **kwargs):
        """Get the route for the query.

        :param method: HTTP Method to use.
        :type method: str
        """
        path = f"/applications/{self.ctx.user.id}/commands"
        if kwargs.get("endpoint"):
            path += f"/{kwargs['endpoint']}"
        return Route(
            method=method,
            path=path
        )

    async def register_command(
        self, callback: Callable,
        type_: Optional[int] = 2
    ) -> ContextMenu:
        """
        Register a context menu command.

        :param callback: The callback which gets executed upon interaction.
        :type callback: Callable
        :param type_: The type of the context menu command.
        :type type_: Optional[int]
        :return: The registered context menu command.
        :rtype: :class:`~.components.ContextMenu`
        """
        if not self.registered:
            await self.registered.refresh()
        cmd_name = callback.__name__.title().replace('Cmd_', '')
        if cmd_name in self.registered.names:
            if not self.registered[cmd_name].callback:
                self.registered[cmd_name].callback = callback
            return {}
        session = self.http
        payload = {
            "name": cmd_name,
            "type": type_
        }
        route = Route(
            'POST',
            f"/applications/{self.ctx.user.id}/commands",
            json=payload
        )
        self.ctx.logger.pprint(
            f"Registering the command: {payload['name']}",
            color='blue'
        )
        try:
            resp = await session.request(route, json=payload)
            self.update_counter += 1
            self.registered.append(
                ContextMenu.from_dict(
                    {**resp, "callback": callback}
                )
            )
            self.ctx.logger.pprint(
                f"Succesfully registered: {payload['name']}",
                color='green'
            )
            return self.registered[-1]
        except discord.HTTPException as excp:
            self.ctx.logger.pprint(
                excp, color='red'
            )
            return None

    async def register_all(self):
        """
        Registers all the decorated Context Menu commands.
        """
        for module in get_modules(self.ctx):
            for cmd in dir(module):
                if cmd.startswith('cmd_') and hasattr(
                    getattr(module, cmd), 'ctx_command'
                ):
                    await self.register_command(getattr(module, cmd))
        msg = f"Registered {len(self.registered)} commands."
        if not self.update_counter:
            msg = "No new context menu commands found."
        self.ctx.logger.pprint(msg, color='green')
