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

Compilation of Discord UI Modals
"""

from __future__ import annotations
import inspect
from typing import (
    TYPE_CHECKING, Any, Callable,
    Dict, List, Optional, Union
)

from discord.ui import TextInput, Modal
from discord.enums import TextStyle

if TYPE_CHECKING:
    from discord import Interaction


class Lookup(dict):
    """
    A dictionary which iterates over values instead of keys.
    """
    def __iter__(self) -> List:
        """
        Iterate over values instead of keys.
        """
        return iter(self.values())

    def __getitem__(self, key: Union[int, str]) -> Any:
        """
        Gets the value of the key.
        If key is an index, it will return the value at that index.
        :param key: The key to get the value of.
        :type key: str
        """
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """
        Sets the value of the key.
        Forbid integer typed keys.
        :param key: The key to set the value of.
        :type key: str
        :param value: The value to set.
        """
        if isinstance(key, int):
            raise ValueError("Cannot use integer as key.")
        super().__setitem__(key, value)


class BaseModal(Modal):
    """
    A generic modal that can be used for getting user inputs.
    """
    def __init__(self, title, check=None, **kwargs):
        super().__init__(title=title, **kwargs)
        self.title = title
        self._check = check

    def add_short(self, text: str, **kwargs):
        """Adds a short text input to the modal.
        :param text: The text to display.
        :type text: str
        """
        return self.__get_textbox(
            text=text,
            style=TextStyle.short,
            **kwargs
        )

    def add_long(self, text: str, **kwargs):
        """Adds a long text input to the modal.
        :param text: The text to display.
        :type text: str
        """
        return self.__get_textbox(
            text=text,
            style=TextStyle.long,
            **kwargs
        )

    @property
    def results(self) -> Lookup[str, str]:
        """Returns the results of the modal.
        :return: The results of the modal.
        :rtype: :class:`~scripts.base.modals.Lookup`
        """
        return Lookup(
            {
                item.label: item.value
                for item in self.children
            }
        )

    # pylint: disable=unused-argument, no-self-use
    async def on_submit(self, interaction: Interaction):
        """
        Called when the modal is submitted.
        """
        await interaction.response.send_message(
            content="\u200B",
            ephemeral=True
        )

    def __get_textbox(self, text, style, **kwargs):
        placeholder = kwargs.pop("placeholder", "Enter a value...")
        self.add_item(
            TextInput(
                label=text,
                style=style,
                placeholder=placeholder,
                **kwargs
            )
        )
        return next(
            (
                item
                for item in self.children
                if isinstance(item, TextInput) and item.label == text
            ),
            None
        )


class ContentReplyModal(BaseModal):
    """
    A Modal which returns a content on submit.
    """
    def __init__(self, content, **kwargs):
        super().__init__(**kwargs)
        self.content = content

    async def on_submit(self, interaction: Interaction):
        """
        Called when the modal is submitted.
        """
        await interaction.response.send_message(
            content=self.content,
            ephemeral=True
        )


class EmbedReplyModal(BaseModal):
    """
    A Modal which returns an embed on submit.
    """
    def __init__(self, embed, **kwargs):
        super().__init__(**kwargs)
        self.embed = embed

    async def on_submit(self, interaction: Interaction):
        """
        Called when the modal is submitted.
        """
        await interaction.response.send_message(
            embed=self.embed,
            ephemeral=True
        )


class FullReplyModal(BaseModal):
    """
    A Modal which replies the kwargs on submit.
    """
    def __init__(self, reply: Dict[str, Any], **kwargs):
        super().__init__(**kwargs)
        self.reply = reply

    async def on_submit(self, interaction: Interaction):
        """
        Called when the modal is submitted.
        """
        await interaction.response.send_message(
            **self.reply,
            ephemeral=True
        )


class CallbackReplyModal(BaseModal):
    """
    A Modal which generates response from callback on submit.
    """
    def __init__(
        self, callback: Optional[Callable] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.callback = callback

    def add_callback(self, callback: Callable):
        """
        Adds a callback to the modal.
        :param callback: The callback to add.
        :type callback: Callable
        """
        self.callback = callback

    async def on_submit(self, interaction: Interaction):
        """
        Called when the modal is submitted.
        """
        if self.callback is None:
            return
        if inspect.iscoroutinefunction(self.callback):
            callback_res = await self.callback(self)
        else:
            callback_res = self.callback(self)
        await interaction.response.send_message(
            **callback_res, ephemeral=True
        )
