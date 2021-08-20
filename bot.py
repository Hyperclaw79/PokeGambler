"""
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
from discord import Message
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
from scripts.helpers.logger import CustomLogger
# pylint: disable=cyclic-import
from scripts.helpers.utils import (
    dm_send, get_ascii, get_commands,
    get_formatted_time, get_modules,
    prettify_discord, get_embed, parse_command,
    get_rand_headers, is_owner, online_now
)


load_dotenv()


class PokeGambler(discord.AutoShardedClient):
    """PokeGambler: A Discord Bot using pokemon themed cards for gambling.
    Subclass of discord.Client which serves as the base for PokeGambler bot.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, **kwargs):
        intents = discord.Intents.all()
        # pylint: disable=assigning-non-slot
        intents.presences = False
        super().__init__(intents=intents)
        self.version = "v1.1.0"
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
        self.logger = CustomLogger(
            self.error_log_path
        )
        self.dealer = CardGambler(self.assets_path)
        self.topgg = topgg.DBLClient(
            self, os.getenv('TOPGG_TOKEN')
        )
        # Commands
        for module in os.listdir("scripts/commands"):
            if module.endswith("commands.py"):
                module_type = module.split("commands.py")[0]
                self.load_commands(module_type)

# Bot Base

    # pylint: disable=too-many-locals
    async def on_message(self, message: Message):
        """
        On_message event from Discord API.
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
            try:
                if "no_log" not in dir(method) or not os.getenv('IS_LOCAL'):
                    cmd_data = CommandData(
                        message.author, message,
                        cmd.replace("cmd_", ""),
                        hasattr(method, "admin_only"),
                        args, option_dict
                    )
                    cmd_data.save()
                task = method(**kwargs)
                # Decorators can return None
                if task:
                    cmd_name = method.__name__.replace("cmd_", "")
                    await task
            except Exception:  # pylint: disable=broad-except
                await self.__handle_error()

# Connectors

    def run(self, *args, **kwargs):
        super().run(os.getenv('TOKEN'), *args, **kwargs)

    async def on_guild_join(self, guild: discord.Guild):
        """
        On_guild_join event from Discord API.
        """
        if not self.is_prod:
            return
        await self.topgg.post_guild_count()
        image = None
        if guild.banner:
            image = guild.banner.url
        elif guild.splash:
            image = guild.splash.url
        elif guild.icon:
            image = guild.icon.url
        emb = get_embed(
            embed_type="info",
            title=f"Added to {guild}.",
            image=image
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

    async def on_guild_remove(self, guild: discord.Guild):
        """
        On_guild_remove event from Discord API.
        """
        if not self.is_prod:
            return
        await self.topgg.post_guild_count()
        emb = get_embed(
            embed_type="info",
            title=f"Left {guild}.",
            image=None,
            color=discord.Colour.dark_red()
        )
        jq_log_channel = discord.utils.get(
            self.get_guild(
                self.official_server
            ).text_channels,
            name="joined_guilds_log"
        )
        await jq_log_channel.send(embed=emb)

    async def on_ready(self):
        """
        On_ready event from Discord API.
        """
        if not getattr(self, "owner", False):
            self.owner = self.get_user(self.owner_id)
        headers = get_rand_headers()
        self.sess = aiohttp.ClientSession(loop=self.loop, headers=headers)
        self.__pprinter()
        self.ready = True
        game = discord.Game(
            f"with the strings of fate. | Check: {self.prefix}info"
        )
        await online_now(self)
        Shop.refresh_tradables()
        PremiumShop.refresh_tradables()
        await self.topgg.post_guild_count()
        await self.change_presence(activity=game)
        self.__reward_nitro_boosters.start()

    def load_commands(
        self, module_type: str,
        reload_module: bool = False
    ):
        """
        Hot Module Import for Commands.
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
                rewarded.append(booster.id)
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
