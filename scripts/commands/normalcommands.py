"""
Normal Commands Module
"""

# pylint: disable=unused-argument

from __future__ import annotations
from datetime import datetime, timedelta
import re
from typing import Callable, List, Optional, TYPE_CHECKING

import discord

from ..base.items import DB_CLIENT
from ..helpers.paginator import Paginator
from ..helpers.utils import (
    get_commands, get_embed, get_modules,
    dedent, showable_command
)
from .basecommand import alias, Commands

if TYPE_CHECKING:
    from discord import Message


class NormalCommands(Commands):
    """
    Public/Normal commands for PokeGambler.
    """

    @alias("cmds")
    async def cmd_commands(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """List all usable commands for the user.
        $```scss
        {command_prefix}commands [admin/owner/dealer] [--module name]
        ```$

        @Lists out all the commands you could use.
        *Admins and Dealers get access to special hidden commands.@

        ~To check the commands list:
            ```
            {command_prefix}commands
            ```
        To check the commands specific to admin:
            ```
            {command_prefix}commands admin
            ```
        To check only profile commands:
            ```
            {command_prefix}commands --module profile
            ```~
        """
        modules = get_modules(self.ctx)
        if kwargs.get("module"):
            modules = [
                mod
                for mod in modules
                if mod.__class__.__name__.lower().startswith(
                    kwargs["module"].lower()
                )
            ]
        command_dict = {
            module.__class__.__name__.replace(
                "Commands", " Commands"
            ): get_commands(self.ctx, message.author, module, args)
            for module in modules
        }
        if set(command_dict.values()) == {''}:
            await message.channel.send(
                embed=get_embed(
                    "Did not find ant commands for the given query.",
                    embed_type="warning",
                    title="No Commands found"
                )
            )
            return
        embed = get_embed(
            f"Use `{self.ctx.prefix}help [command name]` for details",
            title="PokeGambler Commands List"
        )
        for key, val in command_dict.items():
            if val:
                embed.add_field(name=key, value=f"**```fix\n{val}\n```**")
        embed.set_footer(
            text="This command helped? You can help me too by donating at "
            "https://www.paypal.me/hyperclaw79.",
            icon_url="https://emojipedia-us.s3.dualstack.us-west-1."
            "amazonaws.com/thumbs/160/facebook/105/money-bag_1f4b0.png"
        )
        await message.channel.send(embed=embed)

    @alias("?")
    async def cmd_help(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """What did you expect? This is just the Help command.
        $```scss
        {command_prefix}help [command]
        ```$

        @Prints a help message.
        If a command is specified, it prints a help message for that command.
        Otherwise, it lists the available commands.@

        ~To view help for a specific command, say, `total`:
            ```
            {command_prefix}help total
            ```
        To view help for all the commands:
            ```
            {command_prefix}help
            ```~
        """
        modules = get_modules(self.ctx)
        commands = list(
            {
                getattr(module, attr)
                for module in modules
                for attr in dir(module)
                if all(
                    [
                        module.enabled,
                        attr.startswith("cmd_"),
                        showable_command(
                            self.ctx, getattr(module, attr),
                            message.author
                        ),
                    ]
                )
            }
        )

        if args:
            commands = [
                cmd
                for cmd in commands
                if any([
                    cmd.__name__ == f"cmd_{args[0].lower()}",
                    args[0].lower() in getattr(cmd, "alias", [])
                ])
            ]
            if not commands:
                await message.channel.send(
                    embed=get_embed(
                        f"There's no command called **{args[0].title()}**\n"
                        "Or you don't have access to it.",
                        embed_type="error"
                    )
                )
                return
        embeds = []
        for i, cmd in enumerate(commands):
            if len(args) > 0:
                emb = self.__generate_help_embed(cmd, keep_footer=True)
            else:
                emb = self.__generate_help_embed(cmd)
                emb.set_footer(text=f"{i+1}/{len(commands)}")
            embeds.append(emb)
        base = await message.channel.send(
            content='**PokeGambler Commands List:**\n',
            embed=embeds[0]
        )
        if len(embeds) > 1:
            pager = Paginator(self.ctx, message, base, embeds)
            await pager.run(content='**PokeGambler Commands List:**\n')

    async def cmd_invite(self, message: Message, **kwargs):
        """Invite PokeGambler to other servers
        $```scss
        {command_prefix}invite
        ```$

        @Get the Invite link for PokeGambler.@
        """
        pg_den = self.ctx.get_guild(self.ctx.official_server)
        inv_emb = get_embed(
            dedent(
                f"""```md
                # Want to add me to your own server?
                [Invite me](By clicking the title of this embed).
                * Following features are only allowed in {pg_den}:
                    - Gamble Matches
                    - Buying Titles
                    - Cross Trades
                ```"""
            ),
            title="Invite Link",
            image="https://cdn.discordapp.com/attachments/"
            "840469669332516904/861292639857147914/pg_banner.png"
        )
        inv_emb.url = "https://discordapp.com/oauth2/authorize?client_id=" + \
            f"{self.ctx.user.id}&scope=bot&permissions=511040"
        await message.channel.send(
            embed=inv_emb
        )

    async def cmd_info(self, message: Message, **kwargs):
        """Gives info about PokeGambler
        $```scss
        {command_prefix}info
        ```$

        @Gives new players information about PokeGambler.@
        """
        emb1 = self.__info_embed_one()
        emb2 = self.__info_embed_two()
        embeds = [emb1, emb2]
        await self.paginate(message, embeds)

    @alias('latency')
    async def cmd_ping(self, message: Message, **kwargs):
        """PokeGambler Latency
        $```scss
        {command_prefix}ping
        ```$

        @Check the current latency of PokeGambler.@
        """
        ping = round(self.ctx.latency * 1000, 2)
        await message.channel.send(
            embed=get_embed(
                f"**{ping}** ms",
                title="Current Latency"
            )
        )

    def __generate_help_embed(
        self, cmd: Callable,
        keep_footer: bool = False
    ):
        got_doc = False
        meta = {}
        if cmd.__doc__:
            if getattr(cmd, "disabled", False):
                cmd_name = cmd.__name__.replace('cmd_', '').title()
                emb = get_embed(
                    f"**{cmd_name}** is under maintainence.\n"
                    "Details unavailable, so wait for updates.",
                    embed_type="warning",
                    title="Command under Maintainence."
                )
                return emb
            got_doc = True
            doc_str = cmd.__doc__.replace(
                "{command_prefix}",
                self.ctx.prefix
            ).replace(
                "{pokechip_emoji}",
                self.chip_emoji
            )
            patt = r"\$(?P<Syntax>[^\$]+)\$\s+" + \
                r"\@(?P<Description>[^\@]+)" + \
                r"\@(?:\s+\~(?P<Example>[^\~]+)\~)?"
            meta = re.search(patt, doc_str).groupdict()
            emb = discord.Embed(
                title=cmd.__name__.replace("cmd_", "").title(),
                description='\u200B',
                color=11068923
            )
            if "no_thumb" not in dir(cmd):
                emb.set_thumbnail(
                    url="https://cdn.discordapp.com/attachments/"
                    "840469669332516904/840469820180529202/"
                    "pokegambler_logo.png"
                )
        else:
            emb = get_embed(
                "No help message exists for this command.",
                embed_type="warning",
                title="No documentation found."
            )
        for key, val in meta.items():
            if val:
                val = val.replace("  ", " ")
                val = '\n'.join(
                    m.lstrip()
                    for m in val.split('\n')
                )
                emb.add_field(name=f"**{key}**", value=val, inline=False)
        if all([
            got_doc,
            "alias" in dir(cmd)
        ]):
            alt_names = cmd.alias[:]
            if cmd.__name__.replace("cmd_", "") not in alt_names:
                alt_names.append(cmd.__name__.replace("cmd_", ""))
            alias_str = ', '.join(sorted(alt_names, key=len))
            emb.add_field(
                name="**Alias**",
                value=f"```\n{alias_str}\n```"
            )
        if keep_footer and got_doc:
            emb.set_footer(
                text="This command helped? You can help me too "
                "by donating at https://www.paypal.me/hyperclaw79.",
                icon_url="https://emojipedia-us.s3.dualstack.us-west-1."
                "amazonaws.com/thumbs/160/facebook/105/money-bag_1f4b0.png"
            )
        return emb

    def __info_embed_one(self):
        emb = get_embed(
            dedent(
                """
                ```
                𝙋𝙤𝙠𝙚𝙂𝙖𝙢𝙗𝙡𝙚𝙧 uses pokemon themed playing cards
                for entertaining gambling matches.
                It has a dedicated currency and profile system.
                Earned Pokechips may be cross-traded.
                ```
                """
            ),
            title="**Welcome to PokeGambler**",
            image="https://cdn.discordapp.com/attachments/"
            "840469669332516904/861292639857147914/pg_banner.png"
        )
        emb.add_field(
            name="**Getting Started**",
            value=dedent(
                f"""
                ```diff
                You can create a new profile using:
                    {self.ctx.prefix}profile
                Every players gets free 100 Pokechips
                For a list of commands you can access:
                    {self.ctx.prefix}commands
                For usage guide of these commands:
                    {self.ctx.prefix}help
                🛈 Also keep an eye out for sudden gambling matches.
                ```
                """
            ),
            inline=False
        )
        emb.add_field(
            name="**Owners**",
            value=dedent(
                """
                ```yaml
                Bot Owner: Hyperclaw79#3476
                Official Server Owner: justrilrx#9692
                ```
                """
            ),
            inline=False
        )
        return emb

    def __info_embed_two(self):
        emb = get_embed(
            title="**Welcome to PokeGambler**",
            content="\u200B",
            image="https://cdn.discordapp.com/attachments/"
            "840469669332516904/861292639857147914/pg_banner.png"
        )
        official_server = self.ctx.get_guild(self.ctx.official_server)
        emb.add_field(
            name="**Official Server**",
            value="Come hang out with us in "
            f"[『{official_server}』](https://discord.gg/g4TmVyfwj4).",
            inline=False
        )
        emb.add_field(
            name="**Stats**",
            value=f"```yaml\n{self.__get_stats()}\n```",
            inline=False
        )
        return emb

    def __get_stats(self):
        """Get the stats of the bot."""
        handlers = {
            "Latency": lambda: f"{round(self.ctx.latency * 1000, 2)} ms",
            "Total Users": DB_CLIENT.profiles.count,
            "Total Servers": lambda: len(self.ctx.guilds),
            "Most Active User": self.__most_active_user,
            "Most Active Channel": self.__most_active_channel,
            "Most Used Command": self.__most_used_command
        }
        stats = {}
        for key, func in handlers.items():
            res = func()
            if res is not None:
                stats[key] = res
        stats = "\n".join(
            f"{key}: {val}"
            for key, val in stats.items()
        )
        return stats.encode('utf-8').decode('utf-8')

    def __most_active_user(self):
        top_user = next(
            DB_CLIENT.commanddata.aggregate([
                {
                    '$match': {
                        'used_at': {
                            '$gte': datetime.today() - timedelta(
                                weeks=1
                            )
                        },
                        'user_is_admin': False
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
        if top_user is None:
            return None
        user = self.ctx.get_user(int(top_user['_id']))
        return f"{user} ({top_user['num_cmds']})"

    def __most_active_channel(self):
        top_channel = next(
            DB_CLIENT.commanddata.aggregate([
                {
                    '$match': {
                        'used_at': {
                            '$gte': datetime.today() - timedelta(
                                weeks=1
                            )
                        },
                        'user_is_admin': False
                    }
                }, {
                    '$group': {
                        '_id': '$channel',
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
        if top_channel is None:
            return None
        channel = self.ctx.get_channel(int(top_channel['_id']))
        guild = self.ctx.get_guild(int(top_channel['guild']))
        return f"{channel} ({guild})"

    def __most_used_command(self):
        top_command = next(
            DB_CLIENT.commanddata.aggregate([
                {
                    '$match': {
                        'used_at': {
                            '$gte': datetime.today() - timedelta(
                                weeks=1
                            )
                        },
                        'user_is_admin': False
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
        if top_command is None:
            return None
        command = top_command['_id']
        modules = [
            module
            for module in get_modules(self.ctx)
            if f"cmd_{command}" in module.alias
        ]
        if modules:
            command = getattr(
                modules[0], f"cmd_{command}"
            ).__name__.replace("cmd_", "")
        return f"{command} ({top_command['num_cmds']})"
