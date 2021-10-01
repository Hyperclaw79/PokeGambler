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

Control Commands Module
"""

# pylint: disable=unused-argument

from __future__ import annotations
from io import BytesIO
import json
import time
from typing import (
    List, Optional, TYPE_CHECKING,
    Tuple, Type, Union
)

import discord

from ..base.items import Item
from ..base.models import (
    CommandData, Minigame,
    Model, UnlockedModel
)
from ..base.views import SelectView
from ..helpers.checks import user_check
from ..helpers.utils import (
    get_embed, get_enum_embed,
    get_modules, wait_for
)
from .basecommand import (
    ensure_args, model, owner_only, no_log,
    alias, Commands
)

if TYPE_CHECKING:
    from discord import Message


class ControlCommands(Commands):
    '''
    Commands that help in controlling PokeGambler.

    .. note::

        Only the Owners have access to these commands.
    '''

    @owner_only
    @no_log
    @ensure_args
    async def cmd_channel(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param args: The arguments for this command.
        :type args: List[option: str, channel_id: Optional[int]]

        .. meta::
            :description: Set the active channel for the commands.

        .. rubric:: Syntax
        .. code:: coffee

            {command_prefix}channel option [channel_id]

        .. rubric:: Description

        ``👑 Owner Command``
        Useful for redirecting echo command.
        Supported options

            * +/add/append: Add channel to active list.

            * -/remove/del/delete: Remove channel from active list.

            * list: Display active channels list.

            * reset: Reset active channels list.

        .. rubric:: Examples

        * To add channel with ID 1234

        .. code:: coffee
            :force:

            {command_prefix}channel + 1234

        * To remove channel with ID 1234

        .. code:: coffee
            :force:

            {command_prefix}channel - 1234

        * To display the active channels list

        .. code:: coffee
            :force:

            {command_prefix}channel list

        * To reset the active channels list

        .. code:: coffee
            :force:

            {command_prefix}channel reset
        """
        if len(args) >= 2:
            if args and all(dig.isdigit() for dig in args[1]):
                if args[0].lower() in ["+", "add", "append"]:
                    curr_chan = self.ctx.get_channel(int(args[1]))
                    self.ctx.active_channels.append(curr_chan)
                    self.logger.pprint(
                        f"Added {curr_chan}({curr_chan.id}) "
                        "as active channel.",
                        timestamp=True,
                        color="blue"
                    )
                elif args[0].lower() in ["-", "remove", "del", "delete"]:
                    curr_chan = self.ctx.get_channel(int(args[1]))
                    self.ctx.active_channels = [
                        chan
                        for chan in self.ctx.active_channels
                        if chan.id != curr_chan.id
                    ]
                    self.logger.pprint(
                        f"Removed {curr_chan}({curr_chan.id}) "
                        "from active channels.",
                        timestamp=True,
                        color="blue"
                    )
        elif args[0].lower() == "list":
            await message.channel.send(
                "\n".join(
                    f"{chan}({chan.id})"
                    for chan in self.ctx.active_channels
                ) or "None."
            )

        elif args[0].lower() == "reset":
            self.ctx.active_channels = []
            self.logger.pprint(
                "All channels have been succesfully reset.",
                timestamp=True,
                color="green"
            )

    @owner_only
    @no_log
    @model(CommandData)
    @alias('cmd_hist')
    async def cmd_command_history(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param args: The arguments for this command.
        :type args: List[limit: Optional[int]]
        :param kwargs: Extra Keyword arguments for this command.
        :type kwargs: Dict[filter: Optional[str]]

        .. meta::
            :description: Retrieves the latest command history based \
                on provided kwargs.
            :aliases: cmd_hist

        .. rubric:: Syntax
        .. code:: coffee

            {command_prefix}command_history [limit] [--filter param:value]

        .. rubric:: Description

        ``👑 Owner Command``
        Retrieves the latest command history based on provided kwargs.
        Defaults to a limit of 5 commands.
        Filter must be comma-separated key value pairs of format key:value.

        .. tip::

            Check :class:`~scripts.base.models.CommandData`
            for available parameters.

        .. rubric:: Examples

        * To retrieve the 10 latest commands

        .. code:: coffee
            :force:

            {command_prefix}cmd_hist 10

        * To retrieve latest commands used by admins

        .. code:: coffee
            :force:

            {command_prefix}cmd_hist --filter admin_cmd:True
        """
        if kwargs:
            kwargs.pop("mentions")
        limit = int(args[0]) if args else 5
        filter_ = kwargs.get("filter", '')
        cmd_kwargs = {
            param_str.strip().split(':')[0]: param_str.strip().split(':')[1]
            for param_str in filter_.split(',')
            if param_str
        }
        history = CommandData.history(limit=limit, **cmd_kwargs)
        if not history:
            await message.channel.send(
                embed=get_embed(
                    "No commands logged yet."
                )
            )
            return
        embeds = [self.__cmd_hist_parse(cmd) for cmd in history]
        await self.paginate(message, embeds)

    @owner_only
    @no_log
    # pylint: disable=no-self-use
    async def cmd_export_items(self, message: Message, **kwargs):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param kwargs: Extra Keyword arguments for this command.
        :type kwargs: Dict[pretty: Optional[int]]]

        .. meta::
            :description: Exports the :class:`~scripts.base.items.Item` \
                Collection as JSON.

        .. rubric:: Syntax
        .. code:: coffee

            {command_prefix}export_items [--pretty level]

        .. rubric:: Description

        ``👑 Owner Command``
        Exports the dynamically created items from the database as JSON.
        The JSON is uploaded as a file in the channel.
        A --pretty kwarg can be used to provide indentation level.

        .. rubric:: Examples

        * To export the items as a JSON file

        .. code:: coffee
            :force:

            {command_prefix}export_items

        * To see a pretty version of items JSON file

        .. code:: coffee
            :force:

            {command_prefix}export_items --pretty 3
        """
        items = Item.get_unique_items()
        for item in items:
            item.pop("created_on", None)
        jsonified = json.dumps(
            items,
            indent=kwargs.get("pretty"),
            sort_keys=False
        )
        byio = BytesIO()
        byio.write(jsonified.encode())
        byio.seek(0)
        export_fl = discord.File(byio, "items.json")
        await message.channel.send(file=export_fl)

    @owner_only
    @no_log
    async def cmd_import_items(self, message: Message, **kwargs):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`

        .. meta::
            :description: Imports the items from a JSON file.

        .. rubric:: Syntax
        .. code:: coffee

            {command_prefix}import_items

        .. rubric:: Description

        ``👑 Owner Command``
        Waits for JSON file attachment and loads the data
        into the Items collection.

        .. warning::
            Do not import :class:`~scripts.base.items.Rewardbox` using this.
        """
        info_msg = await message.channel.send(
            embed=get_embed(
                "Send an empty message with a JSON file attachment.",
                title="Attach items.json"
            )
        )
        user_inp = await wait_for(
            message.channel, self.ctx,
            init_msg=info_msg,
            check=lambda msg: (
                user_check(msg, message)
                and len(msg.attachments) > 0
                and msg.attachments[0].filename == "items.json"
            ),
            timeout="inf"
        )
        data_bytes = await user_inp.attachments[0].read()
        data = json.loads(data_bytes.decode())
        Item.insert_many(data)
        await user_inp.add_reaction("👍")

    @owner_only
    @no_log
    async def cmd_latest(self, message: Message, **kwargs):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param kwargs: Extra Keyword arguments for this command.
        :type kwargs: Dict[limit: Optional[int]]]

        .. meta::
            :description: Retrieves the latest documents \
                from a Collection.

        .. rubric:: Syntax
        .. code:: coffee

            {command_prefix}latest [--limit limit]

        .. rubric:: Description

        ``👑 Owner Command``
        Retrieves the latest documents from a Collection.
        Defaults to a limit of 5 documents.
        """
        locked, unlocked = self.__get_collections()
        cltn = await self.__get_model_view(
            message, (locked + unlocked)
        )
        if not cltn:
            return
        limit = int(kwargs.get("limit", 5))
        documents = cltn.latest(limit=limit)
        if not documents:
            await message.channel.send(
                embed=get_embed(
                    title="No documents found.",
                    embed_type="warning"
                )
            )
            return
        embeds = []
        for doc in documents:
            emb = get_embed(
                title=f"Latest entries from {cltn.__name__}"
            )
            for key, val in doc.items():
                if key in [
                    "background", "asset_url"
                ]:
                    if val:
                        emb.set_thumbnail(url=val)
                    continue
                emb.add_field(
                    name=key,
                    value=str(val)
                )
            embeds.append(emb)
        await self.paginate(message, embeds)

    @owner_only
    @no_log
    @alias('prg_tbl')
    async def cmd_purge_tables(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param args: The table name to purge.
        :type args: List[table: Optional[str]]

        .. meta::
            :description: Purges the tables in the database.
            :aliases: prg_tbl

        .. rubric:: Syntax
        .. code:: coffee

            {command_prefix}purge_tables [table_name]

        .. rubric:: Description

        ``👑 Owner Command``
        Purges the tables in the database.
        If no table name is given, purges all the tables.

        .. rubric:: Examples

        * To purge the profiles table

        .. code:: coffee
            :force:

            {command_prefix}purge_tables profiles

        * To purge all the tables

        .. code:: coffee
            :force:

            {command_prefix}purge_tables
        """
        locked, unlocked = self.__get_collections()
        if kwargs.get("all", False):
            collections = locked + unlocked
        else:
            cltn = await self.__get_model_view(
                message, (locked + unlocked)
            )
            if not cltn:
                return
            collections = [cltn]
        for cls in collections:
            purger = (
                cls.purge if cls in locked
                else cls.reset_all
            )
            purger()
        await message.add_reaction("👍")

    @owner_only
    @no_log
    @ensure_args
    async def cmd_reload(
        self, message: Message,
        args: List[str] = None,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param args: The module name to reload.
        :type args: List[module: str]

        .. meta::
            :description: Reloads a command module.

        .. rubric:: Syntax
        .. code:: coffee

            {command_prefix}reload module_name

        .. rubric:: Description

        ``👑 Owner Command``
        Hot reloads a command module without having to restart.

        .. rubric:: Examples

        * To reload the Normalcommands module

        .. code:: coffee
            :force:

            {command_prefix}reload normal
        """
        module = args[0].lower()
        possible_modules = [
            cmd.replace("commands", "")
            for cmd in dir(self.ctx)
            if cmd.endswith("commands") and cmd != "load_commands"
        ]
        if module not in possible_modules:
            embed = get_enum_embed(
                possible_modules,
                title="List of reloadable modules"
            )
            await message.channel.send(embed=embed)
        else:
            self.ctx.load_commands(module, reload_module=True)
            await message.channel.send(
                embed=get_embed(f"Successfully reloaded {module}.")
            )

    @owner_only
    @no_log
    @ensure_args
    async def cmd_timeit(
        self, message: Message,
        args: List[str] = None,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param args: The command name to time.
        :type args: List[command: str]

        .. meta::
            :description: Executes a command and displays time taken to run it.

        .. rubric:: Syntax
        .. code:: coffee

            {command_prefix}timeit cmd_name

        .. rubric:: Description

        ``👑 Owner Command``
        A utility commands that is used for timing other commands.

        .. rubric:: Examples

        * To time the leaderboard command

        .. code:: coffee
            :force:

            {command_prefix}timeit lb
        """
        modules = get_modules(self.ctx)
        cmd = args[0].lower()
        for module in modules:
            command = getattr(
                module,
                f"cmd_{cmd}",
                None
            )
            if command:
                break
        kwargs["args"] = args[1:]
        start = time.time()
        await command(message=message, **kwargs)
        end = time.time()
        tot = round(end - start, 2)
        await message.channel.send(
            embed=get_embed(
                f"Command `{self.ctx.prefix}{cmd}` "
                f"took **{tot}** seconds to execute."
            )
        )

    @owner_only
    @no_log
    async def cmd_toggle(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param args: The property to toggle and to which state.
        :type args: List[property: str, state: Optional[str]]

        .. meta::
            :description: Toggle a boolean property of the PokeGambler class.

        .. rubric:: Syntax
        .. code:: coffee

            {command_prefix}toggle property [state]

        .. rubric:: Description

        ``👑 Owner Command``
        Toggle some of the config options dynamically.
        Currently, the supported properties are:

            * guildmode

            * channelmode

        The available states are:

            * enable/on/whitelist

            * disable/off/blacklist

        .. warning::

            This command will be deprecated in the future.

        .. rubric:: Examples

        To switch the channel mode

        .. code:: coffee
            :force:

            {command_prefix}toggle channelmode

        To switch the guild mode to whitelist mode

        .. code:: coffee
            :force:

            {command_prefix}toggle guildmode whitelist
        """
        props = {
            "Channel_Mode": "channel_mode",
            "Guild_Mode": "guild_mode",
            "Owner_Mode": "owner_mode"
        }
        if args:
            if len(args) >= 2:
                prop = args[0].title()
                state = args[1].lower()
            elif len(args) == 1:
                prop = args[0].title()
                state = None
        else:
            await message.channel.send(
                embed=get_enum_embed(
                    list(props),
                    title="List of Possible Options"
                )
            )
            return
        if prop not in list(props):
            await message.channel.send(
                embed=get_enum_embed(
                    list(props),
                    title="List of Possible Options"
                )
            )
            return
        bool_toggles = ["enable", "on", "disable", "off"]
        str_toggles = ["whitelist", "blacklist"]
        possible_states = bool_toggles + str_toggles
        if state in bool_toggles:
            state = bool_toggles.index(state) < 2
        elif state in str_toggles:
            if prop not in ["Guild_Mode", "Channel_Mode"]:
                await message.channel.send(
                    embed=get_enum_embed(
                        list(props)[2:4],
                        title="List of Possible Options"
                    )
                )
                return
        elif state is None:
            if getattr(self.ctx, props[prop], None) not in [
                "whitelist", "blacklist"
            ]:
                state = not getattr(self.ctx, props[prop])
            else:
                state = str_toggles[
                    1 - str_toggles.index(
                        getattr(self.ctx, props[prop])
                    )
                ]
        else:
            embed = get_enum_embed(
                possible_states,
                title="Possible toggle states"
            )
            await message.channel.send(embed=embed)
            return
        setattr(self.ctx, props[prop], state)
        await message.channel.send(
            embed=get_embed(
                f"Successfully toggled **{prop}** to `{str(state).title()}`."
            )
        )

    @owner_only
    @no_log
    @alias('tgl_mod_st')
    async def cmd_toggle_module_state(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param args: The command module to toggle and to which state.
        :type args: List[module: str, state: Optional[str]]

        .. meta::
            :description: Enable or Disable different command modules.
            :aliases: tgl_mod_st

        .. rubric:: Syntax
        .. code:: coffee

            {command_prefix}toggle_module_state module_name state

        .. rubric:: Description

        ``👑 Owner Command``
        Enable or disable (eg. during maintenance) a command module.
        The available states are:

            * on/enable

            * off/disable

        .. rubric:: Examples

        To enable the Controlcommands module

        .. code:: coffee
            :force:

            {command_prefix}tgl_mod_st control on

        To disable the Normalcommands module

        .. code:: coffee
            :force:

            {command_prefix}tgl_mod_st normal off
        """
        if args:
            if len(args) >= 2:
                module = args[0].lower()
                state = args[1].lower()
            elif len(args) == 1:
                module = args[0].lower()
                state = "enable"
        else:
            module = ""
            state = "enable"
        possible_states = ["enable", "on", "disable", "off"]
        if state in possible_states:
            enable = possible_states.index(state) < 2
        else:
            embed = get_enum_embed(
                possible_states,
                title="Possible toggle states"
            )
            await message.channel.send(embed=embed)
        possible_modules = [
            cmd.replace("commands", "")
            for cmd in dir(self.ctx)
            if cmd.endswith("commands") and cmd != "load_commands"
        ]
        if module not in possible_modules:
            embed = get_enum_embed(
                possible_modules,
                title="List of toggleable modules"
            )
            await message.channel.send(embed=embed)
        else:
            getattr(self.ctx, f"{module}commands").enabled = enable
            await message.channel.send(
                embed=get_embed(f"Successfully switched {module} to {state}.")
            )

    def __cmd_hist_parse(self, cmd):
        user = self.ctx.get_user(int(cmd["user_id"]))
        is_admin = cmd["admin_cmd"]
        channel = cmd["channel"]["name"]
        guild = cmd["guild"]["name"]
        timestamp = cmd["used_at"].strftime("%Y-%m-%d %H:%M:%S")
        emb = discord.Embed(
            title="Command History",
            description='\u200B'
        )
        emb.add_field(
            name="Command",
            value=f'**{self.ctx.prefix}{cmd["command"]}**',
            inline=True
        )
        emb.add_field(
            name="Used By",
            value=user,
            inline=True
        )
        emb.add_field(
            name="Is Admin",
            value=is_admin,
            inline=True
        )
        emb.add_field(
            name="Channel",
            value=channel,
            inline=True
        )
        emb.add_field(
            name="Guild",
            value=guild,
            inline=True
        )
        emb.add_field(
            name="Args",
            value=cmd["args"] or "None",
            inline=True
        )
        if cmd["kwargs"]:
            kwarg_json = json.dumps(cmd["kwargs"], indent=3)
            emb.add_field(
                name="Kwargs",
                value=f'```json\n{kwarg_json}\n```',
                inline=True
            )
        emb.set_footer(
            text=f"Command was used at {timestamp}."
        )
        return emb

    @staticmethod
    def __get_collections() -> Tuple[List]:
        locked = [
            cls
            for cls in Model.__subclasses__()
            if cls not in (UnlockedModel, Minigame)
        ] + [Item]
        unlocked = UnlockedModel.__subclasses__()
        locked.extend(Minigame.__subclasses__())
        return locked, unlocked

    @staticmethod
    async def __get_model_view(
        message: Message,
        models: List[Union[Type[Item], Type[Model]]],
        content: str = None
    ) -> Union[Union[Type[Item], Type[Model]]]:
        choices_view = SelectView(
            heading="Select a Collection",
            options={
                opt: ""
                for opt in sorted(
                    models,
                    key=lambda x: x.__name__
                )
            },
            serializer=lambda x: x.__name__
        )
        await message.channel.send(
            "Which table do you wanna select?",
            view=choices_view
        )
        await choices_view.wait()
        return choices_view.result
