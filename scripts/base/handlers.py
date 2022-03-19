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

# pylint: disable=no-member, too-many-lines

from __future__ import annotations
import inspect
import itertools
from typing import (
    TYPE_CHECKING, Any, Callable, Coroutine,
    Dict, List, Optional, Tuple, Type, Union
)

from cachetools import TTLCache
import discord
from discord.http import Route
from discord.app_commands import Choice

from scripts.base.enums import OptionTypes

from .components import (
    AppCommand, ContextMenu,
    GuildEvent, GuildEventType,
    SlashCommand
)

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

    def __str__(self) -> str:
        return str(self.channel)

    def __eq__(self, other: OverriddenChannel) -> bool:
        return self.channel.id == other.channel.id

    async def send(self, *args, **kwargs):
        """
        :meth:`discord.TextChannel.send` like behavior for
        :class:`~scripts.base.handlers.OverriddenChannel`.
        """
        msg = await self.channel.send(*args, **kwargs)
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

    def __str__(self) -> str:
        return str(self.interaction)

    def __eq__(self, other: CustomInteraction) -> bool:
        return self.interaction.id == other.interaction.id

    async def reply(self, *args, **kwargs):
        """
        :meth:`discord.Message.reply` like behavior for Interactions.
        """
        try:
            await self.interaction.response.send_message(
                *args, **kwargs
            )
            msg = await self.interaction.original_message()
        except discord.InteractionResponded:
            msg = await self.interaction.followup.send(
                *args, **kwargs
            )
        return msg

    async def add_reaction(self, reaction: str):
        """:meth:`discord.Message.add_reaction` like behavior for Interactions.

        :param reaction: The reaction to add.
        :type reaction: :class:`str`
        """
        # pylint: disable=import-outside-toplevel
        from ..base.views import EmojiButton

        emoji_btn = EmojiButton(reaction)
        payload = {
            "content": '\u200B',
            "view": emoji_btn,
            "ephemeral": True
        }
        try:
            await self.interaction.response.send_message(
                **payload
            )
        except discord.InteractionResponded:
            await self.interaction.followup.send(
                **payload
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
        return next(
            (
                command
                for command in self
                if command.name == item
            ), None
        )

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
            command = self.Component.from_dict(command)
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

    async def refresh(self, fresh=False, **kwargs):
        """
        Refreshes the command list.
        """
        if fresh:
            self.clear()
        route = self.handler.get_route('GET', **kwargs)
        commands = await self.handler.http.request(route)
        for command in commands:
            if command['type'] in self.Component.types():
                if 'options' in command:
                    for option in command['options']:
                        option['autocomplete'] = option.get(
                            'autocomplete', False
                        )
                if command['name'] not in self.names:
                    self.append(
                        self.handler.component_class.from_dict(command)
                    )


def command_to_dict(
    command: Callable,
    local: Optional[bool] = False
) -> Dict[str, Any]:
    """Convert a command to a dictionary.

    :param command: Command to convert.
    :type command: Callable
    :param local: Whether to use local or official server.
    :type local: Optional[bool]
    :return: Dictionary representation of the command.
    :rtype: Dict[str, Any]
    """
    description = command.__doc__.split("\n")[0]
    with CustomRstParser() as rst_parser:
        rst_parser.parse(command.__doc__)
        meta = rst_parser.meta
        options = rst_parser.parsed_params
    desc = meta.description
    if len(desc) <= 100:
        description = desc
    options = sorted(options, key=lambda x: -x['required'])
    # Fix for Discord API not supporting Default Option
    for option in options:
        option.pop('default', None)
    cmd_name = command.__name__.replace("cmd_", "")
    if local:
        cmd_name += "_"
    return {
        "name": cmd_name,
        "description": description,
        "type": 1,
        "options": options
    }


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
            current_commands.extend(
                getattr(module, attr)
                for attr in dir(module)
                if (
                    attr.startswith("cmd_")
                    and "no_slash" not in dir(
                        getattr(module, attr)
                    )
                )
            )
        current_commands = sorted(
            list(set(current_commands)),
            key=current_commands.index
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
        return next(
            (
                cmd
                for cmd in self.registered
                if cmd.name == command
            ), None
        )

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
        # await interaction.response.defer()
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
            param_names = rst_parser.param_names
        for opt in data.get('options', {}):
            if opt['name'] in param_names:
                if opt['type'] == OptionTypes.USER.value:
                    getter = interaction.guild.get_member
                    alt_getter = self.ctx.get_user
                elif opt['type'] == OptionTypes.CHANNEL.value:
                    getter = interaction.guild.get_channel
                    alt_getter = self.ctx.get_channel
                elif opt['type'] == OptionTypes.ROLE.value:
                    getter = interaction.guild.get_role
                    alt_getter = None
                elif opt['type'] == OptionTypes.ATTACHMENT.value:
                    getter = None
                    alt_getter = None
                    opt['value'] = discord.Attachment(
                        data=data['resolved']['attachments'][opt['value']],
                        # pylint: disable=protected-access
                        state=interaction._state
                    )
                else:
                    getter = None
                if getter:
                    opt['value'] = self.__get_entity(
                        int(opt['value']),
                        getter, alt_getter
                    )
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
        if hasattr(command, "os_only") and self.ctx.is_prod:
            route = self.get_route(guild_id=self.ctx.official_server)
        elif self.ctx.is_local:
            route = self.get_route(**kwargs)
        else:
            route = self.get_route()
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
                params = {
                    key: {
                        field: val
                        for field, val in param.parse().items()
                        if all([
                            val is not None,
                            # Fix for Discord API not supporting Default option
                            field != 'default'
                        ])
                    }
                    for key, param in rst_parser.params.items()
                    if key != 'message'
                }
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
        return command_to_dict(
            command, local=self.ctx.is_local
        )

    async def __sync_commands(self, current_commands, **kwargs):
        if not self.ctx.is_local:
            await self.registered.refresh(fresh=True)
        await self.registered.refresh(**kwargs)
        pad = '' if not self.ctx.is_local else '_'
        cmds = [
            cmd.__name__.replace('cmd_', '') + pad
            for cmd in current_commands
        ]
        for command in self.registered:
            if command.name not in cmds:
                await self.delete_command(command, **kwargs)

    @staticmethod
    def __get_entity(val, getter, alt_getter=None):
        id_ = int(val)
        alt_getter = alt_getter or getter
        return getter(id_) or alt_getter(id_)


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


class AutocompleteHandler:
    """Autocomplete handler for commands.

    :param ctx: The pokegambler client.
    :type ctx: :class:`bot.PokeGambler`
    """
    def __init__(self, ctx: PokeGambler):
        self.ctx = ctx
        self.commands = {}
        self.cache = TTLCache(maxsize=10, ttl=60)

    def register(
        self, cmd: Coroutine,
        callback_dict: Dict[str, Callable[
            [discord.Interaction], List[Any]
        ]]
    ):
        """Register a command with its choices.

        :param cmd: The command to register.
        :param callback_dict: The callback dictionary.
        """
        cmd_dict = command_to_dict(cmd, local=self.ctx.is_local)
        cmd = SlashCommand.from_dict(cmd_dict)
        self.commands[cmd] = callback_dict

    def unregister(self, cmd: SlashCommand):
        """Unregister a command.

        :param cmd: The command to unregister.
        :type cmd: :class:`~scripts.base.components.SlashCommand`
        """
        self.commands.pop(cmd, None)

    async def parse(
        self, interaction: discord.Interaction
    ) -> List[Choice]:
        """Get the choices for a command.

        :param interaction: The interaction to parse.
        :type interaction: :class:`discord.Interaction`
        :return: The choices for the command.
        :rtype: List[:class:`discord.app_commands.Choice`]
        """
        cmd = SlashCommand.from_dict(
            interaction.data
        )
        if cmd not in self.registered:
            return []
        focused_opt = [
            opt
            for opt in cmd.options
            if opt.get('focused', False)
        ]
        if not focused_opt:
            return []
        # Reset on empty input
        if focused_opt[0].get('value', '') == '':
            self.cache.pop(
                (cmd, focused_opt, interaction.user.id)
            )
        focused_opt = focused_opt[0].name
        choices = self.cache.get(
            (cmd, focused_opt, interaction.user.id)
        )
        if not choices:
            callable_ = self.commands[cmd][focused_opt]
            if inspect.iscoroutinefunction(callable_):
                choices = await callable_(interaction)
            else:
                choices = callable_(interaction)
            if len(choices) > 20:
                choices = iter(choices)
            self.cache[
                (cmd, focused_opt, interaction.user.id)
            ] = choices
        choice_list = [
            Choice(
                name=elem['name'],
                value=elem['value']
            )
            for elem in itertools.islice(choices, 20)
        ]
        await interaction.response.autocomplete(choice_list)
        return choice_list

    @property
    def registered(self) -> List[SlashCommand]:
        """Get the registered commands.

        :return: The registered commands.
        :rtype: List[:class:`~scripts.base.components.SlashCommand`]
        """
        return list(self.commands)


class GuildEventHandler:
    """Class which handles guild events.

    :param ctx: The pokegambler client.
    :type ctx: :class:`bot.PokeGambler`
    """
    def __init__(self, ctx: PokeGambler):
        self.ctx = ctx
        self.http = ctx.http

    async def list_events(self, guild_id: Union[int, str]) -> List[GuildEvent]:
        """List all the events for a guild.

        :param guild_id: The guild id.
        :type guild_id: Union[int, str]
        :return: The list of events.
        :rtype: List[:class:`~scripts.base.components.GuildEvent`]
        """
        route = Route(
            method="GET",
            path=f"/guilds/{guild_id}/scheduled-events"
        )
        try:
            resp = await self.http.request(route)
            return [
                GuildEvent.from_dict(event)
                for event in resp
            ]
        except discord.HTTPException as excp:
            self.ctx.logger.pprint(
                excp, color='red'
            )
            return None

    async def register_event(
        self, guild_id: Union[int, str],
        event: GuildEvent
    ) -> GuildEvent:
        """Register a guild event.

        :param guild_id: The guild id.
        :type guild_id: Union[int, str]
        :param event: The event to register.
        :type event: :class:`~scripts.base.components.GuildEvent`
        :return: The registered event.
        :rtype: :class:`~scripts.base.components.GuildEvent`
        """
        route = Route(
            method="POST",
            path=f"/guilds/{guild_id}/scheduled-events"
        )
        if not isinstance(event, GuildEvent):
            event = self.dict_to_event(event)
        try:
            resp = await self.http.request(route, json=event.to_payload())
            return GuildEvent.from_dict(resp)
        except discord.HTTPException as excp:
            self.ctx.logger.pprint(
                excp, color='red'
            )
            return None

    @staticmethod
    def dict_to_event(event: Dict) -> GuildEvent:
        """Convert a dict to a :class:`.components.GuildEvent`

        :param event: The dict to convert.
        :type event: Dict
        :return: The converted event.
        :rtype: :class:`~scripts.base.components.GuildEvent`
        """
        if "start" in event:
            event["scheduled_start_time"] = event.pop("start")
        if "end" in event:
            event["scheduled_end_time"] = event.pop("end")
        text_channel = event.pop("text_channel", None)
        voice_channel = event.pop("voice_channel", None)
        gevent = GuildEvent.from_dict(event)
        if text_channel:
            gevent.set_text_channel(str(text_channel))
        elif voice_channel:
            gevent.set_voice_channel(str(voice_channel))
        elif (
            gevent.entity_type == GuildEventType.EXTERNAL
            and (
                not gevent.entity_metadata
                or not gevent.entity_metadata.get('location')
            )
        ):
            gevent.entity_metadata = {
                'location': "Here"
            }
        return gevent
