"""
The Main Module which serves as the brain of the code.
"""

import difflib
import importlib
import json
import os
import sys
import traceback
from datetime import datetime
from typing import Callable

import aiohttp
import discord
from discord import Message
from dotenv import load_dotenv

from scripts.base.models import CommandData

from scripts.base.cardgen import CardGambler
from scripts.base.dbconn import DBConnector
from scripts.helpers.logger import CustomLogger
# pylint: disable=cyclic-import
from scripts.helpers.utils import (
    dm_send, get_ascii, get_commands, get_formatted_time, get_modules,
    prettify_discord, get_embed, parse_command,
    get_rand_headers, is_owner, online_now
)


load_dotenv()


class PokeGambler(discord.Client):
    """PokeGambler: A Discord Bot using pokemon themed cards for gambling.
    Subclass of discord.Client which serves as the base for PokeGambler bot.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, **kwargs):
        intents = discord.Intents.all()
        intents.presences = False
        super().__init__(intents=intents)
        self.version = "v0.9.0"
        self.db_path = kwargs["db_path"]
        self.error_log_path = kwargs["error_log_path"]
        self.assets_path = kwargs["assets_path"]
        self.config_path = kwargs["config_path"]
        for var in ["DISCORD_WEBHOOK_TOKEN", "DISCORD_WEBHOOK_CHANNEL"]:
            setattr(self, var, os.getenv(var))
        self.update_configs()
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
        self.boost_dict = {}
        self.pending_cmds = {}
        # Classes
        self.database = DBConnector(self.db_path)
        self.logger = CustomLogger(
            self.error_log_path
        )
        self.dealer = CardGambler(self.assets_path)
        self.database.create_tables()
        # Commands
        for module in os.listdir("scripts/commands"):
            if module.endswith("commands.py"):
                module_type = module.split("commands.py")[0]
                self.load_commands(module_type)

    def __bl_wl_check(self, message: Message):
        blacklist_checks = [
            self.channel_mode == "blacklist",
            message.channel.id in self.configs["blacklist_channels"]
        ]
        whitelist_checks = [
            self.channel_mode == "whitelist",
            message.channel.id not in self.configs["whitelist_channels"]
        ]
        blackguild_checks = [
            self.guild_mode == "blacklist",
            message.guild.id in self.configs["blacklist_guilds"]
        ]
        whiteguild_checks = [
            self.guild_mode == "whitelist",
            message.guild.id not in self.configs["whitelist_guilds"]
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
        ).total_seconds() < self.configs["cooldown_time"]:
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
        cmd_obj = cmd_class(ctx=self)
        setattr(self, f"{module_type}commands", cmd_obj)
        return cmd_obj

    def update_configs(self):
        """
        For dynamic config updates.
        """
        # pylint: disable=invalid-name
        with open(self.config_path, encoding='utf-8') as f:
            self.configs = json.load(f)
        self.guild_mode = self.configs["default_guildmode"]
        self.channel_mode = self.configs["default_channelmode"]
        self.owner_id = int(self.configs['owner_id'])
        self.prefix = self.configs['command_prefix']

# Bot Base

    # pylint: disable=too-many-return-statements, too-many-branches
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
            on_cooldown = await self.__handle_cd(message)
            if on_cooldown:
                return
            if self.database.is_blacklisted(
                str(message.author.id)
            ) or message.author.bot:
                await message.add_reaction("🚫")
                return
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
                if "no_log" not in dir(method):
                    cmd_data = CommandData(
                        self.database, message.author, message,
                        cmd.replace("cmd_", ""), args, option_dict
                    )
                    cmd_data.save()
                task = method(**kwargs)
                # Decorators can return None
                if task:
                    await task
            except Exception:  # pylint: disable=broad-except
                tb_obj = sys.exc_info()[2]
                tb_obj = traceback.format_exc()
                self.logger.pprint(
                    tb_obj,
                    timestamp=True,
                    color="red"
                )

# Connectors

    def run(self, *args, **kwargs):
        super().run(os.getenv('token'), *args, **kwargs)

    async def on_ready(self):
        """
        On_ready event from Discord API.
        """
        if not getattr(self, "owner", False):
            self.owner = self.get_user(self.owner_id)
        headers = get_rand_headers()
        self.sess = aiohttp.ClientSession(loop=self.loop, headers=headers)
        pretty = {
            itbl: prettify_discord(
                self,
                **{
                    "iterable": self.configs[itbl],
                    "mode": itbl.split("_")[1].rstrip("s")
                }
            )
            for itbl in [
                "blacklist_channels", "whitelist_channels",
                "blacklist_guilds", "whitelist_guilds"
            ]
        }
        self.ready = True
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
            f"{self.configs['command_prefix']}\n\n"
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
            f"{self.configs['default_channelmode']}\n\n"
            f"\t{self.logger.wrap('Default Guild Mode:', color='blue')} "
            f"{self.configs['default_guildmode']}\n\n"
        )
        game = discord.Game(
            f"with the strings of fate. | Check: {self.prefix}info"
        )
        await self.change_presence(activity=game)
        await online_now(self)
