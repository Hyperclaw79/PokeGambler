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

This module contains the Abstract Base Class for Commands.
It also has some useful decorators for the commands.
"""

# pylint: disable=unused-argument

from __future__ import annotations
from abc import ABC
from datetime import datetime
from functools import wraps
import json
from typing import (
    Any, Callable, Coroutine, Dict, List, Optional,
    TYPE_CHECKING, Tuple, Union
)

import discord
from dotenv import load_dotenv

from ..base.handlers import CustomInteraction
from ..base.items import Item
from ..base.models import Inventory, Model, Profiles
from ..base.shop import PremiumShop, Shop
from ..base.views import CallbackButton, CallbackButtonView, LinkView

from ..helpers.paginator import Paginator
from ..helpers.utils import (
    ImageCacher, dedent, dm_send, get_embed, is_admin,
    is_dealer, is_owner
)
from ..helpers.validators import HexValidator, IntegerValidator

if TYPE_CHECKING:
    from discord import Embed, Message, Member, File, TextChannel
    from bot import PokeGambler

load_dotenv()


def get_commands_btn_view(
    message: Union[Message, CustomInteraction],
    cmds: List[Coroutine],
    cmd_kwargs: Optional[List[Dict[str, Any]]] = None
) -> CallbackButtonView:
    """Get a CallbackButtonView for a list of commands.

    :param message: The message to be used for the CallbackButtonView.
    :type message: Union[Message, CustomInteraction]
    :param cmds: The list of commands to be used for the CallbackButtonView.
    :type cmds: List[Coroutine]
    :param cmd_kwargs: The kwargs to be used for the Commands.
    :type cmd_kwargs: Optional[List[Dict[str, Any]]]
    :return: The CallbackButtonView.
    """
    def cb_wrapper(cmd, **kwargs):
        # pylint: disable=unused-argument
        async def callback(view, interaction):
            await cmd(message=CustomInteraction(interaction), **kwargs)
        return callback

    btns = [
        CallbackButton(
            callback=cb_wrapper(cmd, **kwargs),
            label=cmd.__name__.removeprefix("cmd_").title(),
            oneshot=False
        ) for cmd, kwargs in zip(cmds, (cmd_kwargs or [{} for _ in cmds]))
    ]
    return CallbackButtonView(buttons=btns)


# region Decoarators

# region Permissions


def admin_only(func: Callable):
    '''Only the admins can access these commands.

    :param func: The command to be decorated.
    :type func: Callable
    :return: The decorated function.
    :rtype: Callable
    '''
    func.__dict__["admin_only"] = True

    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if any([
            is_admin(message.author),
            is_owner(self.ctx, message.author),
            self.ctx.is_local
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
                        title=func.__name__.replace("cmd_", "/")
                    )
                )
            return func_with_callback(self, *args, message=message, **kwargs)
        func_name = func.__name__.replace("cmd_", "/")
        return message.reply(
            embed=get_embed(
                f'Command `{func_name}` can only be used by '
                'Pokegambler Admins.\n'
                'And this command can only be used in '
                'the official server.',
                embed_type="error"
            )
        )
    return wrapped


def dealer_only(func: Callable):
    '''Only the dealers can access these commands.

    :param func: The command to be decorated.
    :type func: Callable
    :return: The decorated function.
    :rtype: Callable
    '''
    func.__dict__["dealer_only"] = True

    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if any([
            is_dealer(message.author),
            is_owner(self.ctx, message.author),
            self.ctx.is_local
        ]):
            return func(self, *args, message=message, **kwargs)
        func_name = func.__name__.replace("cmd_", "/")
        command_view = get_commands_btn_view(
            message, [self.ctx.tradecommands.cmd_shop], [{"category": "Titles"}]
        )
        return message.reply(
            embed=get_embed(
                f'Command `{func_name}` can only be used by '
                'Pokegambler Dealers.\n'
                'And this command can only be used in '
                'the official server.',
                embed_type="error"
            ),
            view=command_view
        )
    return wrapped


def owner_only(func: Callable):
    '''Only the owners can access these commands.

    :param func: The command to be decorated.
    :type func: Callable
    :return: The decorated function.
    :rtype: Callable
    '''
    func.__dict__["owner_only"] = True

    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if is_owner(self.ctx, message.author):
            return func(self, *args, message=message, **kwargs)
        func_name = func.__name__.replace("cmd_", "/")
        self.logger.pprint(
            f'Command {func_name} can only be used by owners.',
            color="red",
            wrapped_func=func.__name__
        )
        return message.reply(
            embed=get_embed(
                f'Command `{func_name}` can only be used by '
                'the owners of PokeGambler.',
                embed_type="error"
            )
        )
    return wrapped

# endregion


def alias(alt_names: Union[List[str], str]):
    '''Add an alias to a function.

    :param alt_names: The alternative names of the function.
    :type alt_names: Union[List[str], str]
    :return: The decorated function.
    :rtype: Callable
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


def autocomplete(callback_dict: Dict[str, Coroutine]):
    '''Add an autocomplete callback dictionary to the command.

    :param callback_dict: The callback dictionary.
    :type callback_dict: Dict[str, Coroutine]
    :return: The decorated function.
    :rtype: Callable
    '''
    def decorator(func: Callable):
        func.__dict__["autocomplete"] = callback_dict

        @wraps(func)
        def wrapped(self, message, *args, **kwargs):
            return func(self, *args, message=message, **kwargs)
        return wrapped
    return decorator


def cache_images(func: Callable):
    '''Cache sent images for a particular user.

    :param func: The command to be decorated.
    :type func: Callable
    :return: The decorated function.
    :rtype: Callable
    '''
    if not func.__dict__.get("image_cache"):
        func.__dict__["image_cache"] = {}

    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        user = kwargs.get("user", message.author)
        if (
            user.id not in func.__dict__["image_cache"]
            or func.__dict__["image_cache"][user.id].kwargs != kwargs
        ):
            cache = func.__dict__["image_cache"]
            cache.update({
                user.id: ImageCacher(**{
                    **kwargs,
                    "user": user
                })
            })
            if user.id not in Commands.caches:
                Commands.caches.update({user.id: []})
            Commands.caches[user.id].append(
                cache[user.id]
            )
        if existing := func.__dict__["image_cache"][user.id].cached:
            return message.reply(content=existing)
        return func(self, *args, message=message, **kwargs)
    return wrapped


def check_completion(func: Callable):
    '''Checks if a command is already in progress for a user.

    :param func: The command to be decorated.
    :type func: Callable
    :return: The decorated function.
    :rtype: Callable
    '''
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        async def with_calback(self, message, *args, **kwargs):
            try:
                await func(self, *args, message=message, **kwargs)
            finally:
                if func.__name__ in self.ctx.pending_cmds:
                    self.ctx.pending_cmds[
                        func.__name__
                    ].remove(message.author.id)
        if self.ctx.pending_cmds.get(func.__name__, None):
            if message.author.id in self.ctx.pending_cmds[func.__name__]:
                return message.reply(
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


def cooldown(secs: int):
    '''Add a custom cooldown for a command.

    :param secs: The cooldown in seconds.
    :type secs: int
    :return: The decorated function.
    :rtype: Callable
    '''
    def decorator(func: Callable):
        func.__dict__["cooldown"] = secs

        @wraps(func)
        def wrapped(self, message, *args, **kwargs):
            return func(self, *args, message=message, **kwargs)
        return wrapped
    return decorator


def ctx_command(func: Callable):
    '''Marks a command as a context menu command.

    :param func: The command to be decorated.
    :type func: Callable
    :return: The decorated function.
    :rtype: Callable
    '''
    func.__dict__["ctx_command"] = True

    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        return func(self, *args, message=message, **kwargs)
    return wrapped


def defer(func: Callable):
    '''Defers a function to be executed later.

    :param func: The command to be decorated.
    :type func: Callable
    :return: The decorated function.
    :rtype: Callable
    '''
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if isinstance(message, CustomInteraction):
            async def deferred_exec():
                await message.response.defer()
                await func(self, *args, message=message, **kwargs)
            return deferred_exec()
        return func(self, *args, message=message, **kwargs)
    return wrapped


def ensure_item(func: Callable):
    '''Make sure that the Item with the given ID exists already.

    :param func: The command to be decorated.
    :type func: Callable
    :return: The decorated function.
    :rtype: Callable
    '''
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        command_view = get_commands_btn_view(
            message, [self.ctx.tradecommands.cmd_shop], [{}]
        )
        if not kwargs.get("itemid", None):
            return message.reply(
                embed=get_embed(
                    "You need to provide am Item ID.",
                    embed_type="error",
                    title="No Item ID"
                ),
                view=command_view
            )
        if not HexValidator(
            message=message
        ).check(kwargs["itemid"]):
            return message.reply(
                embed=get_embed(
                    "You need to provide a valid item ID.",
                    embed_type="error",
                    title="Invalid ID"
                ),
                view=command_view
            )
        item = Item.from_id(kwargs["itemid"])
        if not item:
            return message.reply(
                embed=get_embed(
                    "Could not find any item with the given ID.",
                    embed_type="error",
                    title="Item Does Not Exist"
                ),
                view=command_view
            )
        kwargs["item"] = item
        return func(self, message=message, **kwargs)
    return wrapped


def ensure_user(func: Callable):
    '''Make sure user ID is given in the command.

    :param func: The command to be decorated.
    :type func: Callable
    :return: The decorated function.
    :rtype: Callable
    '''
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if not kwargs.get("user_id", None):
            return message.reply(
                embed=get_embed(
                    "You need to provide a user ID.",
                    embed_type="error",
                    title="No User ID"
                )
            )
        if not IntegerValidator(
            message=message
        ).check(kwargs["user_id"]):
            return message.reply(
                embed=get_embed(
                    "You need to provide a valid user ID.",
                    embed_type="error",
                    title="Invalid ID"
                )
            )
        if not message.guild.get_member(int(kwargs["user_id"])):
            return message.reply(
                embed=get_embed(
                    "Unable to fetch this user.\n"
                    "Make sure they're still in the server.",
                    embed_type="error",
                    title="Invalid User"
                )
            )
        return func(self, *args, message=message, **kwargs)
    return wrapped


def model(models: Union[List[Model], Model]):  # noqa
    '''Marks a command with list of Models it is accessing.

    :param models: The models to be accessed.
    :type models: Union[\
List[:class:`~scripts.base.models.Model`], \
:class:`~scripts.base.models.Model`\
]
    :return: The decorated function.
    :rtype: Callable
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


def maintenance(func: Callable):
    '''Disable a broken/wip function to prevent it
    from affecting rest of the bot.

    :param func: The command to be decorated.
    :type func: Callable
    :return: The decorated function.
    :rtype: Callable
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
        return message.reply(
            embed=get_embed(
                f"The command {func_name} is under maintenance.\n"
                "Wait for a future update to see changes.",
                embed_type="error"
            )
        )
    return wrapped


def needs_ticket(name: str):
    '''Checks if user has the tickets in inventory.

    :param name: The name of the ticket.
    :type name: str
    :return: The command which triggered the check.
    :rtype: Callable
    '''
    def decorator(func: Callable):
        func.__dict__["ticket"] = name

        @wraps(func)
        def wrapped(self, message, *args, **kwargs):
            inv = Inventory(message.author)
            tickets = inv.from_name(name)
            if not tickets:
                async def no_tix():
                    await message.response.defer()
                    Shop.refresh_tradables()
                    PremiumShop.refresh_tradables()
                    itemid = Shop.from_name(name) or PremiumShop.from_name(name)
                    embed_content = f"You do not have any **{name}** tickets.\n" + \
                        "You can buy one from the Consumables Shop."
                    if itemid:
                        tkt = Shop.get_item(itemid) or PremiumShop.get_item(itemid)
                        price = (
                            tkt.price if not tkt.premium
                            else tkt.price // 10
                        )
                        curr = (
                            self.chip_emoji if not tkt.premium
                            else self.bond_emoji
                        )
                        embed_content = embed_content.removesuffix(".") + \
                            f" for **{price}** {curr}."
                        command_view = get_commands_btn_view(
                            message,
                            [self.ctx.tradecommands.cmd_buy],
                            [{"itemid": itemid}]
                        )
                    else:
                        command_view = get_commands_btn_view(
                            message,
                            [self.ctx.tradecommands.cmd_shop],
                            [{"category": "Consumables"}]
                        )
                    await message.reply(
                        embed=get_embed(
                            embed_content,
                            embed_type="error",
                            title="Insufficient Tickets"
                        ),
                        view=command_view
                    )
                return no_tix()
            kwargs["tickets"] = tickets
            return func(self, *args, message=message, **kwargs)
        return wrapped
    return decorator


def no_log(func: Callable):
    '''Pevents a command from being logged in the DB.
    Useful for debug related commands.

    :param func: The command to be decorated.
    :type func: Callable
    :return: The decorated function.
    :rtype: Callable
    '''
    func.__dict__["no_log"] = True

    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        return func(self, *args, message=message, **kwargs)
    return wrapped


def no_slash(func: Callable):
    '''Prevents a command from being triggered by a slash.

    :param func: The command to be decorated.
    :type func: Callable
    :return: The decorated function.
    :rtype: Callable
    '''
    func.__dict__["no_slash"] = True

    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        return func(self, *args, message=message, **kwargs)
    return wrapped


def os_only(func: Callable):
    '''These commands can only run in the official server.

    :param func: The command to be decorated.
    :type func: Callable
    :return: The decorated function.
    :rtype: Callable
    '''
    func.__dict__["os_only"] = True

    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if all([
            message.guild.id != self.ctx.official_server,
            not self.ctx.is_local
        ]):
            return message.reply(
                embed=get_embed(
                    "This command can only be used in the official server.",
                    embed_type="error",
                    title="Invalid Server"
                )
            )
        return func(self, *args, message=message, **kwargs)
    return wrapped


def suggest_actions(
    commands: List[Tuple[
        str, str, Optional[Dict[str, Any]]
    ]]
):
    '''Suggests actions to be taken when a command fails.

    :param commands: The commands to be suggested. (Category, Command, Kwargs)
    :type commands: List[Tuple[str, str, Optional[Dict[str, Any]]]]
    :return: The decorated function.
    :rtype: Callable
    '''
    def decorator(func: Callable):
        @wraps(func)
        def wrapped(self, message, *args, **kwargs):
            cmds = [
                (
                    getattr(
                        getattr(self.ctx, cmd[0]),
                        f"cmd_{cmd[1]}"
                    ),
                    cmd[2] if len(cmd) > 2 else {}
                )
                for cmd in commands
            ]
            cmds, cmd_kwargs = zip(*cmds)
            commands_view = get_commands_btn_view(message, cmds, cmd_kwargs)
            kwargs["view"] = commands_view
            return func(self, *args, message=message, **kwargs)
        return wrapped
    return decorator

# endregion


async def get_profile(
    ctx: PokeGambler,
    message: Message,
    user: Union[int, str, Member]
) -> Profiles:
    """Retrieves the Profile for a user (creates for new users).
    If the user is not found in the guild, returns None.

    :param ctx: The PokeGambler bot class.
    :type ctx: :class:`bot.PokeGambler`
    :param message: The message that triggered the command.
    :type message: :class:`discord.Message`
    :param user: The user to get the Profile for.
    :type user: Union[int, str, :class:`discord.Member`]
    :return: The Profile of the user.
    :rtype: :class:`~scripts.base.models.Profiles`
    """
    try:
        if isinstance(user, (int, str)):
            user = message.guild.get_member(int(user))
            if not user:
                official_guild = ctx.get_guild(
                    int(ctx.official_server)
                )
                user = official_guild.get_member(int(user))
            if not user:
                await message.reply(
                    embed=get_embed(
                        "Could not retrieve the user.",
                        embed_type="error",
                        title="User not found"
                    )
                )
                return None
        if user.bot:
            await message.reply(
                embed=get_embed(
                    "Bot accounts cannot have profiles.",
                    embed_type="error",
                    title="Bot Account found"
                )
            )
            return None
        return Profiles(user)
    except discord.HTTPException:
        await message.reply(
            embed=get_embed(
                "Could not retrieve the user.",
                embed_type="error",
                title="User not found"
            )
        )
        return None


class Commands(ABC):
    '''
    The Base command class which serves as the starting point for all commands.
    Can also be used to enable or disable entire categories.

    :param ctx: The PokeGambler client.
    :type ctx: :class:`bot.PokeGambler`
    '''
    caches = {}

    def __init__(
        self, ctx: PokeGambler,
        *args, **kwargs
    ):
        self.ctx = ctx
        self.logger = ctx.logger
        self.enabled = kwargs.get('enabled', True)
        self.alias = []
        self.chip_emoji = "<a:blinker:874624466771120188>"
        self.bond_emoji = "<:pokebond:874625119010586635>"
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
    def enable(self) -> bool:
        '''Quickly Enable a Commands Category module.

        :return: True
        :rtype: bool
        '''
        self.enabled = True
        return self.enabled

    @property
    def disable(self) -> bool:
        '''Quickly Disable a Commands Category module.

        :return: False
        :rtype: bool
        '''
        self.enabled = False
        return self.enabled

    async def paginate(
        self, message: Message,
        embeds: List[Embed],
        files: Optional[List[File]] = None,
        content: Optional[str] = None
    ):
        """Convenience method for conditional pagination.

        :param message: The Message which triggered the command.
        :type message: :class:`discord.Message`
        :param embeds: The Embeds to paginate.
        :type embeds: List[:class:`discord.Embed`]
        :param files: Optional Files to paginate.
        :type files: Optional[List[:class:`discord.File`]]
        :param content: Optional content to include in the message.
        :type content: Optional[str]
        """
        if not embeds and not files:
            if content:
                await message.reply(content=content)
            return
        if files:
            embeds = await self.__handle_files(
                message, embeds, files
            )
        if len(embeds) == 1:
            await message.reply(
                content=content,
                embed=embeds[0]
            )
            return
        sendables = {
            "embed": embeds[0]
        }
        if content:
            sendables["content"] = content
        for idx, embed in enumerate(embeds):
            if embed.footer.text is discord.Embed.Empty:
                embed.set_footer(text=f"{idx+1}/{len(embeds)}")
        sendables["view"] = Paginator(
            embeds, content=content
        )
        await message.reply(**sendables)
        await sendables["view"].wait()

    # pylint: disable=too-many-arguments
    async def handle_low_balance(
        self, message: Union[Message, CustomInteraction],
        user: Member, private: Optional[bool] = True,
        channel: Optional[TextChannel] = None,
        embed_content: Optional[str] = None,
        is_pokebonds: Optional[bool] = False
    ):
        """Handles a user with a low balance.

        :param message: The message that triggered the command.
        :type message: :class:`discord.Message`
        :param user: The user with a low balance.
        :type user: :class:`discord.Member`
        :param private: Whether to send the message in a DM.
        :type private: Optional[bool]
        :default private: True
        :param channel: The channel to send the message in.
        :type channel: Optional[:class:`discord.TextChannel`]
        :param embed_content: The content to include in the embed.
        :type embed_content: Optional[str]
        :param is_pokebonds: Whether the user has PokeBonds.
        :type is_pokebonds: Optional[bool]
        :default is_pokebonds: False
        """
        if not is_pokebonds:
            action_view = get_commands_btn_view(
                message, [
                    self.ctx.profilecommands.cmd_loot,
                    self.ctx.profilecommands.cmd_daily
                ]
            )
        else:
            action_view = LinkView(
                url="https://pokegambler.vercel.app/store",
                label="Buy Pokebonds",
                emoji=self.bond_emoji
            )

        emb_points = "\n🔶 ".join([
            "🔶 Every user gets 100 Pokechips as a starting bonus.",
            "You can earn more Pokechips from Loot, Daily or Gambling Minigames.",
            "You can buy more or exchange for other bot credits."
        ])
        curr = self.bond_emoji if is_pokebonds else self.chip_emoji
        emb = get_embed(
            embed_content or f"You do not have enough {curr} to do that.",
            embed_type="error",
            title="Insufficient Balance",
            fields={
                f"How to get more  {self.chip_emoji}": dedent(
                    f"```md\n{emb_points}\n```"
                )
            } if not is_pokebonds else None
        )
        if private:
            await dm_send(
                message, user, embed=emb,
                view=action_view
            )
        elif channel is None:
            raise ValueError("Channel is required for non-private messages.")
        else:
            await channel.send(
                content=user.mention,
                embed=emb,
                view=action_view
            )

    async def __handle_files(self, message, embeds, files):
        asset_chan = message.guild.get_channel(
            self.ctx.img_upload_channel
        ) or self.ctx.get_channel(
            self.ctx.img_upload_channel
        )
        if not embeds:
            embeds = [discord.Embed() for _ in files]
        msg = await asset_chan.send(files=files)
        for idx, embed in enumerate(embeds):
            embed.set_image(
                url=msg.attachments[idx].proxy_url
            )
        return embeds

    @classmethod
    def expire_cache(cls, user_id: int):
        '''Expires all the caches for a user.

        :param user_id: The user ID to expire caches for.
        :type user_id: int
        '''
        if user_id in cls.caches:
            for cache in cls.caches[user_id]:
                cache.expire()
