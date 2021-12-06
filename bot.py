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

The Main Module which serves as the brain of the code.
"""

# pylint: disable=no-member

from collections import namedtuple
import difflib
import importlib
from io import BytesIO
import os
import sys
import traceback
from datetime import datetime
from typing import Callable

import aiohttp
import discord
from discord import Message, Interaction
from discord.ext import tasks
from dotenv import load_dotenv
import topgg

from scripts.base.cardgen import CardGambler
from scripts.base.models import (
    Blacklist, CommandData, Inventory,
    Nitro, Profiles
)
from scripts.base.items import Item
from scripts.base.shop import PremiumShop, Shop
from scripts.base.handlers import ContextHandler, SlashHandler

from scripts.helpers.logger import CustomLogger
# pylint: disable=cyclic-import
from scripts.helpers.utils import (
    dm_send, get_ascii, get_commands,
    get_formatted_time, get_modules, is_admin, is_dealer,
    prettify_discord, get_embed, parse_command,
    get_rand_headers, is_owner, online_now
)


load_dotenv()


class PokeGambler(discord.AutoShardedClient):
    """
    PokeGambler: A Discord Bot using pokemon themed cards for gambling.
    Subclass of :class:`discord.Client` which serves as the base
    for PokeGambler bot.

    :param error_log_path: Path to the error log file.
    :type error_log_path: str
    :param assets_path: Path to the assets folder.
    :type assets_path: str

    .. _top.gg: https://top.gg/bot/873569713005953064
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, **kwargs):
        intents = discord.Intents.all()
        # pylint: disable=assigning-non-slot
        intents.presences = False
        super().__init__(intents=intents)
        self.version = "v1.2.0"
        self.error_log_path = kwargs["error_log_path"]
        self.assets_path = kwargs["assets_path"]
        self.__update_configs()
        # Defaults
        self.active_channels = []
        self.ready = False
        self.start_time = datetime.now()
        self.owner = None
        self.sess = None
        self.owner_mode = False
        self.cooldown_users = {}
        self.cooldown_cmds = {}
        self.loot_cd = {}
        self.pending_cmds = {}
        self.views = {}
        # Classes
        #: The :class:`~scripts.helpers.logger.CustomLogger` for PokeGambler.
        self.logger = CustomLogger(
            self.error_log_path
        )
        #: The :class:`~scripts.base.cardgen.CardGambler` for Gamble matches.
        self.dealer = CardGambler(self.assets_path)
        #: :class:`topgg.DBLClient` for handling votes and stats.
        #:
        #: .. tip:: Check out PokeGambler's `Top.gg`_  page.
        self.topgg = topgg.DBLClient(
            self, os.getenv('TOPGG_TOKEN')
        )
        #: The :class:`~scripts.base.handlers.SlashHandler` for handling
        #:  slash commands.
        self.slasher = SlashHandler(self)
        #: The :class:`~scripts.base.handlers.ContextHandler` for handling
        #:  context commands.
        self.ctx_cmds = ContextHandler(self)
        # Commands
        for module in os.listdir("scripts/commands"):
            if module.endswith("commands.py"):
                module_type = module.split("commands.py")[0]
                self.load_commands(module_type)

