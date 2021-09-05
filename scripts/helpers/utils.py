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

Compilation of Utility Functions
"""

from __future__ import annotations
import asyncio
import cProfile
from io import BytesIO
import os
import random
import re
import time
from typing import (
    Any, Callable, Dict, Iterable, List,
    Optional, TYPE_CHECKING, Tuple, Union
)
from cachetools import Cache, TTLCache

import discord

if TYPE_CHECKING:
    from discord import (
        Embed, File, Message,
        TextChannel, Member
    )
    from PIL.Image import Image
    from bot import PokeGambler
    # pylint: disable=cyclic-import
    from ..commands.basecommand import Commands
    from .logger import CustomLogger


class LineTimer:
    """A Context Manager to profile a set of lines of code.

    :param logger: The logger to use.
    :type logger: CustomLogger
    :param message: Prefix to add to the profile output.
    :type message: Optional[str]
    :param profile_it: Verbose profiling?
    :type profile_it: Optional[bool]
    """
    def __init__(
        self, logger: CustomLogger,
        message: Optional[str] = None,
        profile_it: Optional[bool] = False
    ):
        self.profile_it = profile_it
        self.logger = logger
        if profile_it:
            self.profiler = cProfile.Profile(
                subcalls=False,
                builtins=False
            )
        else:
            self.start_time = None
        self.message = message or ''
        if self.message:
            self.message = f"{self.message}: "

    def __enter__(self):
        if self.profile_it:
            self.profiler.enable()
        else:
            self.start_time = time.time()

    # pylint: disable=unused-argument
    def __exit__(self, exc_type, exc_value, traceback):
        if self.profile_it:
            self.profiler.disable()
            self.profiler.print_stats(sort='cumtime')
        else:
            elapsed = time.time() - self.start_time
            self.logger.pprint(
                f"{self.message}{elapsed: 2.2f} secs\n",
                color="yellow"
            )


class ImageCacher:
    """
    A TTL Cache for images created in a command for a user.

    :param user: The user to cache images for.
    :type user: :class:`discord.Member`
    :param kwargs: Additional Keyword Arguments.
    :type kwargs: Dict[str, Any]
    """
    def __init__(self, user: discord.Member, **kwargs):
        self.cache = TTLCache(maxsize=1, ttl=60)
        self.user = user
        self.kwargs = kwargs

    @property
    def keys(self) -> Tuple[str, Tuple[str, Any]]:
        """Returns a hashable key for the cache.

        :return: Hashable Key
        :rtype: Tuple[str, Tuple[str, Any]]
        """
        kwgs = tuple({
            key: val
            for key, val in self.kwargs.items()
            if key not in ["args", "mentions", "selected_user"]
        })
        return (self.user.id, kwgs)

    def expire(self):
        """
        Expire the cache.
        """
        Cache.clear(self.cache)

    def register(self, img_url: str):
        """Registers the image url to the cache.

        :param img_url: The image url to register.
        :type img_url: str
        """
        self.cache[self.keys] = img_url

    @property
    def cached(self) -> Optional[str]:
        """Returns the cached image URL if it exists.

        :return: The cached image URL.
        :rtype: Optional[str]
        """
        return self.cache.get(self.keys)


def dedent(message: str) -> str:
    """Strips whitespaces from the left of every line.

    :param message: The message to dedent.
    :type message: str
    :return: The dedented message.
    :rtype: str
    """
    return '\n'.join(
        line.lstrip()
        for line in message.splitlines()
    )


async def dm_send(
    message: Message, user: Member,
    content: Optional[str] = None,
    embed: Optional[Embed] = None,
    **kwargs
) -> Message:
    """Attempts to send message to the User's DM.
    In case of fallback, sends in the original channel.

    :param message: The message to send.
    :type message: :class:`discord.Message`
    :param user: The user to send the message to.
    :type user: :class:`discord.Member`
    :param content: The content of the message.
    :type content: Optional[str]
    :param embed: The embed to send.
    :type embed: Optional[:class:`discord.Embed`]
    :param kwargs: Additional Keyword Arguments.
    :type kwargs: Dict[str, Any]
    :return: The message sent.
    :rtype: :class:`discord.Message`
    """
    # pylint: disable=import-outside-toplevel, cyclic-import
    from ..helpers.slash import CustomInteraction

    try:
        if isinstance(message, CustomInteraction):
            msg = await message.reply(
                content=content,
                embed=embed,
                **kwargs
            )
        else:
            msg = await user.send(
                content=content,
                embed=embed,
                **kwargs
            )
    except discord.Forbidden:
        msg = await message.reply(
            content=f"{content if content else ''}",
            embed=embed,
            **kwargs
        )
    return msg


def get_ascii(msg: str) -> str:
    """Returns the ascii art for a text.

    :param msg: The message to convert to ascii art.
    :type msg: str
    :return: The ascii art.
    :rtype: str
    """
    artmap = {
        "0": ".█████╗.\n██╔══██╗\n██║..██║\n██║..██║\n╚█████╔╝\n.╚════╝.",
        "1": "..███╗..\n.████║..\n██╔██║..\n╚═╝██║..\n███████╗\n╚══════╝",
        "2": "██████╗.\n╚════██╗\n..███╔═╝\n██╔══╝..\n███████╗\n╚══════╝",
        "3": "██████╗.\n╚════██╗\n.█████╔╝\n.╚═══██╗\n██████╔╝\n╚═════╝.",
        "4": "..██╗██╗\n.██╔╝██║\n██╔╝.██║\n███████║\n╚════██║\n.....╚═╝",
        "5": "███████╗\n██╔════╝\n██████╗.\n╚════██╗\n██████╔╝\n╚═════╝.",
        "6": ".█████╗.\n██╔═══╝.\n██████╗.\n██╔══██╗\n╚█████╔╝\n.╚════╝.",
        "7": "███████╗\n╚════██║\n....██╔╝\n...██╔╝.\n..██╔╝..\n..╚═╝...",
        "8": ".█████╗.\n██╔══██╗\n╚█████╔╝\n██╔══██╗\n╚█████╔╝\n.╚════╝.",
        "9": ".█████╗.\n██╔══██╗\n╚██████║\n.╚═══██║\n.█████╔╝\n.╚════╝.",
        "v": "██╗...██╗\n██║...██║\n╚██╗.██╔╝\n.╚████╔╝.\n..╚██╔╝..\n...╚═╝...",  # noqa
        ".": "...\n...\n...\n...\n██╗\n╚═╝"
    }
    mapping = [artmap[ch] for ch in msg]
    art = '\n'.join(
        ''.join(var.split('\n')[i].replace(' ', '', 1) for var in mapping)
        for i in range(6)
    )

    art = '\t\t\t' + art.replace('\n', '\n\t\t\t')
    return art


# pylint: disable=too-many-arguments
def get_embed(
    content: Optional[str] = "",
    embed_type: Optional[str] = "info",
    title: Optional[str] = None,
    footer: Optional[str] = None,
    image: Optional[str] = None,
    thumbnail: Optional[str] = None,
    color: Optional[int] = None,
    no_icon: bool = False
) -> Embed:
    """Creates a Discord Embed with appropriate color, \
        title and description.

    :param content: The content of the embed.
    :type content: Optional[str]
    :param embed_type: The type of embed., default is info.
    :type embed_type: Optional[str]
    :param title: The title of the embed.
    :type title: Optional[str]
    :param footer: The footer of the embed.
    :type footer: Optional[str]
    :param image: The image url for the embed.
    :type image: Optional[str]
    :param thumbnail: The thumbnail url for the embed.
    :type thumbnail: Optional[str]
    :param color: The color of the embed.
    :type color: Optional[int]
    :param no_icon: If True, no icon will be shown.
    :type no_icon: bool
    :return: The embed
    :rtype: :class:`discord.Embed`
    """
    embed_params = {
        "info": {
            "name": "INFORMATION",
            "icon": ":information_source:",
            "color": (
                color if color is not None
                else 11068923
            )
        },
        "warning": {
            "name": "WARNING",
            "icon": ":warning:",
            "color": 16763904
        },
        "error": {
            "name": "ERROR",
            "icon": "❌",
            "color": 11272192
        }
    }
    params = embed_params[embed_type]
    if no_icon:
        title = f"{title or params['name']}"
    else:
        title = f"{params['icon']} {title or params['name']}"
    emb = discord.Embed(
        title=title,
        description=content,
        color=params['color']
    )
    if footer:
        emb.set_footer(text=footer)
    if image:
        emb.set_image(url=image)
    if thumbnail:
        emb.set_thumbnail(url=thumbnail)
    if color:
        emb.color = color
    return emb


def get_enum_embed(
    iterable: Iterable,
    embed_type: str = "info",
    title: Optional[str] = None,
    custom_ext: bool = False,
    color: Optional[int] = None
) -> Embed:
    """Creates a Discord Embed with prettified iterable as description.

    :param iterable: The iterable to be used as description.
    :type iterable: Iterable
    :param embed_type: The type of embed., default is info.
    :type embed_type: str
    :param title: The title of the embed.
    :type title: Optional[str]
    :param custom_ext: If True, won\'t be wrapped in Markdown codeblock.
    :type custom_ext: bool
    :param color: The color of the embed.
    :type color: Optional[int]
    :return: The embed
    :rtype: :class:`discord.Embed`
    """
    enum_str = '\n'.join(
        f"{i + 1}. {name}"
        for i, name in enumerate(iterable)
    )
    if not custom_ext:
        enum_str = f"```md\n{enum_str}\n```"
    return get_embed(
        enum_str,
        embed_type=embed_type,
        title=title,
        color=color
    )


def get_formatted_time(
    tot_secs: int,
    show_hours: bool = True,
    show_mins: bool = True
) -> str:
    """Converts total seconds into a human readable format.

    :param tot_secs: The total seconds to be converted.
    :type tot_secs: int
    :param show_hours: If True, hours will be shown.
    :type show_hours: bool
    :param show_mins: If True, minutes will be shown.
    :type show_mins: bool
    :return: The formatted time.
    :rtype: str
    """
    hours = divmod(tot_secs, 3600)
    minutes = divmod(hours[1], 60)
    seconds = divmod(minutes[1], 1)
    disp_tm = f"**{int(seconds[0]):02d} seconds**"
    if show_mins:
        disp_tm = f"**{int(minutes[0]):02d} minutes** and " + disp_tm
    if show_hours:
        disp_tm = f"**{int(hours[0]):02d} hours**, " + disp_tm
    return disp_tm


def get_modules(ctx: PokeGambler) -> List[Commands]:
    """Returns a list of all the
    :class:`~scripts.commands.basecommand.Commands` Modules.

    :param ctx: The PokeGambler client object.
    :type ctx: :class:`bot.PokeGambler`
    :return: A list of all the command modules.
    :rtype: List[:class:`~scripts.commands.basecommand.Commands`]
    """
    yield from (
        getattr(ctx, comtype)
        for comtype in dir(ctx)
        if all([
            not comtype.startswith("_"),
            comtype.endswith('commands'),
            comtype != "load_commands"
        ])
    )


def get_rand_headers() -> Dict:
    """Generates a random header for the aiohttp session.

    .. warning:: Will be deprecated in the future.

    :return: A header with a random User-Agent.
    :rtype: Dict
    """
    browsers = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "AppleWebKit/537.36 (KHTML, like Gecko)",
        "discord/0.0.306",
        "Chrome/80.0.3987.132",
        "Discord/1.6.15",
        "Safari/537.36",
        "Electron/7.1.11"
    ]
    return {
        "User-Agent": ' '.join(
            set(
                random.choices(
                    browsers,
                    k=random.randint(1, len(browsers))
                )
            )
        ),
        "Referer": "https://discordapp.com",
        "Origin": "https://discordapp.com"
    }


def is_admin(user: Member) -> bool:
    """Checks if user is an admin in the official server.

    :param user: The user to be checked.
    :type user: :class:`discord.Member`
    :return: True if the user is an admin.
    :rtype: bool
    """
    roles = [
        role.name.lower()
        for role in user.roles
    ]
    return all([
        "admins" in roles,
        user.guild.id == int(os.getenv('OFFICIAL_SERVER'))
    ])


def is_dealer(user: Member) -> bool:
    """Checks if user is a PokeGambler Dealer.

    :param user: The user to be checked.
    :type user: :class:`discord.Member`
    :return: True if the user is a PokeGambler Dealer.
    :rtype: bool
    """
    roles = [
        role.name.lower()
        for role in user.roles
    ]
    return all([
        "dealers" in roles,
        user.guild.id == int(os.getenv('OFFICIAL_SERVER'))
    ])


def is_owner(ctx: PokeGambler, user: Member) -> bool:
    """Checks if the user is an owner of PokeGambler.

    :param ctx: The PokeGambler client object.
    :type ctx: :class:`bot.PokeGambler`
    :param user: The user to be checked.
    :type user: :class:`discord.Member`
    :return: True if the user is an owner of PokeGambler.
    :rtype: bool
    """
    return user.id in (
        ctx.allowed_users,
        ctx.owner_id
    )


def img2file(
    img: Image, fname: str,
    ext: str = "JPEG"
) -> File:
    """Convert a PIL Image into a discord File.

    :param img: The PIL Image to be converted.
    :type img: :class:`PIL.Image.Image`
    :param fname: The filename of the file.
    :type fname: str
    :param ext: The extension of the file.
    :type ext: str
    :return: The discord File object.
    :rtype: :class:`discord.File`
    """
    byio = BytesIO()
    img.save(byio, ext)
    byio.seek(0)
    return discord.File(byio, fname)


async def online_now(ctx: PokeGambler):
    """Notifies on Discord, that PokeGambler is ready.

    :param ctx: The PokeGambler client object.
    :type ctx: :class:`bot.PokeGambler`
    """
    secret = ctx.discord_webhook_token
    channel = ctx.discord_webhook_channel
    url = f"https://discord.com/api/webhooks/{channel}/{secret}"
    body = {
        "username": "PokeGambler Status Monitor",
        "content": "\n".join([
            "<:online:874626019607334922>\t**Online**",
            "PokeGambler is back online, you can use commands again.",
            "\u200B\n\u200B\n"
        ])
    }
    await ctx.sess.post(url=url, data=body)


def parse_command(prefix: str, msg: str) -> Dict:
    """Parses a message to obtain the command, args and kwargs.

    :param prefix: The prefix of the command.
    :type prefix: str
    :param msg: The message to be parsed.
    :type msg: str
    :return: A dictionary with the command, args and kwargs.
    :rtype: Dict
    """
    def is_digit(word, check_float=False):
        symbols = ['+', '-']
        if check_float:
            if word.count('.') != 1:
                return False
            symbols.append('.')
        for sym in symbols:
            if sym in word:
                word = word.replace(sym, '')
        return word.isdigit()

    def purify_kwarg(kwarg):
        key = kwarg.split(' ')[0]
        val = ' '.join(kwarg.split(' ')[1:])
        if len(kwarg.split(' ')) == 1:
            val = True
        elif val in [
            "true", "True", "false", "False"
        ]:
            val = val in ["true", "True"]
        elif is_digit(val):
            val = int(val)
        elif is_digit(val, check_float=True):
            val = float(val)
        return key, val

    parsed = {
        "Command": "",
        "Args": [],
        "Kwargs": {}
    }
    non_kwarg_str, *kwarg_str = msg.partition('--')
    main_sep_patt = (
        re.escape(prefix) +
        r'(?:(?P<Command>\S+)\s?)' +
        r'(?:(?P<Args>.+)\s?)*'
    )
    main_parsed_dict = re.search(
        main_sep_patt,
        non_kwarg_str,
        re.IGNORECASE
    ).groupdict()
    if kwarg_str:
        main_parsed_dict["Kwargs"] = ''.join(kwarg_str)
    parsed["Command"] = main_parsed_dict["Command"].lower()
    if main_parsed_dict["Args"]:
        parsed["Args"] = [
            arg
            for arg in main_parsed_dict["Args"].rstrip(' ').split(' ')
            if arg
        ]
    if main_parsed_dict.get("Kwargs", None):
        kwargs = main_parsed_dict["Kwargs"].split(' --')
        kwargs[0] = kwargs[0].lstrip('-')
        kwarg_dict = {}
        for kwarg in kwargs:
            key, val = purify_kwarg(kwarg)
            kwarg_dict[key] = val
        parsed["Kwargs"] = kwarg_dict
    return parsed


def prettify_discord(
    ctx: PokeGambler,
    iterable: List[str],
    mode: str = "guild"
) -> str:
    """Prettification for iterables like guilds and channels.

    :param ctx: The PokeGambler client object.
    :type ctx: :class:`bot.PokeGambler`
    :param iterable: The iterable to be prettified.
    :type iterable: List[str]
    :param mode: Guild or Channel?
    :type mode: str
    :return: The prettified string.
    :rtype: str
    """
    func = getattr(ctx, f"get_{mode}")
    return '\n\t'.join(
        ', '.join(
            f"{func(id=elem)} ({str(elem)})"
            for elem in iterable[i: i + 2]
        )
        for i in range(0, len(iterable), 2)
    )


# pylint: disable=too-many-arguments
def showable_command(
    ctx: PokeGambler,
    cmd: Callable, user: Member
):
    """Checks if a command is accessible to a user based on roles.

    :param ctx: The PokeGambler client object.
    :type ctx: :class:`bot.PokeGambler`
    :param cmd: The command to be checked.
    :type cmd: Callable
    :param user: The user to check the command for.
    :type user: :class:`discord.Member`
    :return: True if the command is accessible, False otherwise.
    :rtype: bool
    """
    def has_access(cmd, user):
        if is_owner(ctx, user):
            return True
        if is_admin(user):
            return not getattr(cmd, "owner_only", False)
        if is_dealer(user):
            return not any([
                getattr(cmd, "owner_only", False),
                getattr(cmd, "admin_only", False)
            ])
        return not any([
            getattr(cmd, "owner_only", False),
            getattr(cmd, "admin_only", False),
            getattr(cmd, "dealer_only", False)
        ])
    return all([
        cmd.__doc__,
        not getattr(cmd, "disabled", False),
        has_access(cmd, user)
    ])


def get_commands(
    ctx: PokeGambler, user: Member, module: Commands,
    roles: Optional[List[str]] = None,
) -> str:
    """Get a list of all showable commands for a given Module.

    :param ctx: The PokeGambler client object.
    :type ctx: :class:`bot.PokeGambler`
    :param user: The user to check the commands for.
    :type user: :class:`discord.Member`
    :param module: The module to get the commands from.
    :type module: :class:`~scripts.commands.basecommand.Commands`
    :param roles: The roles to check the commands for.
    :type roles: Optional[List[str]]
    :return: A list of all showable commands.
    :rtype: str
    """
    role = roles[0] if roles else None
    return '\n'.join(
        sorted(
            [
                cmd.replace("cmd_", ctx.prefix)
                for cmd in dir(module)
                if all([
                    cmd.startswith("cmd_"),
                    showable_command(
                        ctx,
                        getattr(module, cmd),
                        user
                    ),
                    cmd not in getattr(module, "alias", []),
                    any([
                        role is None,
                        all([
                            role is not None,
                            getattr(
                                getattr(module, cmd),
                                f"{role}_only", False
                            )
                        ])
                    ])
                ])
            ],
            key=len
        )
    )


async def wait_for(
    chan: TextChannel, ctx: PokeGambler,
    event: str = "message",
    init_msg: Optional[Message] = None,
    check: Optional[Callable] = None,
    timeout: Optional[Union[float, str]] = None
) -> Message:
    """Modified version of :meth:`discord.Client.wait_for`.
    Checks the history once upon timeout.

    :param chan: The channel to wait for messages in.
    :type chan: :class:`discord.TextChannel`
    :param ctx: The PokeGambler client object.
    :type ctx: :class:`bot.PokeGambler`
    :param event: The event to wait for., defaults to message.
    :type event: str
    :param init_msg: Checks history after this message.
    :type init_msg: Optional[:class:`discord.Message`]
    :param check: Checks the message against this function.
    :type check: Optional[Callable]
    :param timeout: The timeout to wait for.
    :type timeout: Optional[Union[float, str]]
    :return: The message that was received.
    :rtype: :class:`discord.Message`
    """
    if not timeout:
        timeout = 5.0
    elif timeout == "inf":
        timeout = None
    try:
        reply = await ctx.wait_for(
            event,
            check=check,
            timeout=timeout
        )
        return reply
    except asyncio.TimeoutError:
        history = chan.history(limit=10, after=init_msg)
        reply = await history.find(predicate=check)
        return reply
