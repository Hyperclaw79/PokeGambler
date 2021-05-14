"""
Compilation of Utility Functions
"""

import asyncio
import random
import re
from io import BytesIO
from typing import Iterable

import discord
from ..base.models import Profile

__all__ = [
    'get_formatted_time', 'get_ascii',
    'prettify_discord', 'get_embed',
    'get_enum_embed', 'parse_command',
    'wait_for', 'get_rand_headers',
    'img2file', 'is_owner', 'is_admin', 'is_dealer'
]


def get_formatted_time(tot_secs: int) -> str:
    """ Converts total seconds into a human readable format."""
    hours = divmod(tot_secs, 3600)
    minutes = divmod(hours[1], 60)
    seconds = divmod(minutes[1], 1)
    return f"{int(hours[0]):02d} hours, {int(minutes[0]):02d} minutes" + \
        f" and {int(seconds[0]):02d} seconds"


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
        "v": "██╗...██╗\n██║...██║\n╚██╗.██╔╝\n.╚████╔╝.\n..╚██╔╝..\n...╚═╝...",
        ".": "...\n...\n...\n...\n██╗\n╚═╝"
    }
    mapping = [artmap[ch] for ch in msg]
    art = '\n'.join(
        ''.join(var.split('\n')[i].replace(' ', '', 1) for var in mapping)
        for i in range(6)
    )

    art = '\t\t\t' + art.replace('\n', '\n\t\t\t')
    return art


def prettify_discord(ctx, iterable: list, mode="guild") -> str:
    """ Prettification for iterables like guilds and channels. """
    func = getattr(ctx, f"get_{mode}")
    return '\n\t'.join(
        ', '.join(
            f"{func(id=elem)} ({str(elem)})"
            for elem in iterable[i : i + 2]
        )
        for i in range(0, len(iterable), 2)
    )


def get_embed(
    content: str, embed_type: str = "info",
    title: str = None, footer: str = None
) -> discord.Embed:
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
    emb = discord.Embed(
        title=f"{params['icon']} {title or params['name']}",
        description=content,
        color=params['color']
    )
    if footer:
        emb.set_footer(text=footer)
    return emb


def get_enum_embed(
    iterable: Iterable, embed_type: str = "info",
    title: str = None, custom_ext=False
) -> discord.Embed:
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
        non_kwarg_str
    ).groupdict()
    if kwarg_str:
        main_parsed_dict["Kwargs"] = ''.join(kwarg_str)
    parsed["Command"] = main_parsed_dict["Command"]
    if main_parsed_dict["Args"]:
        parsed["Args"] = main_parsed_dict["Args"].rstrip(' ').split(' ')
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
    chan, ctx, event="message",
    init_msg=None, check=None, timeout=None
):
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


def get_rand_headers():
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


def img2file(img, fname, ext="JPEG"):
    """
    Convert a PIL Image into a discord File.
    """
    byio = BytesIO()
    img.save(byio, ext)
    byio.seek(0)
    return discord.File(byio, fname)


def is_owner(ctx, user):
    """
    Checks if user is bot owner.
    """
    return user.id in [
        ctx.configs["allowed_users"],
        ctx.owner_id
    ]

def is_admin(user):
    """
    Checks if user is a server admin.
    """
    roles = [
        role.name.lower()
        for role in user.roles
    ]
    return "admins" in roles


def is_dealer(user):
    """
    Checks if user is a PokeGambler Dealer.
    """
    roles = [
        role.name.lower()
        for role in user.roles
    ]
    return "dealers" in roles

def get_modules(ctx):
    """
    Returns a list of all the commands.
    """
    return ([
        getattr(ctx, comtype)
        for comtype in dir(ctx)
        if all([
            comtype.endswith('commands'),
            comtype != "load_commands"
        ])
    ])

async def get_profile(database, message, user):
    """
    Retrieves the Profile for a user (creates for new users).
    If the user is not found in the guild, returns None.
    """
    try:
        if isinstance(user, (int, str)):
            user = message.guild.get_member(user)
            if not user:
                await message.channel.send(
                    embed=get_embed(
                        "Could not retrieve the user.",
                        embed_type="error",
                        title="User not found"
                    )
                )
                return None
        return Profile(database, user)
    except discord.HTTPException:
        await message.channel.send(
            embed=get_embed(
                "Could not retrieve the user.",
                embed_type="error",
                title="User not found"
            )
        )
        return None
