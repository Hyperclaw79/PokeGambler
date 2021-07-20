"""
This module contains the Abstract Base Class for Commands.
It also has some useful decorators for the commands.
"""

# pylint: disable=unused-argument

from __future__ import annotations
from abc import ABC
from datetime import datetime
from functools import wraps
import json
from typing import Callable, List, Optional, TYPE_CHECKING, Union

import discord

from ..base.items import Item
from ..base.models import Inventory, Model, Profiles
from ..helpers.paginator import Paginator
from ..helpers.utils import (
    get_embed, is_admin,
    is_dealer, is_owner
)

if TYPE_CHECKING:
    from discord import Embed, Message, Member, File
    from bot import PokeGambler

__all__ = [
    'owner_only', 'admin_only', 'dealer_only',
    'get_chan', 'maintenance', 'no_log', 'alias',
    'model', 'Commands'
]


def owner_only(func: Callable):
    '''
    Only the owners can access these commands.
    '''
    func.__dict__["owner_only"] = True

    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if is_owner(self.ctx, message.author):
            return func(self, *args, message=message, **kwargs)
        func_name = func.__name__.replace("cmd_", self.ctx.prefix)
        self.logger.pprint(
            f'Command {func_name} can only be used by owners.',
            color="red",
            wrapped_func=func.__name__
        )
        return message.channel.send(
            embed=get_embed(
                f'Command `{func_name}` can only be used by '
                'the owners of PokeGambler.',
                embed_type="error"
            )
        )
    return wrapped


def admin_only(func: Callable):
    '''
    Only the admins can access these commands.
    '''
    func.__dict__["admin_only"] = True

    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if any([
            all([
                is_admin(message.author),
                message.guild.id == self.ctx.official_server
            ]),
            is_owner(self.ctx, message.author)
        ]):
            async def func_with_callback(
                self, *args, message=message, **kwargs
            ):
                await func(self, *args, message=message, **kwargs)
                cmd_dump = json.dumps(
                    {
                        "Used By": message.author,
                        "Used At": datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        "Guild": message.guild,
                        "Channel": message.channel,
                        "Kwargs": kwargs
                    },
                    indent=3,
                    default=str
                )
                await message.guild.get_channel(
                    self.ctx.admin_cmd_log_channel
                ).send(
                    embed=get_embed(
                        f"```json\n{cmd_dump}\n```",
                        title=func.__name__.replace("cmd_", self.ctx.prefix)
                    )
                )
            return func_with_callback(self, *args, message=message, **kwargs)
        func_name = func.__name__.replace("cmd_", self.ctx.prefix)
        return message.channel.send(
            embed=get_embed(
                f'Command `{func_name}` can only be used by '
                'Pokegambler Admins.',
                embed_type="error"
            )
        )
    return wrapped


def dealer_only(func: Callable):
    '''
    Only the dealers can access these commands.
    '''
    func.__dict__["dealer_only"] = True

    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if all([
            is_dealer(message.author),
            message.guild.id == self.ctx.official_server
        ]):
            return func(self, *args, message=message, **kwargs)
        func_name = func.__name__.replace("cmd_", self.ctx.prefix)
        return message.channel.send(
            embed=get_embed(
                f'Command `{func_name}` can only be used by '
                'Pokegambler Dealers.',
                embed_type="error"
            )
        )
    return wrapped


def get_chan(func: Callable):
    '''
    Gets the active channel if there's one present.
    Else returns the message channel.
    '''
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if kwargs.get("channel"):
            chan = kwargs["channel"]
        elif kwargs.get("chan"):
            chan = kwargs["chan"]
        elif self.ctx.active_channels:
            chan = self.ctx.active_channels[-1]
        else:
            chan = message.channel
        kwargs.update({'chan': chan})
        return func(self, *args, message=message, **kwargs)
    return wrapped


def maintenance(func: Callable):
    '''
    Disable a broken/wip function to prevent it from affecting rest of the bot.
    '''
    func.__dict__["disabled"] = True

    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        func_name = func.__name__.replace('cmd_', '')
        self.logger.pprint(
            f"The command {func_name} is under maintenance.\n"
            "Wait for a future update to see changes.",
            timestamp=True,
            color="red"
        )
        return message.channel.send(
            embed=get_embed(
                f"The command {func_name} is under maintenance.\n"
                "Wait for a future update to see changes.",
                embed_type="error"
            )
        )
    return wrapped


def no_log(func: Callable):
    '''
    Pevents a command from being logged in the DB.
    Useful for debug related commands.
    '''
    func.__dict__["no_log"] = True

    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        return func(self, *args, message=message, **kwargs)
    return wrapped


def alias(alt_names: Union[List[str], str]):
    '''
    Add an alias to a function.
    '''
    if isinstance(alt_names, str):
        alt_names = [alt_names]

    def decorator(func: Callable):
        func.__dict__["alias"] = alt_names

        @wraps(func)
        def wrapped(self, message, *args, **kwargs):
            for name in alt_names:
                setattr(
                    self,
                    f"cmd_{name}",
                    getattr(self, func.__name__)
                )
            return func(self, *args, message=message, **kwargs)
        return wrapped
    return decorator


def model(models: Union[List[Model], Model]):
    '''
    Marks a command with list of Models it is accessing.
    '''
    if isinstance(models, Model):
        models = [models]

    def decorator(func: Callable):
        func.__dict__["models"] = models

        @wraps(func)
        def wrapped(self, message, *args, **kwargs):
            return func(self, *args, message=message, **kwargs)
        return wrapped
    return decorator


