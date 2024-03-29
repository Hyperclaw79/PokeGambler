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

This module is a compilation of user input validators.
"""

# pylint: disable=too-few-public-methods

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TYPE_CHECKING, Union
import re

from .utils import dm_send, get_embed

if TYPE_CHECKING:
    from discord import Embed, Message


class Validator(ABC):
    """
    Base class for all validators.

    :param message: The message which triggered the validation.
    :type message: :class:`discord.Message`
    :param on_error: A dictionary containing error heading and content.
    :type on_error: Dict
    :param dm_user: Route the message to user\'s DM?
    :type dm_user: bool
    :param notify: Notify the user if the validation fails?
    :type notify: bool
    """

    error_embed_title = ""
    error_embed_desc = ""
    error_embed_kwargs = {}
    null_embed_title = "No Value specified."
    null_embed_desc = "You need to provide a value."
    null_embed_kwargs = {}
    cleaner = None

    # pylint: disable=too-many-arguments
    def __init__(
        self, message: Message,
        on_error: Optional[Dict[str, str]] = None,
        on_null: Optional[Dict[str, str]] = None,
        dm_user: bool = False,
        notify: bool = True
    ):
        self.message = message
        on_error = on_error or {}
        on_null = on_null or {}
        if on_error.get("title"):
            self.error_embed_title = on_error.pop("title")
        if on_error.get("description"):
            self.error_embed_desc = on_error.pop("description")
        if on_null.get("title"):
            self.null_embed_title = on_null.pop("title")
        if on_null.get("description"):
            self.null_embed_desc = on_null.pop("description")
        self.error_embed_kwargs.update(on_error)
        self.null_embed_kwargs.update(on_null)
        self.dm_user = dm_user
        self.notify = notify

    @abstractmethod
    def check(self, value) -> bool:
        """
        Subclass specific logic for validation.
        """

    @property
    def error_embed(self) -> Embed:
        """Returns an error embed.

        :return: An error embed.
        :rtype: :class:`discord.Embed`
        """
        return get_embed(
            title=self.error_embed_title,
            embed_type="error",
            content=(
                self.error_embed_desc
                + "\nPlease retry the command."
            ),
            **self.error_embed_kwargs
        )

    @property
    def null_embed(self) -> Embed:
        """Returns a null embed.

        :return: A null embed.
        :rtype: :class:`discord.Embed`
        """
        return get_embed(
            title=self.null_embed_title,
            embed_type="error",
            content=(
                self.null_embed_desc
                + "\nPlease retry the command."
            ),
            **self.null_embed_kwargs
        )

    async def __notify(self, is_null: bool = False):
        """
        Performs the notifier function.
        """
        if not self.notify:
            return
        embed = self.null_embed if is_null else self.error_embed
        if not self.dm_user:
            await self.message.reply(embed=embed)
        else:
            await dm_send(
                self.message, self.message.author,
                embed=embed
            )

    async def validate(self, value: Any) -> bool:
        """Validates the given value.

        :param value: The value to be validated.
        :type value: str
        :return: True if the value is valid, False otherwise.
        :rtype: bool
        """
        if value is None:
            await self.__notify(is_null=True)
            return False
        if not self.check(value):
            await self.__notify()
            return False
        return True

    async def cleaned(self, value: Any) -> Any:
        """
        Cleans the given value after validation.
        """
        valid = await self.validate(value)
        if not valid:
            return None
        if self.cleaner is not None:
            # pylint: disable=not-callable
            return self.cleaner(value)
        return value


class ChainValidator(Validator):
    """
    Chain multiple validators together.

    :param validator_spec: Validator and Kwargs mapping.
    :type validator_spec: Dict[Validator, Dict[str, Any]]
    """
    def __init__(
        self, message: Message,
        validator_spec: Dict[Validator, Dict[str, Any]],
        **kwargs
    ):
        super().__init__(message=message, **kwargs)
        self.validators = [
            validator(**kwgs)
            for validator, kwgs in validator_spec.items()
        ]

    def check(self, value) -> bool:
        for validator in self.validators:
            if not validator.check(value):
                self.error_embed_title = validator.error_embed_title
                self.error_embed_desc = validator.error_embed_desc
                return False
        return True


class IntegerValidator(Validator):
    """
    Validates an integer value.
    """

    error_embed_title = "Invalid input"
    #:
    error_embed_desc = "Please enter a valid integer."
    cleaner = int

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def check(self, value: Union[str, int]) -> bool:
        return str(value).replace(',', '').isdigit()


class MaxValidator(IntegerValidator):
    """Validates a value is less than or equal to the maximum.

    :param max_value: The maximum value to validate against.
    :type max_value: int
    :kwargs: Additional keyword arguments to pass to the superclass.
    :type kwargs: Dict
    """

    def __init__(
        self, max_value: int, **kwargs
    ):
        super().__init__(**kwargs)
        self.max_value = max_value
        if not kwargs.get("on_error"):
            self.error_embed_title = "Input value is too high."
            self.error_embed_desc = "Value must be less than " + \
                f"than **{max_value}**."

    def check(self, value: Union[str, int]) -> bool:
        if not super().check(value):
            self.error_embed_title = super().error_embed_title
            self.error_embed_desc = super().error_embed_desc
            return False
        return int(str(value).replace(',', '')) <= self.max_value


class MinValidator(IntegerValidator):
    """
    Validates a value is greater than or equal to the minimum.

    :param min_value: The minimum value to validate against.
    :type min_value: int
    :kwargs: Additional keyword arguments to pass to the superclass.
    :type kwargs: Dict
    """

    def __init__(
        self, min_value: int, **kwargs
    ):
        super().__init__(**kwargs)
        self.min_value = min_value
        if not kwargs.get("on_error"):
            self.error_embed_title = "Input value is too low."
            self.error_embed_desc = "Value must be greater than " + \
                f"than **{min_value}**."

    def check(self, value: Union[str, int]) -> bool:
        if not super().check(value):
            self.error_embed_title = super().error_embed_title
            self.error_embed_desc = super().error_embed_desc
            return False
        return int(str(value).replace(',', '')) >= self.min_value


class MaxLengthValidator(Validator):
    """Validates a string to be of a certain length.

    :param max_length: The maximum permissible length of the string.
    :type max_length: int
    :kwargs: Additional keyword arguments to pass to the superclass.
    :type kwargs: Dict
    """
    error_embed_title = "Invalid Input"
    #:
    error_embed_desc = "Input value has too many characters."

    def __init__(self, max_length: int, **kwargs):
        super().__init__(**kwargs)
        self.max_length = max_length
        if not kwargs.get("on_error"):
            self.error_embed_desc += f"\nMax length: **{max_length}**"

    def check(self, value) -> bool:
        return len(value) <= self.max_length


class MinLengthValidator(Validator):
    """Validates a string to be of a certain length.

    :param min_length: The minimum permissible length of the string.
    :type min_length: int
    :kwargs: Additional keyword arguments to pass to the superclass.
    :type kwargs: Dict
    """
    error_embed_title = "Invalid Input"
    #:
    error_embed_desc = "Input value has too few characters."

    def __init__(self, min_length: int, **kwargs):
        super().__init__(**kwargs)
        self.min_length = min_length
        if not kwargs.get("on_error"):
            self.error_embed_desc += f"\nMin length: **{min_length}**"

    def check(self, value) -> bool:
        return len(value) >= self.min_length


class RegexValidator(Validator):
    """Validates a string against a regular expression.

    :param pattern: The regular expression to use for validation.
    :type pattern: str
    """

    def __init__(self, pattern: str, **kwargs):
        super().__init__(**kwargs)
        self.pattern = re.compile(pattern)

    def check(self, value) -> bool:
        return self.pattern.match(value) is not None


class HexValidator(RegexValidator):
    """
    Validates if a string is a hexadecimal value.
    """
    #:
    error_embed_title = "Invalid Hexadecimal value"

    def __init__(self, **kwargs):
        super().__init__(r'#?[0-9a-fA-F]{6}', **kwargs)

    @staticmethod
    def cleaner(hex_str: str) -> int:
        """
        Converts a hexadecimal string to an integer.
        :param hex_str: The hexadecimal string to convert.
        :type hex_str: str
        :return: The integer value of the hexadecimal string.
        :rtype: int
        """
        return int(hex_str.lstrip('#'), 16)


class ImageUrlValidator(RegexValidator):
    """
    Validates if a strings is an image URL.
    """
    #:
    error_embed_title = "Invalid image URL"
    #:
    error_embed_desc = "Only Png and JPG images are supported."

    def __init__(self, **kwargs):
        super().__init__(
            r'(?:http|https)://[^\s]+\.(?:png|jpg|jpeg)',
            **kwargs
        )


class UrlValidator(RegexValidator):
    """
    Validates if a string is a URL.
    """
    #:
    error_embed_title = "Invalid URL"

    def __init__(self, **kwargs):
        super().__init__(r'(?:http|https)://[^\s]+', **kwargs)


class ItemNameValidator(RegexValidator):
    """
    Validates if a string is a valid item name.
    """
    #:
    error_embed_title = "Invalid Item Name"

    def __init__(self, **kwargs):
        super().__init__(
            r'[A-Z](?:[a-z]+|[A-Z]*(?=[A-Z]|$))',
            **kwargs
        )