# Bot Base

    # pylint: disable=too-many-locals
    async def on_message(self, message: Message):
        """Called when a :class:`discord.Message` is created and sent.

        .. note::

            This requires :attr:`discord.Intents.messages`
            to be enabled.

        :param message: The message which triggered the event.
        :type message: :class:`discord.Message`
        """
        # Guild and Channel Checks
        if message.guild is None:
            await self.__no_dm_cmds(message)
            return
        if self.__bl_wl_check(message):
            return
    # Controller
        if message.content.lower().startswith(
            self.prefix.lower()
        ):
            proceed = await self.__pre_command_checks(message)
            if not proceed:
                return
            res = self.__get_method(message)
            method, cmd, args, option_dict, closest = res
            if not method:
                cmd_name = cmd.replace('cmd_', self.prefix)
                cmd_err_msg = f"Command `{cmd_name}` does not exist!"
                if closest:
                    cmd_err_msg += f"\nDid you mean `{closest}`?"
                await message.channel.send(
                    embed=get_embed(
                        cmd_err_msg,
                        embed_type="error",
                        title="Invalid Command"
                    )
                )
                return
            cmd_cd = getattr(method, "cooldown", None)
            if cmd_cd:
                on_cmd_cd = await self.__handle_cmd_cd(message, method, cmd_cd)
                if on_cmd_cd:
                    return
            kwargs = {
                "message": message,
                "args": args,
                "mentions": [],
                **option_dict
            }
            if message.mentions:
                kwargs["mentions"] = message.mentions
            await self.__exec_command(method, kwargs)

    async def on_interaction(self, interaction: Interaction):
        """
        | Called when an interaction happened.
        | This currently happens due to slash command invocations \
            or components being used.

        :param interaction: The interaction data.
        :type interaction: :class:`discord.Interaction`
        """
        if not 1 <= interaction.data.get('type', 0) <= 2:
            return
        if not interaction.guild or self.__bl_wl_check(interaction):
            return
        if interaction.data.get('type') == 1:
            method, kwargs = await self.slasher.parse_response(interaction)
            if not (method and kwargs):
                return
            await self.__exec_command(method, kwargs, is_interaction=True)
        elif interaction.data.get('type') in (2, 3):
            await self.ctx_cmds.execute(interaction)

