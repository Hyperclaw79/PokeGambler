"""
Normal Commands Module
"""

# pylint: disable=unused-argument

from __future__ import annotations
import os
import re
from typing import Callable, List, Optional, TYPE_CHECKING

import discord

from ..helpers.paginator import Paginator
from ..helpers.utils import (
    get_commands, get_embed, get_modules,
    dedent, showable_command
)
from .basecommand import alias, Commands

if TYPE_CHECKING:
    from discord import Message, Member


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
        if kwargs.get("module", None):
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

    @alias('$')
    async def cmd_donate(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """Feel free to buy me a cup of coffee, thanks!
        $```scss
        {command_prefix}donate [amount in USD]
        ```$

        @Opens a donation window on your browser where you can support me.@
        """
        amt = 10
        if len(args) > 0 and args[0].isdigit():
            amt = int(args[0])
        emb = discord.Embed(
            title="**Thank you very much for you generosity.**",
            color=16766720,
            url=f"https://www.paypal.com/paypalme2/hyperclaw79/{amt}"
        )
        emb.set_image(
            url="https://cdn.discordapp.com/attachments/840469669332516904/"
            "840469820180529202/pokegambler_logo.png"
        )
        await message.channel.send(embed=emb)
        _ = os.system(
            f'start https://www.paypal.com/paypalme2/hyperclaw79/{amt}'
        )

    # pylint: disable=missing-function-docstring
    async def cmd_invite(self, message: Message, **kwargs):
        await message.channel.send(
            embed=get_embed(
                "I am a private bot and cannot be invited to other servers.\n"
                "Why not just get your friends to this server instead? :wink:",
                embed_type="warning",
                title="Cannot Join Other Servers"
            )
        )

    async def cmd_info(self, message: Message, **kwargs):
        # BETA: Modify info before release.
        """Gives info about PokeGambler
        $```scss
        {command_prefix}info
        ```$

        @Gives new players information about PokeGambler.@
        """
        emb = get_embed(
            dedent(
                """
                > Welcome to the first `BETA` test of PokeGambler.
                **PokeGambler** uses pokemon themed playing cards
                for entertaining gambling matches.
                It has a dedicated currency and profile system.
                Earned Pokechips may be cashed out for Poketwo credits.
                """
            ),
            title="**Welcome to PokeGambler**"
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

                Also keep an eye out for sudden gambling matches.
                ```
                """
            ),
            inline=False
        )
        emb.add_field(
            name="**Owners**",
            value=dedent(
                """
                ```py
                Bot Owner: 'Hyperclaw79#3476'
                Server Owner: 'justrilrx#9692'
                ```
                """
            ),
            inline=True
        )
        emb.add_field(
            name="**Stats**",
            value="`Disabled during BETA`",
            inline=True
        )
        emb.set_image(
            url="https://cdn.discordapp.com/attachments/"
            "840469669332516904/843077048435736586/banner.jpg"
        )
        await message.channel.send(embed=emb)

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
            alt_names = getattr(cmd, "alias")[:]
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
