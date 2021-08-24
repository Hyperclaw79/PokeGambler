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
