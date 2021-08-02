"""
Compilation of Discord UI Views
"""

# pylint: disable=unused-argument, no-member
# pylint: disable=too-few-public-methods

from __future__ import annotations
from datetime import datetime
import math
from typing import (
    Callable, Dict,
    Optional, TYPE_CHECKING
)

import discord

if TYPE_CHECKING:
    from ..commands.basecommand import Commands
    from ..commands.gamblecommands import GambleCommands


class BaseView(discord.ui.View):
    """
    The overriden Base class for Views.
    """
    notify: bool = True

    async def dispatch(self, module: Commands) -> bool:
        """
        Overriden method to track all views.
        """
        module.ctx.views[module.__class__.__name__].append(self)
        timedout = await super().wait()
        module.ctx.views[module.__class__.__name__].remove(self)
        return timedout


class SelectComponent(discord.ui.Select):
    """
    A Select Component that allows the user to choose an option.
    """
    def __init__(self, heading: str, options: Dict[str, str]):
        opts = [
            discord.SelectOption(
                label=str(label),
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
        """
        On Selecting a choice, execute the required function.
        """
        if not self.view.no_response:
            await interaction.response.send_message(
                f'Selected {self.values[0]}.',
                ephemeral=True
            )
        self.view.result = [
            key
            for key in self.opts
            if str(key) == self.values[0]
        ][0]
        self.view.stop()


class SelectView(BaseView):
    """
    A Select View that allows the user to choose an option.
    """
    def __init__(self, no_response=False, **kwargs):
        super().__init__()
        self.timeout = kwargs.pop('timeout', None)
        self.add_item(SelectComponent(**kwargs))
        self.no_response = no_response
        self.result = None


class Confirm(BaseView):
    """
    A simple View that gives us a confirmation menu.
    """
    def __init__(
        self, check: Optional[Callable] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.value = None
        self.check = check
        self.user = None

    @discord.ui.button(
        label="️️️️✔️",
        style=discord.ButtonStyle.green
    )
    async def confirm(
        self, button: discord.ui.Button,
        interaction: discord.Interaction
    ):
        """
        When the confirm button is pressed, set the inner value to True.
        """
        if (
            self.check is not None
            and not self.check(interaction.user)
        ):
            return
        self.value = True
        self.user = interaction.user
        self.stop()


class LinkView(BaseView):
    """
    A View that allows the user to visit a link.
    """
    def __init__(
        self, url: str,
        emoji: str, **kwargs
    ):
        super().__init__(**kwargs)
        self.add_item(
            discord.ui.Button(
                label='Invite Me',
                url=url,
                emoji=emoji
            )
        )


class GambleCounter(BaseView):
    """
    Tracks and updates the registration list
    for a gamble match.
    """

    # pylint: disable=too-many-arguments

    def __init__(
        self, gamble_cmd: GambleCommands,
        reg_embed: discord.Embed,
        fee: Optional[int] = 50,
        max_players: Optional[int] = 12,
        timeout: Optional[float] = 30.0
    ):
        super().__init__(timeout=timeout)
        self.registration_list = []
        self.start_time = datetime.now()
        self.gamble_cmd = gamble_cmd
        self.reg_embed = reg_embed
        self.fee = fee
        self.max_players = max_players

    @property
    def deadline(self):
        """
        Returns the deadline for the registration.
        """
        return int(
            30 - (
                datetime.now() - self.start_time
            ).total_seconds()
        )

    @property
    def transaction_fee(self):
        """
        Returns the transaction fee for the registration.
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
        """
        Register a user to the list.
        """
        # pylint: disable=import-outside-toplevel
        from .models import Profiles

        usr = interaction.user
        bal = Profiles(usr).get("balance")
        if bal < self.fee:
            await self.gamble_cmd.handle_low_bal(
                usr, (await interaction.original_message().channel)
            )
            return
        self.registration_list.append(interaction.user)
        await interaction.response.edit_message(
            embed=self.prep_embed(),
            view=self
        )
        if len(self.registration_list) == self.max_players:
            self.stop()

    def prep_embed(self):
        """
        Returns the embed for the registration list.
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