def ensure_user(func: Callable):
    '''
    Make sure user ID is given in the command.
    '''
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if not kwargs.get("args"):
            return message.channel.send(
                embed=get_embed(
                    "You need to provide a user ID.",
                    embed_type="error",
                    title="No User ID"
                )
            )
        if not message.guild.get_member(int(kwargs["args"][0])):
            return message.channel.send(
                embed=get_embed(
                    "Unable to fetch this user.\n"
                    "Make sure they're still in the server.",
                    embed_type="error",
                    title="Invalid User"
                )
            )
        return func(self, *args, message=message, **kwargs)
    return wrapped


def ensure_item(func: Callable):
    '''
    Make sure that the Item with the given ID exists already.
    '''
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        args = kwargs.pop("args", None)
        if not args:
            return message.channel.send(
                embed=get_embed(
                    "You need to provide am Item ID.",
                    embed_type="error",
                    title="No Item ID"
                )
            )
        item = Item.from_id(args[0])
        if not item:
            return message.channel.send(
                embed=get_embed(
                    "Could not find any item with the given ID.",
                    embed_type="error",
                    title="Item Does Not Exist"
                )
            )
        kwargs["item"] = item
        kwargs["args"] = args
        args = []
        return func(self, *args, message=message, **kwargs)
    return wrapped


def no_thumb(func: Callable):
    '''
    Mark a command to prevent thumbnail in it's help.
    Useful for commands with Ascii tables in their docs.
    '''
    func.__dict__["no_thumb"] = True

    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        return func(self, *args, message=message, **kwargs)
    return wrapped


def cooldown(secs: int):
    '''
    Add a custom cooldown for a command.
    '''
    def decorator(func: Callable):
        func.__dict__["cooldown"] = secs

        @wraps(func)
        def wrapped(self, message, *args, **kwargs):
            # if func not in self.ctx.cooldown_cmds:
            #     self.ctx.cooldown_cmds[func] = {}
            return func(self, *args, message=message, **kwargs)
        return wrapped
    return decorator


def check_completion(func: Callable):
    '''
    Checks if a command is already in progress for a user.
    '''
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        async def with_calback(self, message, *args, **kwargs):
            await func(self, *args, message=message, **kwargs)
            self.ctx.pending_cmds[
                func.__name__
            ].remove(message.author.id)
        if self.ctx.pending_cmds.get(func.__name__, None):
            if message.author.id in self.ctx.pending_cmds[func.__name__]:
                return message.channel.send(
                    embed=get_embed(
                        "You already triggered this command once.\n"
                        "Please complete it before using it again.",
                        embed_type="error",
                        title="Command Pending"
                    )
                )
            self.ctx.pending_cmds[func.__name__].append(message.author.id)
            return with_calback(self, *args, message=message, **kwargs)
        self.ctx.pending_cmds[func.__name__] = [message.author.id]
        return with_calback(self, *args, message=message, **kwargs)
    return wrapped


def needs_ticket(name: str):
    '''
    Checks if user has the tickets in inventory.
    '''
    def decorator(func: Callable):
        @wraps(func)
        def wrapped(self, message, *args, **kwargs):
            inv = Inventory(message.author)
            tickets = inv.from_name(name)
            if not tickets:
                return message.channel.send(
                    embed=get_embed(
                        "You do not have any renaming tickets.\n"
                        "You can buy one from the Consumables Shop.",
                        embed_type="error",
                        title="Insufficient Tickets"
                    )
                )
            kwargs["tickets"] = tickets
            return func(self, *args, message=message, **kwargs)
        return wrapped
    return decorator


class Commands(ABC):
    '''
    The Base command class which serves as the starting point for all commands.
    Can also be used to enable or disable entire categories.
    '''
    def __init__(
        self, ctx: PokeGambler,
        *args, **kwargs
    ):
        self.ctx = ctx
        self.logger = ctx.logger
        self.enabled = kwargs.get('enabled', True)
        self.alias = []
        self.chip_emoji = "<:pokechip:840469159242760203>"
        self.bond_emoji = "<:pokebond:853991200628932608>"
        cmds = [
            getattr(self, attr)
            for attr in dir(self)
            if all([
                attr.startswith("cmd_"),
                "alias" in dir(getattr(self, attr))
            ])
        ]
        for cmd in cmds:
            for name in cmd.alias:
                self.alias.append(f"cmd_{name}")
                setattr(self, f"cmd_{name}", cmd)

    @property
    def enable(self):
        '''
        Quickly Enable a Commands Category module.
        '''
        self.enabled = True
        return self.enabled

    @property
    def disable(self):
        '''
        Quickly Disable a Commands Category module.
        '''
        self.enabled = False
        return self.enabled

    async def paginate(
        self, message: Message,
        embeds: List[Embed],
        files: Optional[List[File]] = None
    ):
        """
        Convenience method for conditional pagination.
        """
        if files:
            asset_chan = message.guild.get_channel(
                self.ctx.img_upload_channel
            ) or self.ctx.get_channel(
                self.ctx.img_upload_channel
            )
            msg = await asset_chan.send(file=files[0])
            embeds[0].set_image(
                url=msg.attachments[0].proxy_url
            )
        base = await message.channel.send(embed=embeds[0])
        if len(embeds) > 1:
            if not embeds[0].footer:
                for idx, emb in enumerate(embeds):
                    emb.set_footer(
                        text=f"{idx + 1} / {len(embeds)}"
                    )
            pager = Paginator(
                self.ctx, message, base,
                embeds, files
            )
            await pager.run()


async def get_profile(message: Message, user: Member):
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
        if user.bot:
            await message.channel.send(
                embed=get_embed(
                    "Bot accounts cannot have profiles.",
                    embed_type="error",
                    title="Bot Account found"
                )
            )
            return None
        return Profiles(user)
    except discord.HTTPException:
        await message.channel.send(
            embed=get_embed(
                "Could not retrieve the user.",
                embed_type="error",
                title="User not found"
            )
        )
        return None
