"""
Control Commands Module
"""

# pylint: disable=unused-argument

from __future__ import annotations
from io import BytesIO
import json
import time
from typing import List, Optional, TYPE_CHECKING

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
    model, owner_only, no_log,
    alias, Commands
)

if TYPE_CHECKING:
    from discord import Message


class ControlCommands(Commands):
    '''
    Commands that control/interact with other commands.
    Examples: Togglers, Command Lister, Restart, Channel
    '''

    @owner_only
    @no_log
    async def cmd_channel(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """Set the active channel for the commands.
        $```scss
        {command_prefix}channel [+/add/append] channel_id
        {command_prefix}channel [-/remove/del/delete] channel_id
        {command_prefix}channel list
        {command_prefix}channel reset
        ```$

        @`👑 Owner Command`
        Useful for redirecting echo command.@

        ~To add channel with ID 1234 to selected channels list:
            ```
            {command_prefix}channel + 1234
            ```
        To remove channel with ID 1234 from selected channels list:
            ```
            {command_prefix}channel - 1234
            ```
        To display the selected channels list:
            ```
            {command_prefix}channel list
            ```
        To reset the selected channels list:
            ```
            {command_prefix}channel reset
            ```~
        """
        if not args:
            return
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
        """Retrieves the latest command history based on provided kwargs.
        $```scss
        {command_prefix}command_history [limit]
        ```$

        @`👑 Owner Command`
        Retrieves the latest command history based on provided kwargs.
        Defaults to a limit of 5 commands.@

        ~To retrieve the 10 latest commands:
            ```
            {command_prefix}cmd_hist 10
            ```
        To retrieve latest commands used by admins:
            ```
            {command_prefix}cmd_hist --admin_cmd
            ```~
        """
        if kwargs:
            kwargs.pop("mentions")
        limit = int(args[0]) if args else 5
        history = CommandData.history(limit=limit, **kwargs)
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
    async def cmd_export_items(self, message: Message, **kwargs):
        """Items Table Exporter.
         $```scss
        {command_prefix}export_items [--pretty level]
        ```$

        @`👑 Owner Command`
        Exports the dynamically created items from the database as JSON.
        The JSON is uploaded as a file in the channel.
        A --pretty kwarg can be used to provide indentation level.@

        ~To export the items as a JSON file:
            ```
            {command_prefix}export_items
            ```
        To see a pretty version of items JSON file:
         ```
            {command_prefix}export_items --pretty 3
            ```~
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
        """Items Table Importer.
         $```scss
        {command_prefix}import_items
        ```$

        @`👑 Owner Command`
        Waits for JSON file attachment and loads the data into Items table.
        Attachment's name should be `items.json`.
        :warning: Do not import Reward Boxes using this.@
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
    @alias('prg_tbl')
    async def cmd_purge_tables(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """Purges the tables in the database.
         $```scss
        {command_prefix}purge_tables [table_name]
        ```$

        @`👑 Owner Command`
        Purges the tables in the database.
        If no table name is given, purges all the tables.@

        ~To purge the profiles table:
            ```
            {command_prefix}prg_tbl profiles
            ```
        ~To purge all the tables:
            ```
            {command_prefix}prg_tbl
            ```~
        """
        to_delete = [
            cls
            for cls in Model.__subclasses__()
            if cls not in (UnlockedModel, Minigame)
        ] + [Item]
        to_reset = UnlockedModel.__subclasses__()
        to_delete.extend(Minigame.__subclasses__())
        if kwargs.get("all", False):
            collections = to_delete + to_reset
        else:
            choices_view = SelectView(
                heading="Select a Collection",
                options={
                    opt: ""
                    for opt in sorted(
                        to_delete + to_reset,
                        key=lambda x: x.__name__
                    )
                },
                serializer=lambda x: x.__name__
            )
            await message.channel.send(
                "Which table do you wanna purge?",
                view=choices_view
            )
            await choices_view.wait()
            cltn = choices_view.result
            if not cltn:
                return
            collections = [cltn]
        for cls in collections:
            purger = (
                cls.purge if cls in to_delete
                else cls.reset_all
            )
            purger()
        await message.add_reaction("👍")

    @owner_only
    @no_log
    async def cmd_reload(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """Hot reload commands.
        $```scss
        {command_prefix}reload module_name
        ```$

        @`👑 Owner Command`
        For hot reloading changes in a commands module.@

        ~To reload changes in normalcommands:
            ```
            {command_prefix}reload normal
            ```~
        """
        if not args:
            return
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
    async def cmd_timeit(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """Executes a command and displays time taken to run it.
        $```scss
        {command_prefix}timeit cmd_name
        ```$

        @`👑 Owner Command`
        A utility commands that is used for timing other commands.@

        ~To time the leaderboard command:
            ```
            {command_prefix}timeit lb
            ```~
        """
        if not args:
            return
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
        """Toggle a boolean property of the PokeGambler class.
        $```scss
        {command_prefix}toggle property [on/enable/whitelist]
        {command_prefix}toggle property [off/disable/blacklist]
        ```$

        @`👑 Owner Command`
        Toggle some of the config options dynamically.
        Currently, you can toggle: Channel_Mode, Guild_Mode@

        ~To enable the autologging:
            ```
            {command_prefix}toggle autolog enable
            ```
        To operate in Whitelist Guild mode:
            ```
            {command_prefix}toggle guildmode whitelist
            ```~
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
        """Enable or Disable different command modules.
        $```scss
        {command_prefix}toggle_module_state module_name [on/off]
        ```$

        @`👑 Owner Command`
        For enabling or disabling a commands module (during maintainence).@

        ~To enable the Controlcommands module:
            ```
            {command_prefix}toggle_module_state control enable
            ```
        To disable the Normalcommands module:
            ```
            {command_prefix}toggle_module_state normal disable
            ```~
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
        channel = self.ctx.get_channel(int(cmd["channel"]))
        guild = self.ctx.get_guild(int(cmd["guild"]))
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
