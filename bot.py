"""
The Main Module which serves as the brain of the code.
"""

import importlib
import json
import os
import re
import sys
import traceback
from datetime import datetime

import aiohttp
import discord

from scripts.base.cardgen import CardGambler
from scripts.base.dbconn import DBConnector
from scripts.helpers.logger import CustomLogger
from scripts.helpers.utils import (
    get_ascii, prettify_discord, get_embed,
    parse_command, get_rand_headers,
    is_owner, is_admin
)


class PokeGambler(discord.Client):
    """PokeGambler: A Discord Bot using pokemon themed cards for gambling.
    Subclass of discord.Client which serves as the base for PokeGambler bot.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, **kwargs):
        intents = discord.Intents.all()
        intents.presences = False
        super().__init__(intents=intents)
        self.version = "v0.8.0"
        self.db_path = kwargs["db_path"]
        self.error_log_path = kwargs["error_log_path"]
        self.assets_path = kwargs["assets_path"]
        self.config_path = kwargs["config_path"]
        self.update_configs()
        # Defaults
        self.active_channels = []
        self.ready = False
        self.start_time = datetime.now()
        self.owner = None
        self.sess = None
        # Classes
        self.database = DBConnector(self.db_path)
        self.logger = CustomLogger(
            self.error_log_path
        )
        self.dealer = CardGambler(self.assets_path)
        self.database.create_tables()
        # Commands
        self.cooldown_users = {}
        for module in os.listdir("scripts/commands"):
            if module.endswith("commands.py"):
                module_type = module.split("commands.py")[0]
                self.load_commands(module_type)

    def __bl_wl_check(self, message):
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

    def __get_method(self, message):
        cleaned_content = message.clean_content
        for user in message.mentions:
            cleaned_content = re.sub(
                fr"\s?@{user.name}", "", cleaned_content
            )
        parsed = parse_command(
            self.prefix.lower(),
            cleaned_content.lower()
        )
        cmd = f'cmd_{parsed["Command"]}'
        args = parsed["Args"]
        option_dict = parsed["Kwargs"]
        method = None
        for com in [
            getattr(self, comtype)
            for comtype in sorted(
                dir(self),
                key=lambda x:x.startswith("custom"),
                reverse=True
            )
            if all([
                comtype.endswith('commands'),
                comtype != "load_commands"
            ])
        ]:
            if com.enabled:
                method = getattr(com, cmd, None)
                if method:
                    return method, cmd, args, option_dict
        return method, cmd, args, option_dict

    async def __no_dm_cmds(self, message):
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

    async def __handle_cd(self, message):
        if is_owner(self, message.author):
            return False
        on_cooldown = self.cooldown_users.get(message.author, None)
        if on_cooldown and (
            datetime.now() - self.cooldown_users[message.author]
        ).total_seconds() < self.configs["cooldown_time"]:
            await message.add_reaction("⌛")
            return True
        self.cooldown_users[message.author] = datetime.now()

    def load_commands(self, module_type, reload_module=False):
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
        cmd_obj = cmd_class(ctx=self, database=self.database, logger=self.logger)
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

    async def on_message(self, message):
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
            res = self.__get_method(message)
            method, cmd, args, option_dict = res
            if not method:
                cmd_name = cmd.replace('cmd_', self.prefix)
                await message.channel.send(
                    embed=get_embed(
                        f"Command `{cmd_name}` does not exist!",
                        embed_type="error",
                        title="Invalid Command"
                    )
                )
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
                    self.database.log_command(**{
                        "user_id": str(message.author.id),
                        "user_is_admin": is_admin(message.author),
                        "used_at": datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        "channel": str(message.channel.id),
                        "guild": str(message.guild.id),
                        "command": cmd.replace("cmd_", ""),
                        "args": args,
                        "kwargs": option_dict
                    })
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
        super().run(self.configs['token'], *args, **kwargs)

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