# Connectors

    def run(self, *args, **kwargs):
        """A blocking call that abstracts away the event loop
        initialisation from you.

        If you want more control over the event loop then this
        function should not be used. Use :meth:`discord.Client.start` coroutine
        or :meth:`discord.Client.connect` + :meth:`discord.Client.login`.

        Roughly Equivalent to: ::

            try:
                loop.run_until_complete(start(*args, **kwargs))
            except KeyboardInterrupt:
                loop.run_until_complete(close())
                # cancel all tasks lingering
            finally:
                loop.close()

        .. warning::

            This function must be the last function to call due to the fact
            that it is blocking. That means that registration of events or
            anything being called after this function call will not execute
            until it returns.
        """

        super().run(os.getenv('TOKEN'), *args, **kwargs)

    async def on_guild_join(self, guild: discord.Guild):
        """Called when a :class:`discord.Guild` is either created
        by the :class:`PokeGambler` or when :class:`PokeGambler`
        joins a guild.

        .. note::

            This requires :attr:`discord.Intents.guilds` to be enabled.

        :param guild: The guild which added PokeGambler.
        :type guild: :class:`discord.Guild`
        """
        await self.__handle_guild_change("join", guild)

    async def on_guild_remove(self, guild: discord.Guild):
        """Called when a :class:`discord.Guild` is removed
        from the :class:`PokeGambler`.

        This happens through, but not limited to, these circumstances:

        - The client got banned.
        - The client got kicked.
        - The client left the guild.
        - The client or the guild owner deleted the guild.

        In order for this event to be invoked, :class:`PokeGambler` must have
        been part of the guild to begin with.
        (i.e. it is part of :class:`PokeGambler`.guilds)

        .. note::

            This requires :attr:`discord.Intents.guilds` to be enabled.

        :param guild: The guild which was removed from PokeGambler.
        :type guild: :class:`discord.Guild`
        """
        await self.__handle_guild_change("leave", guild)

    async def on_member_update(
        self, before: discord.Member,
        after: discord.Member
    ):
        """Called when a :class:`discord.Member` is updated.

        This event is called whenever a member's status,
        roles, or other attributes are updated.
        We will use this to sync Slash command permissions
        for new admins, dealers, etc.

        .. note::

            This requires :attr:`discord.Intents.guilds` to be enabled.

        :param before: The member before the update.
        :type before: :class:`discord.Member`
        :param after: The member after the update.
        :type after: :class:`discord.Member`
        """
        if not self.is_prod or after.guild.id != self.official_server:
            return
        commands = []
        allow = True
        if any([
            not is_dealer(before) and is_dealer(after),
            is_dealer(before) and not is_dealer(after)
        ]):
            for module in get_modules(self):
                commands.extend(
                    self.__get_commands(module, role="dealer")
                )
            allow = is_dealer(after)
        elif any([
            not is_admin(before) and is_admin(after),
            is_admin(before) and not is_admin(after)
        ]):
            for module in get_modules(self):
                commands.extend(
                    self.__get_commands(module, role="admin")
                )
            allow = is_admin(after)
        if commands:
            await self.slasher.sync_permissions(commands, after, allow)

    async def on_ready(self):
        """Called when the client is done preparing the data received
        from Discord. Usually after login is successful and the
        :class:`PokeGambler`.guilds and co. are filled up.

        .. warning::

            This function is not guaranteed to be the first event called.
            Likewise, this function is **not** guaranteed to only be called
            once. This library implements reconnection logic and thus will
            end up calling this event whenever a RESUME request fails.
        """
        if not getattr(self, "owner", False):
            self.owner = self.get_user(self.owner_id)
        headers = get_rand_headers()
        self.sess = aiohttp.ClientSession(loop=self.loop, headers=headers)
        self.__pprinter()
        self.ready = True
        Shop.refresh_tradables()
        PremiumShop.refresh_tradables()
        await self.topgg.post_guild_count()
        if self.is_prod or self.is_local:
            self.logger.pprint(
                "Syncing up the slash commands now.",
                color='blue'
            )
            kwargs = {}
            if self.is_local:
                kwargs["guild_id"] = self.whitelist_guilds[0]
            elif self.is_prod:
                kwargs["guild_id"] = self.official_server
            await self.slasher.add_slash_commands(**kwargs)
            self.logger.pprint(
                "Registering the context menu commands now.",
                color='blue'
            )
            await self.ctx_cmds.register_all()
        await online_now(self)
        game = discord.Game(
            f"with the strings of fate. | Check: {self.prefix}info"
        )
        await self.change_presence(activity=game)
        self.__reward_nitro_boosters.start()

    def load_commands(
        self, module_type: str,
        reload_module: bool = False
    ):
        """Hot Module Import for Commands.

        :param module_type: The module type to load.
        :type module_type: str
        :param reload_module: Whether the module is preloaded.
        :type reload_module: bool
        :return: The loaded module.
        :rtype: :class:`~scripts.commands.basecommand.Commands`
        """
        if reload_module:
            module = importlib.reload(
                sys.modules.get(f"scripts.commands.{module_type}commands")
            )
        else:
            module = importlib.import_module(
                f"scripts.commands.{module_type}commands"
            )
        cmd_class = getattr(module, f"{module_type.title()}Commands")
        if cmd_class.__name__ not in self.views:
            self.views[cmd_class.__name__] = []
        for view in self.views[cmd_class.__name__]:
            if not view.is_finished():
                view.notify = False
                view.stop()
        for locked_cmd in list(self.pending_cmds):
            if locked_cmd in dir(cmd_class):
                self.pending_cmds.pop(locked_cmd)
        cmd_obj = cmd_class(ctx=self)
        setattr(self, f"{module_type}commands", cmd_obj)
        return cmd_obj

