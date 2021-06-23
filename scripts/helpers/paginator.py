"""
Custom Pagination Module for Discord Embeds.
"""

# pylint: disable=inconsistent-return-statements


from __future__ import annotations

import asyncio
from typing import Optional, TYPE_CHECKING, List

import discord

if TYPE_CHECKING:
    from bot import PokeGambler
    from discord import Embed, File, Message

class Paginator:
    """Custom Pagination for Discord Embeds

    Adds a reaction based pagination to discord Embeds.

    Attributes
    ----------
    message : discord.Message
        the message which triggered the command
    base : discord.Message
        the message with the first embed, serving as the root
    embeds : list
        a list of embeds that need to be paginated
    ctx : PokeGambler
        an instance of the main PokeGambler class

    Methods
    -------
    run(content="")
        Attaches the reactions and pagination functionality to base message.
        You can also send custom content, along with the embeds.
    """

    # pylint: disable=too-few-public-methods

    def __init__(
        self, ctx: PokeGambler,
        message: Message, base: Message,
        embeds: List[Embed],
        files: Optional[List[File]] = None
    ):
        self.message = message
        self.base = base
        self.pointers = ['👈', '👉', '❌']
        self.embeds = embeds
        self.files = files
        self.cursor = 0
        self.ctx = ctx

    async def _add_handler(self):
        def reaction_check(reaction, user):
            if all([
                user == self.message.author,
                reaction.message.id == self.base.id,
                reaction.emoji in self.pointers
            ]):
                return True
        while True:
            reaction, _ = await discord.Client.wait_for(
                self.ctx, event='reaction_add', check=reaction_check
            )
            option = self.pointers.index(reaction.emoji)
            if option == 1 and self.cursor < len(self.embeds) - 1:
                self.cursor += 1
                if (
                    self.files
                    and len(self.files) > self.cursor
                    and not self.embeds[self.cursor].image.url
                ):
                    msg = await self.base.guild.get_channel(
                        self.ctx.configs["img_upload_channel"]
                    ).send(file=self.files[self.cursor])
                    self.embeds[self.cursor].set_image(
                        url=msg.attachments[0].proxy_url
                    )
                await self.base.edit(embed=self.embeds[self.cursor])
            elif option == 0 and self.cursor > 0:
                self.cursor -= 1
                await self.base.edit(embed=self.embeds[self.cursor])
            elif option == 2:
                await self.base.delete()
                break
            else:
                pass

    async def _remove_handler(self):
        def reaction_check(reaction, user):
            if all([
                user == self.message.author,
                reaction.message.id == self.base.id,
                reaction.emoji in self.pointers
            ]):
                return True
        while True:
            reaction, _ = await discord.Client.wait_for(
                self.ctx, event='reaction_remove', check=reaction_check
            )
            option = self.pointers.index(reaction.emoji)
            if option == 1 and self.cursor < len(self.embeds) - 1:
                self.cursor += 1
                if (
                    self.files
                    and len(self.files) > self.cursor
                    and not self.embeds[self.cursor].image.url
                ):
                    msg = await self.base.guild.get_channel(
                        self.ctx.configs["img_upload_channel"]
                    ).send(file=self.files[self.cursor])
                    self.embeds[self.cursor].set_image(
                        url=msg.attachments[0].proxy_url
                    )
                await self.base.edit(embed=self.embeds[self.cursor])
            elif option == 0 and self.cursor > 0:
                self.cursor -= 1
                await self.base.edit(embed=self.embeds[self.cursor])
            else:
                pass

    async def run(self, content: str = ""):
        """
        Creates the pagination task and runs in the background.
        """
        await self.base.edit(content=content, embed=self.embeds[0])
        for pointer in self.pointers:
            await self.base.add_reaction(pointer)
        asyncio.create_task(self._add_handler())
        asyncio.create_task(self._remove_handler())
