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

Normal Commands Module
"""

# pylint: disable=unused-argument

from __future__ import annotations
import re
from typing import Callable, Optional, TYPE_CHECKING

import discord

from ..base.models import CommandData, Profiles, Votes
from ..base.views import LinkView, MorphView
from ..helpers.parsers import CustomRstParser
from ..helpers.utils import (
    get_commands, get_embed, get_modules,
    dedent, showable_command
)
from .basecommand import alias, Commands, ctx_command, model

if TYPE_CHECKING:
    from discord import Message


class NormalCommands(Commands):
    """
    Public/Normal commands for PokeGambler.
    """

    @ctx_command
    @alias("cmds")
    async def cmd_commands(
        self, message: Message,
        module: Optional[str] = None,
        role: Optional[discord.Role] = None,
        **kwargs
    ):
        """
        :param message: The messag which triggered this command.
        :type message: :class:`discord.Message`
        :param module: The module to show commands for.
        :type module: Optional[str]
        :choices module: [Profile, Gamble, Duel, Normal, Trade, Control, Admin]
        :param role: The role to show commands for. (None/Admin/Owner)
        :type role: Optional[:class:`discord.Role`]

        .. meta::
            :description: Lists all usable commands for the user.
            :aliases: cmds

        .. rubric:: Syntax
        .. code:: coffee

            /commands [role:Role] [module:name]

        .. rubric:: Description

        Lists out all the commands you could use.

        .. note::

            Admins and Dealers get access to special hidden commands

        .. rubric:: Examples

        * To check the commands list

        .. code:: coffee
            :force:

            /commands

        * To check the commands specific to admin

        .. code:: coffee
            :force:

            /commands role:admin

        * To check only profile commands

        .. code:: coffee
            :force:

            /commands module:Profile
        """
        modules = get_modules(self.ctx)
        if module:
            modules = [
                mod
                for mod in modules
                if mod.__class__.__name__.lower().startswith(
                    module.lower()
                )
            ]
        command_dict = {
            module.__class__.__name__.replace(
                "Commands", " Commands"
            ): get_commands(
                self.ctx, message.author,
                module, [str(role) if role else None]
            )
            for module in modules
        }
        if set(command_dict.values()) == {''}:
            await message.reply(
                embed=get_embed(
                    "Did not find any commands for the given query.",
                    embed_type="warning",
                    title="No Commands found"
                )
            )
            return
        embed = get_embed(
            "Use `/help command:name` for details",
            title="PokeGambler Commands List"
        )
        embed_all = embed.copy()
        info_dict = {}
        for key, val in command_dict.items():
            if val:
                if not module:
                    emb_new = embed.copy()
                    emb_new.add_field(
                        name=key,
                        value=f"**```fix\n{val}\n```**"
                    )
                    info_dict[key] = emb_new
                embed_all.add_field(
                    name=key,
                    value=f"**```fix\n{val}\n```**"
                )
        if not module:
            info_dict["All Commands"] = embed_all
            morpher = MorphView(info_dict=info_dict)
            await message.reply(embed=embed, view=morpher)
            self.ctx.loop.create_task(morpher.dispatch(module=self))
        else:
            await message.reply(embed=embed_all)

    @alias("?")
    async def cmd_help(
        self, message: Message,
        command: Optional[str] = None,
        **kwargs
    ):
        """
        :param message: The messag which triggered this command.
        :type message: :class:`discord.Message`
        :param command: The command to get help for.
        :type command: Optional[str]

        .. meta::
            :description: What did you expect? This is just the Help command.
            :aliases: ?

        .. rubric:: Syntax
        .. code:: coffee

            /help [command:name]

        .. rubric:: Description

        Displays the help embed.
        If a command is specified, it prints a help message for that command.
        Otherwise, it lists the available commands.

        .. rubric:: Examples

        * To view help for a the profile command

        .. code:: coffee
            :force:

            /help command:profile

        * To view help for all the commands

        .. code:: coffee
            :force:

            /help
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
                        module.__class__.__name__ != 'TradeCommands'
                    ]
                )
            }
        )

        if command:
            commands = [
                cmd
                for cmd in commands
                if any([
                    cmd.__name__ == f"cmd_{command.lower()}",
                    command.lower() in getattr(cmd, "alias", [])
                ])
            ]
            if not commands:
                await message.reply(
                    embed=get_embed(
                        f"There's no command called **{command.title()}**\n"
                        "Or you don't have access to it.",
                        embed_type="error"
                    )
                )
                return
        embeds = []
        for cmd in commands:
            emb = self.__help_generate_embed(
                cmd, keep_footer=(command is not None)
            )
            embeds.append(emb)
        embeds.sort(key=lambda x: x.title)
        await self.paginate(
            message, embeds,
            content="**PokeGambler Commands List:**"
        )

    @model([Profiles, CommandData])
    async def cmd_info(self, message: Message, **kwargs):
        """
        :param message: The messag which triggered this command.
        :type message: :class:`discord.Message`

        .. meta::
            :description: Gives info about PokeGambler.

        .. rubric:: Syntax
        .. code:: coffee

            /info

        .. rubric:: Description

        Gives new players information about PokeGambler.
        """
        emb1 = self.__info_embed_one()
        emb2 = self.__info_embed_two()
        embeds = [emb1, emb2]
        await self.paginate(message, embeds)

    @ctx_command
    async def cmd_invite(self, message: Message, **kwargs):
        """
        :param message: The messag which triggered this command.
        :type message: :class:`discord.Message`

        .. meta::
            :description: Invite PokeGambler to other servers.

        .. rubric:: Syntax
        .. code:: coffee

            /invite

        .. rubric:: Description

        Get the Invite link for PokeGambler.
        """
        pg_den = self.ctx.get_guild(self.ctx.official_server)
        inv_emb = get_embed(
            dedent(
                f"""```md
                # Want to add me to your own server?
                [Invite me](By clicking the button below).
                * Following features are only allowed in {pg_den}:
                    * Gamble Matches
                    * Buying Titles
                    * Cross Trades
                ```"""
            ),
            title="Invite Link",
            image="https://cdn.discordapp.com/attachments/"
            "874623706339618827/874628993939308554/pg_banner.png"
        )
        invite_view = LinkView(
            emoji="<:pokegambler:844321894488342559>",
            url="https://discordapp.com/oauth2/authorize?client_id="
            f"{self.ctx.user.id}&scope=bot%20applications.commands"
            "&permissions=543179533392"
        )
        await message.reply(
            embed=inv_emb,
            view=invite_view
        )

    @ctx_command
    @alias('latency')
    async def cmd_ping(self, message: Message, **kwargs):
        """
        :param message: The messag which triggered this command.
        :type message: :class:`discord.Message`

        .. meta::
            :description: PokeGambler Latency

        .. rubric:: Syntax
        .. code:: coffee

            /ping

        .. rubric:: Description

        Checks the current latency of PokeGambler.
        """
        ping = round(self.ctx.latency * 1000, 2)
        await message.reply(
            embed=get_embed(
                f"**{ping}** ms",
                title="Current Latency"
            )
        )

    def __help_generate_embed(
        self, cmd: Callable,
        keep_footer: bool = False
    ):
        got_doc = False
        meta = {}
        aliases = ""
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
                "{pokechip_emoji}",
                self.chip_emoji
            )
            with CustomRstParser() as rst_parser:
                rst_parser.parse(doc_str)
                aliases = rst_parser.meta.aliases
                meta = {
                    section.argument: dedent(section.to_string())
                    for section in rst_parser.sections
                }
            emb = discord.Embed(
                title=cmd.__name__.replace("cmd_", "").title(),
                description='\u200B',
                color=11068923
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
                val = re.sub(
                    r'\\\|\\\|\~([^\\]+)\\\|\\\|',
                    lambda x: x[1].split('.')[-1],
                    '\n'.join(
                        m.lstrip()
                        for m in val.split('\n')
                    )
                )
                emb.add_field(name=f"**{key}**", value=val, inline=False)
        if all([
            got_doc,
            aliases
        ]):
            alt_names = aliases.split(', ')
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
            "874623706339618827/874628993939308554/pg_banner.png"
        )
        emb.add_field(
            name="**Getting Started**",
            value=dedent(
                """
                ```diff
                You can create a new profile using:
                    /profile
                Every players gets free 100 Pokechips
                For a list of commands you can access:
                    /commands
                For usage guide of these commands:
                    /help
                    🛈 Check the help for every command before using it.

                🛈 Also keep an eye out for sudden gambling matches.
                ```
                """
            ),
            inline=False
        )
        server_owner = self.ctx.get_guild(
            self.ctx.official_server
        ).owner
        emb.add_field(
            name="**Owners**",
            value=dedent(
                f"""
                ```yaml
                Bot Owner: {self.ctx.owner}
                Official Server Owner: {server_owner}
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
            "874623706339618827/874628993939308554/pg_banner.png"
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
            value=f"```yaml\n{self.__info_get_stats()}\n```",
            inline=False
        )
        return emb

    def __info_get_stats(self):
        """Get the stats of the bot."""
        handlers = {
            "Latency": lambda: f"{round(self.ctx.latency * 1000, 2)} ms",
            # pylint: disable=no-member
            "Total Users": Profiles.mongo.estimated_document_count,
            "Total Servers": lambda: len(self.ctx.guilds),
            "Most Active User": self.__info_most_active_user,
            "Most Voted By": lambda: self.__info_most_active_user(mode="vote"),
            "Most Active Channel": self.__info_most_active_channel,
            "Most Used Command": self.__info_most_used_command
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

    @staticmethod
    def __info_most_active_channel():
        top_channel = CommandData.most_active_channel()
        if top_channel is None:
            return None
        channel = top_channel['name']
        guild = top_channel['guild']['name']
        return f"{channel} ({guild})"

    def __info_most_active_user(self, mode: str = "command"):
        if mode == "vote":
            top_user = Votes.most_active_voter()
            metric = "total_votes"
        else:
            top_user = CommandData.most_active_user()
            metric = "num_cmds"
        if top_user is None:
            return None
        user = self.ctx.get_user(int(top_user['_id']))
        return f"{user} ({top_user[metric]})"

    def __info_most_used_command(self):
        top_command = CommandData.most_used_command()
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
