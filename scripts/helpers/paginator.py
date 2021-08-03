"""
Custom Pagination Module for Discord Embeds.
"""

# pylint: disable=no-member,unused-argument

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING, List

import discord

from ..base.views import BaseView

if TYPE_CHECKING:
    from discord import Embed


class BidirectionalCycler:
    """
    A bidirectional iterator that can be used to cycle between items.
    """
    def __init__(self, iterable: List[Any]):
        self._iterable = iterable
        self._cursor = 0

    def forward(self):
        """
        Gets the next element in the iterable.
        """
        self._cursor = (self._cursor + 1) % len(self._iterable)
        return self._iterable[self._cursor]

    def backward(self):
        """
        Gets the previous element in the iterable.
        """
        self._cursor -= 1
        if self._cursor < 0:
            self._cursor += len(self._iterable)
        return self._iterable[self._cursor]


class Paginator(BaseView):
    """Custom Pagination for Discord Embeds

    Adds a reaction based pagination to discord Embeds.

    Attributes
    ----------
    embeds : list
        a list of embeds that need to be paginated
    content: str
        an optional content for the message
    """

    def __init__(
        self, embeds: List[Embed],
        content: Optional[str] = None,
        **kwargs
    ):
        super().__init__(timeout=None)
        self.embeds = BidirectionalCycler(embeds)
        self.content = content

    @discord.ui.button(label='👈')
    async def prev(
        self, button: discord.ui.Button,
        interaction: discord.Interaction
    ):
        """
        Move to the previous embed.

        Parameters
        ----------
        button : discord.ui.Button
            the button that was pressed
        interaction : discord.Interaction
            the interaction that was performed
        """
        await interaction.response.edit_message(
            embed=self.embeds.backward(),
            content=self.content
        )

    @discord.ui.button(label='👉')
    async def next(
        self, button: discord.ui.Button,
        interaction: discord.Interaction
    ):
        """
        Move to the next embed.

        Parameters
        ----------
        button : discord.ui.Button
            the button that was pressed
        interaction : discord.Interaction
            the interaction that was performed
        """
        await interaction.response.edit_message(
            embed=self.embeds.forward(),
            content=self.content
        )
