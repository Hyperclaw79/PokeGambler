"""
Control Commands Module
"""

# pylint: disable=unused-argument

import json
import subprocess
import time

import discord

from ..helpers.paginator import Paginator
from ..helpers.utils import (
    get_embed, get_enum_embed, get_modules
)
from .basecommand import (
    owner_only, maintenance, no_log, alias,
    Commands
)


class ControlCommands(Commands):
    '''
    Commands that control/interact with other commands.
    Examples: Togglers, Command Lister, Restart, Channel
    '''
    @owner_only
    @maintenance
    @no_log
    async def cmd_restart(self, **kwargs):
        """Closes session and spawns a new process.
        $```scss
        {command_prefix}restart
        ```$

        @`👑 Owner Command`
        Restarts the bot with local changes.@
        """
        await self.ctx.sess.close()
        await self.ctx.close()
        # Need to implement a way to kill the current process first.
        subprocess.run("python launcher.py", check=True)

    @owner_only
    @no_log
    async def cmd_toggle(self, message, args=None, **kwargs):
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
            "Guild_Mode": "guild_mode"
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
        self.ctx.user_changed.update({
            props[prop]: state
        })
        setattr(self.ctx, props[prop], state)
        await message.channel.send(
            embed=get_embed(
                f"Successfully toggled **{prop}** to `{str(state).title()}`."
            )
        )

    @owner_only
    @no_log
    @alias('tgl_mod_st')
    async def cmd_toggle_module_state(self, message, args=None, **kwargs):
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
        ] + ["config"]
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

    @owner_only
    @no_log
    async def cmd_reload(self, message, args=None, **kwargs):
        """Hot reload commands or configs.
        $```scss
        {command_prefix}reload module_name
        ```$

        @`👑 Owner Command`
        For hot reloading changes in a commands module/configs.@

        ~To reload changes in normalcommands:
            ```
            {command_prefix}reload normal
            ```
        To reload changes in Configs:
            ```
            {command_prefix}reload config
            ```~
        """
        if not args:
            return
        module = args[0].lower()
        possible_modules = [
            cmd.replace("commands", "")
            for cmd in dir(self.ctx)
            if cmd.endswith("commands") and cmd != "load_commands"
        ] + ["config"]
        if module not in possible_modules:
            embed = get_enum_embed(
                possible_modules,
                title="List of reloadable modules"
            )
            await message.channel.send(embed=embed)
        else:
            if module == "config":
                self.ctx.update_configs()
            else:
                self.ctx.load_commands(module, reload_module=True)
            await message.channel.send(
                embed=get_embed(f"Successfully reloaded {module}.")
            )

    @owner_only
    @no_log
    async def cmd_channel(self, message, args=None, **kwargs):
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
        else:
            if args and args[0].lower() == "list":
                await message.channel.send(
                    "\n".join(
                        f"{chan}({chan.id})"
                        for chan in self.ctx.active_channels
                    ) or "None."
                )

            elif args and args[0].lower() == "reset":
                self.ctx.active_channels = []
                self.logger.pprint(
                    "All channels have been succesfully reset.",
                    timestamp=True,
                    color="green"
                )

    @owner_only
    @no_log
    @alias('cmd_hist')
    async def cmd_command_history(self, message, args=None, **kwargs):
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
            {command_prefix}cmd_hist --user_is_admin
            ```~
        """
        def parse(cmd):
            user = self.ctx.get_user(int(cmd["user_id"]))
            is_admin = cmd["user_is_admin"]
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
        if kwargs:
            kwargs.pop("mentions")
        limit = 5
        if args:
            limit = int(args[0])
        history = self.database.get_command_history(limit=limit, **kwargs)
        if not history:
            await message.channel.send(
                embed=get_embed(
                    "No commands logged yet."
                )
            )
            return
        embeds = [parse(cmd) for cmd in history]
        base = await message.channel.send(embed=embeds[0])
        if len(embeds) > 1:
            pager = Paginator(message, base, embeds, self.ctx)
            await pager.run()

    @owner_only
    @no_log
    async def cmd_timeit(self, message, args=None, **kwargs):
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
    @alias('prg_cmds')
    async def cmd_purge_commands(self, message, **kwargs):
        """Purges the Commands table in the database.
         $```scss
        {command_prefix}purge_commands
        ```$

        @`👑 Owner Command`
        Purges the Commands table in the database.@

        ~To purge the commands table:
            ```
            {command_prefix}prg_cmds
            ```~
        """
        self.database.purge_commands()
        await message.add_reaction("👍")