# Private Methods

    def __bl_wl_check(self, message: Message):
        blacklist_checks = [
            self.channel_mode == "blacklist",
            message.channel.id in getattr(self, "blacklist_channels")
        ]
        whitelist_checks = [
            self.channel_mode == "whitelist",
            message.channel.id not in getattr(self, "whitelist_channels")
        ]
        blackguild_checks = [
            self.guild_mode == "blacklist",
            message.guild.id in getattr(self, "blacklist_guilds")
        ]
        whiteguild_checks = [
            self.guild_mode == "whitelist",
            message.guild.id not in getattr(self, "whitelist_guilds")
        ]
        return_checks = [
            all(blacklist_checks),
            all(whitelist_checks),
            all(blackguild_checks),
            all(whiteguild_checks)
        ]
        return any(return_checks)

    async def __exec_command(self, method, kwargs, is_interaction=False):
        try:
            message = kwargs["message"]
            opts = {
                key: val
                for key, val in kwargs.items()
                if key not in ("message", "mentions", "args")
            }
            cmd_name = method.__name__.replace("cmd_", "")
            if "no_log" not in dir(method) or not self.is_local:
                cmd_data = CommandData(
                    message.author, message, is_interaction,
                    cmd_name, hasattr(method, "admin_only"),
                    kwargs["args"], opts
                )
                cmd_data.save()
            task = method(**kwargs)
            # Decorators can return None
            if task:
                await task
        except Exception:  # pylint: disable=broad-except
            await self.__handle_error()

    @staticmethod
    def __get_commands(module, role="owner"):
        commands = []
        for attr in dir(module):
            if attr.startswith("cmd_") and attr not in getattr(
                module, "alias", []
            ):
                method = getattr(module, attr)
                if hasattr(method, f"{role}_only"):
                    commands.append(method)
        return commands

    def __get_method(self, message: Message):
        cleaned_content = message.clean_content
        for user in message.mentions:
            cleaned_content = cleaned_content.replace(
                f" @{user.name}", ""
            )
            cleaned_content = cleaned_content.replace(
                f" @{user.nick}", ""
            )
        parsed = parse_command(
            self.prefix,
            cleaned_content
        )
        cmd = f'cmd_{parsed["Command"]}'
        args = parsed["Args"]
        option_dict = parsed["Kwargs"]
        method = None
        all_cmds = []
        all_aliases = []
        for com in get_modules(self):
            if com.enabled:
                method = getattr(com, cmd, None)
                if method:
                    return method, cmd, args, option_dict, cmd
                all_cmds.extend([
                    cmd_name.replace(self.prefix, '')
                    for cmd_name in get_commands(
                        self, message.author, com
                    ).splitlines()
                ])
                all_aliases.extend([
                    alias.replace("cmd_", "")
                    for alias in com.alias
                ])
        all_cmd_names = all_cmds + all_aliases
        closest = difflib.get_close_matches(
            cmd.replace('cmd_', ''),
            all_cmd_names,
            n=1
        )
        closest = closest[0] if closest else None
        return method, cmd, args, option_dict, closest

    async def __no_dm_cmds(self, message: Message):
        if message.content.lower().startswith(
            self.prefix.lower()
        ):
            try:
                await message.channel.send(
                    embed=get_embed(
                        "I currently do not support commands in the DMs.\n"
                        "Please use the command in a server.",
                        embed_type="warning",
                        title="No Commands in DMs"
                    )
                )
            except discord.Forbidden:
                pass

    async def __handle_cd(self, message: Message):
        if is_owner(self, message.author):
            return False
        on_cooldown = self.cooldown_users.get(message.author, None)
        if on_cooldown and (
            datetime.now() - self.cooldown_users[message.author]
        ).total_seconds() < self.cooldown_time:
            await message.add_reaction("⌛")
            return True
        self.cooldown_users[message.author] = datetime.now()

    async def __handle_cmd_cd(
        self, message: Message,
        method: Callable,
        cooldown: int
    ) -> bool:
        self.cooldown_cmds[method] = self.cooldown_cmds.get(method, {})
        if message.author not in self.cooldown_cmds[method]:
            self.cooldown_cmds[method][message.author] = datetime.now()
        else:
            elapsed = (
                datetime.now() - self.cooldown_cmds[method][message.author]
            ).total_seconds()
            if elapsed < cooldown:
                await message.add_reaction("⌛")
                rem_time = get_formatted_time(cooldown - elapsed)
                await dm_send(
                    message, message.author,
                    embed=get_embed(
                        f"You need to wait {rem_time}"
                        " before reusing that command.",
                        embed_type="error",
                        title="Command On Cooldown"
                    )
                )
                return True
            self.cooldown_cmds[method].pop(message.author)
        return False

    @tasks.loop(hours=24)
    async def __reward_nitro_boosters(self):
        if all([
            (
                datetime.utcnow() - Nitro.get_last_rewarded()
            ).days >= 30,
            datetime.utcnow().day == 5,
            not os.getenv("IS_LOCAL"),
            self.is_prod
        ]):
            DummyMessage = namedtuple('Message', ['channel'])
            official_server = self.get_guild(self.official_server)
            boosters = official_server.premium_subscribers
            owner = official_server.get_member(
                self.owner_id
            )
            rewarded = []
            rewardboxes = []
            for booster in boosters:
                profile = Profiles(booster)
                nitro_box = Item.from_name(
                    "Nitro Booster Reward Box",
                    force_new=True
                )
                Inventory(booster).save(nitro_box.itemid)
                chan = discord.utils.get(
                    official_server.channels,
                    name='general',
                    category__name='PokéGambler'
                )
                message = DummyMessage(channel=chan)
                await dm_send(
                    message, booster,
                    content=f"Hey {booster.name},",
                    embed=get_embed(
                        f"Thanks for Boosting『**{official_server}**』this month"
                        f"!\nA『**{nitro_box}**』is added to your inventory.",
                        title="Monthly Server Booster Reward",
                        footer=f"ItemID: {nitro_box.itemid}",
                        image=nitro_box.asset_url,
                        color=profile.get('embed_color')
                    )
                )
                rewarded.append(booster)
                rewardboxes.append(nitro_box.itemid)
            Nitro(owner, rewarded, rewardboxes).save()

    def __pprinter(self):
        pretty = {
            itbl: prettify_discord(
                self,
                **{
                    "iterable": getattr(self, itbl),
                    "mode": itbl.split("_")[1].rstrip("s")
                }
            )
            for itbl in [
                "blacklist_channels", "whitelist_channels",
                "blacklist_guilds", "whitelist_guilds"
            ]
        }
        ver_ascii = get_ascii(self.version)
        self.logger.pprint(
            """
                \t██████╗  █████╗ ██╗  ██╗███████╗
                \t██╔══██╗██╔══██╗██║ ██╔╝██╔════╝
                \t██████╔╝██║  ██║█████═╝ █████╗
                \t██╔═══╝ ██║  ██║██╔═██╗ ██╔══╝
                \t██║     ╚█████╔╝██║ ╚██╗███████╗
                \t╚═╝      ╚════╝ ╚═╝  ╚═╝╚══════╝
            """,
            color=["yellow", "bold"],
            timestamp=False
        )
        self.logger.pprint(
            """
                ██████╗  █████╗  ███╗   ███╗██████╗ ██╗     ███████╗██████╗
                ██╔════╝ ██╔══██╗████╗ ████║██╔══██╗██║     ██╔════╝██╔══██╗
                ██║  ██╗ ███████║██╔████╔██║██████╦╝██║     █████╗  ██████╔╝
                ██║  ╚██╗██╔══██║██║╚██╔╝██║██╔══██╗██║     ██╔══╝  ██╔══██╗
                ╚██████╔╝██║  ██║██║ ╚═╝ ██║██████╦╝███████╗███████╗██║  ██║
                 ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚═╝╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝
            """,
            color=["red"],
            timestamp=False
        )
        self.logger.pprint(
            f"\n{ver_ascii}\n",
            color=["green", "bold"],
            timestamp=False
        )
        print(
            f"\t{self.logger.wrap('Owner:', color='blue')} "
            f"{self.owner} ({self.owner_id})\n\n"
            f"\t{self.logger.wrap('Bot Name:', color='blue')} {self.user}\n\n"
            f"\t{self.logger.wrap('Command Prefix:', color='blue')} "
            f"{self.prefix}\n\n"
            f"\t{self.logger.wrap('Blacklisted Channels', color='blue')}\n"
            "\t~~~~~~~~~~~~~~~~~~~~\n"
            f"\t{pretty['blacklist_channels']}\n\n"
            f"\t{self.logger.wrap('Whitelisted Channels', color='blue')}\n"
            "\t~~~~~~~~~~~~~~~~~~~~\n"
            f"\t{pretty['whitelist_channels']}\n\n"
            f"\t{self.logger.wrap('Blacklisted Servers', color='blue')}\n"
            "\t~~~~~~~~~~~~~~~~~~~\n"
            f"\t{pretty['blacklist_guilds']}\n\n"
            f"\t{self.logger.wrap('Whitelisted Servers', color='blue')}\n"
            "\t~~~~~~~~~~~~~~~~~~~\n"
            f"\t{pretty['whitelist_guilds']}\n\n"
            f"\t{self.logger.wrap('Default Channel Mode:', color='blue')} "
            f"{self.channel_mode}\n\n"
            f"\t{self.logger.wrap('Default Guild Mode:', color='blue')} "
            f"{self.guild_mode}\n\n"
        )

    async def __pre_command_checks(self, message):
        on_cooldown = await self.__handle_cd(message)
        if on_cooldown:
            return False
        if Blacklist.is_blacklisted(
            str(message.author.id)
        ) or message.author.bot:
            await message.add_reaction("🚫")
            return False
        if self.owner_mode and not is_owner(self, message.author):
            await message.channel.send(
                    embed=get_embed(
                        "PokeGambler is currently in **owner mode**.\n"
                        "Only the bot owner can use the commands.\n"
                        "Please try again later.",
                        embed_type="warning",
                        title="Owner Mode is active."
                    )
                )
            return False
        return True

    def __update_configs(self):
        """
        For dynamic config updates.
        """
        self.guild_mode = os.getenv(
            "DEFAULT_GUILDMODE",
            "blacklist"
        )
        self.channel_mode = os.getenv(
            "DEFAULT_CHANNELMODE",
            "blacklist"
        )
        self.prefix = os.getenv('COMMAND_PREFIX', '->')
        self.cooldown_time = int(os.getenv('COOLDOWN_TIME', "5"))
        self.is_prod = os.getenv('IS_PROD', "False") == "True"
        self.is_local = os.getenv('IS_LOCAL', "False") == "True"
        for cfg_id in (
            "discord_webhook_token",
            "discord_webhook_channel"
        ):
            setattr(self, cfg_id, os.getenv(cfg_id.upper()))
        for cfg_id in (
            "owner_id", "official_server",
            "admin_cmd_log_channel",
            "img_upload_channel",
            "error_log_channel"
        ):
            setattr(self, cfg_id, int(os.getenv(cfg_id.upper())))
        for itbl in (
            "blacklist_guilds", "whitelist_guilds",
            "blacklist_channels", "whitelist_channels",
            "allowed_users"
        ):
            val = []
            if os.getenv(itbl.upper(), None):
                val = [
                    int(itbl_id.strip())
                    for itbl_id in os.environ[itbl.upper()].split(', ')
                ]
            setattr(self, itbl, val)

    async def __handle_error(self):
        tb_obj = sys.exc_info()[2]
        tb_obj = traceback.format_exc()
        self.logger.pprint(
            tb_obj,
            timestamp=True,
            color="red"
        )
        err_msg = f"```py\n{tb_obj}\n```"
        if len(err_msg) > 2000:
            err_fl = discord.File(
                BytesIO(str(tb_obj).encode()),
                filename="error.py"
            )
            await self.get_channel(
                self.error_log_channel
            ).send(file=err_fl)
        else:
            await self.get_channel(
                self.error_log_channel
            ).send(err_msg)

    async def __handle_guild_change(self, event, guild):
        if not self.is_prod or not guild.name or guild.unavailable:
            return
        await self.topgg.post_guild_count()
        image = None
        if guild.banner:
            image = guild.banner.url
        elif guild.splash:
            image = guild.splash.url
        elif guild.icon:
            image = guild.icon.url
        action = 'Added to' if event == 'join' else 'Left'
        emb = get_embed(
            embed_type="info",
            title=f"{action} {guild}【{guild.id}】",
            image=image,
            color=(
                discord.Color.dark_red()
                if event != 'join' else None
            )
        )
        for attr in (
            "description", "owner",
            "member_count", "created_at"
        ):
            emb.add_field(
                name=attr.replace("_", " ").title(),
                value=str(getattr(guild, attr))
            )
        if guild.large:
            emb.color = discord.Colour.gold()
        jq_log_channel = discord.utils.get(
            self.get_guild(
                self.official_server
            ).text_channels,
            name="joined_guilds_log"
        )
        await jq_log_channel.send(embed=emb)
        if event == "join":
            chan = guild.system_channel or discord.utils.get(
                guild.text_channels, name="general"
            )
            if chan:
                try:
                    await chan.send(
                        embed=get_embed(
                            title="Thanks for adding me!",
                            content=f"See `{self.prefix}info` to get started.",
                            image="https://media.discordapp.net/attachments/"
                            "874623706339618827/874628993939308554/pg_banner.png"
                            "?width=640&height=360"
                        )
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass
