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

Compilation of Discord UI Views
"""

# pylint: disable=unused-argument, no-member
# pylint: disable=too-few-public-methods
# pylint: disable=attribute-defined-outside-init

from __future__ import annotations
from datetime import datetime
import math
from typing import (
    Callable, Dict, List,
    Optional, TYPE_CHECKING
)

import discord

if TYPE_CHECKING:
    from ..commands.basecommand import Commands
    from ..commands.gamblecommands import GambleCommands


class BaseView(discord.ui.View):
    """The overriden Base class for **discord.ui.View**.

    :param timeout: The timeout to wait for a response.,
        default is 180.0 seconds.
    :param check: A check function for validating the interaction.
    """
    notify: bool = True

    def __init__(
        self, timeout: Optional[float] = 180.0,
        check: Optional[Callable] = None
    ):
        super().__init__(timeout=timeout)
        self.check = check

    async def dispatch(self, module: Commands) -> bool:
        """Overriden method to track all views.

        :param module: The module to which the view belongs to.
        :type module: :class:`~scripts.commands.basecommand.Commands`
        :return: True if not timed out, False otherwise.
        :rtype: bool
        """
        module.ctx.views[module.__class__.__name__].append(self)
        timedout = await super().wait()
        module.ctx.views[module.__class__.__name__].remove(self)
        return timedout


class SelectComponent(discord.ui.Select):
    """A Select Component that allows the user to choose an option.

    :param heading: The heading of the component.
    :type heading: str
    :param options: The options for the Select.
    :type options: Dict
    :param serializer: The serializer to be used for the options.,
        defaults to ``str``.
    :type serializer: Optional[Callable]
    """
    def __init__(
        self, heading: str,
        options: Dict[str, str],
        serializer: Optional[Callable] = str
    ):
        self.serializer = serializer
        opts = [
            discord.SelectOption(
                label=serializer(label),
                description=str(description)
            )
            for label, description in options.items()
        ]
        super().__init__(
            placeholder=heading,
            min_values=1, max_values=1,
            options=opts
        )
        self.opts = options

    async def callback(self, interaction: discord.Interaction):
        """On Selecting a choice, execute the required function.

        :param interaction: The interaction that triggered the callback.
        :type interaction: :class:`discord.Interaction`
        """
        if (
            self.view.check is not None
            and not self.view.check(interaction)
        ):
            return
        value = [
            key
            for key in self.opts
            if self.serializer(key) == self.values[0]
        ][0]
        if isinstance(self.view, MultiSelectView):
            self.view.results.append(value)
            self.placeholder = self.values[0]
            self.disabled = True
            await interaction.message.edit(view=self.view)
            if all(
                child.values
                for child in self.view.children
            ):
                self.view.stop()
            return
        if isinstance(self.view, MorphView):
            await self.view.morph(interaction, value)
            return
        if not self.view.no_response:
            await interaction.response.send_message(
                f'Selected {self.values[0]}.',
                ephemeral=True
            )
        self.view.result = value
        self.view.stop()


class SelectView(BaseView):
    """A Select View that allows the user to choose an option.

    :param no_response: Whether an Ephemeral response should be sent.,
        defaults to True.
    :type no_response: bool
    """
    def __init__(self, no_response=True, **kwargs):
        timeout = kwargs.pop('timeout', 180)
        check = kwargs.pop('check', None)
        super().__init__(timeout=timeout, check=check)
        self.add_item(SelectComponent(**kwargs))
        self.no_response = no_response
        self.result = None


class MultiSelectView(BaseView):
    """A Multi Select View that requires the user to
    choose all Selects before proceeding.

    :param kwarg_list: The keyword arguments for the Selects.
    :type kwarg_list: List[dict]
    :param kwargs: Additional keyword arguments for the View.
    :type kwargs: dict
    """
    def __init__(self, kwarg_list: List[Dict], **kwargs):
        timeout = kwargs.pop('timeout', 180)
        check = kwargs.pop('check', None)
        super().__init__(timeout=timeout, check=check)
        self.no_response = True
        self.results = []
        for kwargs in kwarg_list:
            self.add_item(SelectComponent(**kwargs))


class Confirm(BaseView):
    """
    A simple View that gives us a confirmation menu.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.value = None
        self.user = None

    @discord.ui.button(
        label="️️️️✔️",
        style=discord.ButtonStyle.green
    )
    async def confirm(
        self, button: discord.ui.Button,
        interaction: discord.Interaction
    ):
        """When the confirm button is pressed, set the inner value to True.

        :param button: The button that was pressed.
        :type button: :class:`discord.ui.Button`
        :param interaction: The interaction that triggered the callback.
        :type interaction: :class:`discord.Interaction`
        """
        if (
            self.check is not None
            and not self.check(interaction)
        ):
            return
        self.value = True
        self.user = interaction.user
        self.stop()


class LinkView(BaseView):
    """A View that allows the user to visit a link.

    :param url: The url to be linked to.
    :type url: str
    :param label: The text to be displayed on the button.
    :type label: str
    :param emoji: The emoji to be displayed on the button.
    :type emoji: Optional[str]
    """
    def __init__(
        self, url: str,
        label: str = 'Invite Me',
        emoji: Optional[str] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.add_item(
            discord.ui.Button(
                label=label,
                url=url,
                emoji=emoji
            )
        )


class EmojiButton(BaseView):
    """A read-only View with an emoji Button.

    :param emoji: The emoji to be displayed.
    :type emoji: str
    """
    def __init__(self, emoji: str, **kwargs):
        super().__init__(**kwargs)
        self.add_item(
            discord.ui.Button(
                label='',
                emoji=emoji
            )
        )


class GambleCounter(BaseView):
    """A view which tracks and updates the registration list
    for a gamble match.

    :param gamble_cmd: The GambleCommands module.
    :type gamble_cmd: :class:`~scripts.commands.gamblecommands.GambleCommands`
    :param gamble_thread: The discord thread where the match is taking place.
    :type gamble_thread: :class:`discord.Thread`
    :param reg_embed: The discord embed to be used for registration.
    :type reg_embed: :class:`discord.Embed`
    :param fee: The fee for the gamble match., defaults to 50.
    :type fee: Optional[int]
    :param max_players: The maximum number of players for the match,
        defaults to 12.
    :type max_players: Optional[int]
    :param timeout: The timeout for the registration, defaults to 180.
    """

    # pylint: disable=too-many-arguments

    def __init__(
        self, gamble_cmd: GambleCommands,
        gamble_thread: discord.Thread,
        reg_embed: discord.Embed,
        fee: Optional[int] = 50,
        max_players: Optional[int] = 12,
        timeout: Optional[float] = 30.0
    ):
        super().__init__(timeout=timeout)
        self.registration_list = []
        self.start_time = datetime.now()
        self.gamble_cmd = gamble_cmd
        self.gamble_thread = gamble_thread
        self.reg_embed = reg_embed
        self.fee = fee
        self.max_players = max_players

    @property
    def deadline(self) -> int:
        """Returns the deadline (in seconds) for the registration.

        :return: The deadline for the registration.
        :rtype: int
        """
        return int(
            30 - (
                datetime.now() - self.start_time
            ).total_seconds()
        )

    @property
    def transaction_fee(self) -> str:
        """Calculates the transaction fee for the registration.

        .. note::
            The Fee scales up by 5% for every extra player more than 12.

        :return: The transaction fee for the registration.
        :rtype: str
        """
        return str(
            10 + 5 * math.floor(
                max(0, len(self.registration_list) - 12) / 3
            )
        )

    @discord.ui.button(label='➕')
    async def register_user(
        self, button: discord.ui.Button,
        interaction: discord.Interaction
    ):
        """Register a user to the list.

        :param button: The button that was pressed.
        :type button: :class:`discord.ui.Button`
        :param interaction: The interaction that triggered the callback.
        :type interaction: :class:`discord.Interaction`
        """
        # pylint: disable=import-outside-toplevel
        from .models import Profiles

        usr = interaction.user
        bal = Profiles(usr).get("balance")
        if bal < self.fee:
            await self.gamble_cmd.handle_low_bal(
                usr, interaction.message.channel
            )
            return
        if interaction.user not in self.registration_list:
            self.registration_list.append(interaction.user)
            await self.gamble_thread.add_user(interaction.user)
            await interaction.response.edit_message(
                embed=self.prep_embed(),
                view=self
            )
            if len(self.registration_list) == self.max_players:
                self.stop()

    def prep_embed(self) -> discord.Embed:
        """Returns the embed for the registration list.

        :return: The embed for the registration list.
        :rtype: :class:`discord.Embed`
        """
        embed = self.reg_embed.copy()
        embed.description = self.reg_embed.description.replace(
            "<tr>", self.transaction_fee
        )
        embed.set_footer(
            text=f"Press ➕ (within {self.deadline} secs)"
            " to be included in the match."
        )
        embed.add_field(
            name=f"Current Participants "
            f"『{len(self.registration_list)}/{self.max_players}』",
            value=', '.join(
                player.name
                for player in self.registration_list
            ),
            inline=False
        )
        embed.add_field(
            name="Pokechips in the pot",
            value=f"{self.fee * len(self.registration_list)} "
            f"{self.gamble_cmd.chip_emoji}",
            inline=False
        )
        return embed


class MoreInfoView(BaseView):
    """A view that morphs the message content/embed on button click.

    :param content: The content to be displayed after the button is clicked.
    :type content: Optional[str]
    :param embed: The embed to be displayed after the button is clicked.
    :type embed: Optional[:class:`discord.Embed`]
    """
    def __init__(
        self, content: Optional[str] = None,
        embed: Optional[discord.Embed] = None,
        overwrite: Optional[bool] = True,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.content = content
        self.embed = embed
        self.overwrite = overwrite

    @discord.ui.button(label='More Info', emoji='ℹ')
    async def more_info(
        self, button: discord.ui.Button,
        interaction: discord.Interaction
    ):
        """Morph the message content/embed on button click.

        :param button: The button that was pressed.
        :type button: :class:`discord.ui.Button`
        :param interaction: The interaction that triggered the callback.
        :type interaction: :class:`discord.Interaction`
        """
        if self.overwrite:
            await interaction.message.edit(**{
                "embed": self.embed,
                "content": self.content,
                "view": None
            })
        else:
            msg_kwargs = {"view": None}
            if self.content is not None:
                msg_kwargs["content"] = self.content
            if self.embed is not None:
                msg_kwargs["embed"] = self.embed
            await interaction.message.edit(**msg_kwargs)
        self.stop()


class MorphView(BaseView):
    """Dynamically Morphing Embed based on Select component's value.

    :param info_dict: The mapping between Select label and its embed.
    :type info_dict: Dict[str, :class:`discord.Embed`]
    """
    def __init__(self, info_dict: Dict[str, discord.Embed]):
        super().__init__(timeout=None)
        self.info_dict = info_dict
        self.add_item(
            SelectComponent(
                heading="Choose Commands Category.",
                options={
                    key: ""
                    for key in info_dict
                }
            )
        )

    async def morph(self, interaction, label: str):
        """Morph the message content/embed on SelectComponent's label change.

        :param interaction: The interaction that triggered the callback.
        :type interaction: :class:`discord.Interaction`
        :param label: The new label of the SelectComponent.
        :type label: str
        """
        self.children[0].placeholder = label
        await interaction.message.edit(
            embed=self.info_dict[label],
            view=self
        )
