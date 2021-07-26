"""
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
    Callable, Dict, Iterable, List,
    Optional, TYPE_CHECKING, Union
)

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
    """
    A Context Manager to profile a set of lines of code.
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


def get_formatted_time(
    tot_secs: int,
    show_hours: bool = True,
    show_mins: bool = True
) -> str:
    """ Converts total seconds into a human readable format."""
    hours = divmod(tot_secs, 3600)
    minutes = divmod(hours[1], 60)
    seconds = divmod(minutes[1], 1)
    disp_tm = f"**{int(seconds[0]):02d} seconds**"
    if show_mins:
        disp_tm = f"**{int(minutes[0]):02d} minutes** and " + disp_tm
    if show_hours:
        disp_tm = f"**{int(hours[0]):02d} hours**, " + disp_tm
    return disp_tm


def get_ascii(msg: str) -> str:
    """ Returns the ascii art for a text. """
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


def prettify_discord(
    ctx: PokeGambler,
    iterable: List,
    mode: str = "guild"
) -> str:
    """ Prettification for iterables like guilds and channels. """
    func = getattr(ctx, f"get_{mode}")
    return '\n\t'.join(
        ', '.join(
            f"{func(id=elem)} ({str(elem)})"
            for elem in iterable[i: i + 2]
        )
        for i in range(0, len(iterable), 2)
    )


# pylint: disable=too-many-arguments
def get_embed(
    content: str, embed_type: str = "info",
    title: Optional[str] = None,
    footer: Optional[str] = None,
    image: Optional[str] = None,
    thumbnail: Optional[str] = None,
    color: Optional[int] = None,
    no_icon: bool = False
) -> Embed:
    """
    Creates a Discord Embed with appropriate color, title and description.
    """
    embed_params = {
        "info": {
            "name": "INFORMATION",
            "icon": ":information_source:",
            "color": 11068923
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
    custom_ext: bool = False
) -> Embed:
    """ Creates a Discord Embed with prettified iterable as description. """
    enum_str = '\n'.join(
        f"{i + 1}. {name}"
        for i, name in enumerate(iterable)
    )
    if not custom_ext:
        enum_str = f"```md\n{enum_str}\n```"
    return get_embed(
        enum_str,
        embed_type=embed_type,
        title=title
    )


def parse_command(prefix: str, msg: str) -> dict:
    """ Parses a message to obtain the command, args and kwargs. """
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


# pylint: disable=too-many-arguments
async def wait_for(
    chan: TextChannel, ctx: PokeGambler,
    event: str = "message",
    init_msg: Optional[Message] = None,
    check: Optional[Callable] = None,
    timeout: Optional[Union[float, str]] = None
) -> Message:
    """
    Modified version of discord.Client.wait_for.
    Checks the history once upon timeout.
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


def get_rand_headers() -> Dict:
    """
    Generates a random header for the aiohttp session.
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


def img2file(
    img: Image, fname: str,
    ext: str = "JPEG"
) -> File:
    """
    Convert a PIL Image into a discord File.
    """
    byio = BytesIO()
    img.save(byio, ext)
    byio.seek(0)
    return discord.File(byio, fname)


def is_owner(ctx: PokeGambler, user: Member) -> bool:
    """
    Checks if user is bot owner.
    """
    return user.id in (
        ctx.allowed_users,
        ctx.owner_id
    )


def is_admin(user: Member) -> bool:
    """
    Checks if user is a server admin.
    """
    roles = [
        role.name.lower()
        for role in user.roles
    ]
    return all([
        "admins" in roles,
        user.guild.id == os.getenv('OFFICIAL_SERVER')
    ])


def is_dealer(user: Member) -> bool:
    """
    Checks if user is a PokeGambler Dealer.
    """
    roles = [
        role.name.lower()
        for role in user.roles
    ]
    return all([
        "dealer" in roles,
        user.guild.id == os.getenv('OFFICIAL_SERVER')
    ])


def get_modules(ctx: PokeGambler) -> List[Commands]:
    """
    Returns a list of all the commands.
    """
    return [
        getattr(ctx, comtype)
        for comtype in dir(ctx)
        if all([
            comtype.endswith('commands'),
            comtype != "load_commands"
        ])
    ]


def dedent(message: str) -> str:
    """
    Strips whitespaces from the left of every line.
    """
    return '\n'.join(
        line.lstrip()
        for line in message.splitlines()
    )


async def online_now(ctx: PokeGambler):
    """
    Notifies on Discord, that PokeGambler is ready.
    """
    secret = ctx.discord_webhook_token
    channel = ctx.discord_webhook_channel
    url = f"https://discord.com/api/webhooks/{channel}/{secret}"
    body = {
        "username": "PokeGambler Status Monitor",
        "content": "\n".join([
            "<:online:841643544581111808>\t**Online**",
            "PokeGambler is back online, you can use commands again.",
            "\u200B\n\u200B\n"
        ])
    }
    await ctx.sess.post(url=url, data=body)


async def dm_send(
    message: Message, user: Member,
    content: Optional[str] = None,
    embed: Optional[Embed] = None
) -> Message:
    """
    Attempts to send message to the User's DM.
    In case of fallback, sends in the original channel.
    """
    try:
        msg = await user.send(content=content, embed=embed)
    except discord.Forbidden:
        msg = await message.channel.send(
            content=f"Hey {user.mention},\n{content if content else ''}",
            embed=embed
        )
    return msg


def showable_command(
    ctx: PokeGambler,
    cmd: Callable, user: Member
):
    """
    Checks if a command is accessible to a user based on roles.
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
    args: Optional[List[str]] = None,
):
    """
    Get a list of all showable commands for a given Module.
    """
    role = args[0] if args else None
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
