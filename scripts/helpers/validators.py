"""
This module is a compilation of user input validators.
"""

# pylint: disable=too-few-public-methods

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Optional, TYPE_CHECKING
import re

from .utils import dm_send, get_embed

if TYPE_CHECKING:
    from discord import Embed, Message


class Validator(ABC):
    """
    Base class for all validators.
    """

    error_embed_title = ""
    error_embed_desc = ""
    error_embed_kwargs = {}

    def __init__(
        self, message: Message,
        on_error: Optional[Dict[str, str]] = None,
        dm_user: bool = False
    ):
        self.message = message
        on_error = on_error or {}
        if on_error.get("title"):
            self.error_embed_title = on_error.pop("title")
        if on_error.get("description"):
            self.error_embed_desc = on_error.pop("description")
        self.error_embed_kwargs.update(on_error)
        self.dm_user = dm_user

    @abstractmethod
    def check(self, value) -> bool:
        """
        Subclass specific logic for validation.
        """

    @property
    def error_embed(self) -> Embed:
        """
        Returns an error embed.
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

    async def __notify(self):
        """
        Returns the notifier function.
        """
        if not self.dm_user:
            await self.message.channel.send(
                embed=self.error_embed
            )
        else:
            await dm_send(
                self.message, self.message.author,
                embed=self.error_embed
            )

    async def validate(self, value) -> bool:
        """
        Validates the given value.
        """
        if not self.check(value):
            await self.__notify()
            return False
        return True


class IntegerValidator(Validator):
    """
    Validates an integer value.
    """

    error_embed_title = "Invalid input"
    error_embed_desc = "Please enter a valid integer."

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def check(self, value) -> bool:
        return str(value).isdigit()


class MaxValidator(IntegerValidator):
    """
    Validates a value is less than or equal to the maximum.
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

    def check(self, value) -> bool:
        if not super().check(value):
            self.error_embed_title = super().error_embed_title
            self.error_embed_desc = super().error_embed_desc
            return False
        return int(value) <= self.max_value


class MinValidator(IntegerValidator):
    """
    Validates a value is greater than or equal to the minimum.
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

    def check(self, value) -> bool:
        if not super().check(value):
            self.error_embed_title = super().error_embed_title
            self.error_embed_desc = super().error_embed_desc
            return False
        return int(value) >= self.min_value


class MinMaxValidator(Validator):
    """
    Validates a value between a min and max.
    """

    def __init__(
        self, min_value: int,
        max_value: int, **kwargs
    ):
        super().__init__(**kwargs)
        self.int_validator = IntegerValidator(**kwargs)
        self.min_validator = MinValidator(min_value, **kwargs)
        self.max_validator = MaxValidator(max_value, **kwargs)

    def check(self, value) -> bool:
        int_result = self.int_validator.check(value)
        if not int_result:
            self.error_embed_title = "Invalid input"
            self.error_embed_desc = (
                f"Value must be between **{self.min_validator.min_value}**"
                f" and **{self.max_validator.max_value}**."
            )
            return False
        if not self.min_validator.check(value):
            self.error_embed_title = self.min_validator.error_embed_title
            self.error_embed_desc = self.min_validator.error_embed_desc
            return False
        if not self.max_validator.check(value):
            self.error_embed_title = self.max_validator.error_embed_title
            self.error_embed_desc = self.max_validator.error_embed_desc
            return False
        return True


class MaxLengthValidator(Validator):
    """
    Validates a string of a certain length.
    """
    error_embed_title = "Invalid Input"
    error_embed_desc = "Input value has too many characters."

    def __init__(self, max_length: int, **kwargs):
        super().__init__(**kwargs)
        self.max_length = max_length
        if not kwargs.get("on_error"):
            self.error_embed_desc += f"\nMax length: **{max_length}**"

    def check(self, value) -> bool:
        return len(value) <= self.max_length


class RegexValidator(Validator):
    """
    Validates a string against a regex.
    """

    def __init__(self, pattern: str, **kwargs):
        super().__init__(**kwargs)
        self.pattern = re.compile(pattern)

    def check(self, value) -> bool:
        return self.pattern.match(value) is not None


class HexValidator(RegexValidator):
    """
    Validates a hexadecimal value.
    """
    error_embed_title = "Invalid Hexadecimal value"

    def __init__(self, **kwargs):
        super().__init__(r'#?[0-9a-fA-F]*', **kwargs)


class ImageUrlValidator(RegexValidator):
    """
    Validates an image URL.
    """
    error_embed_title = "Invalid image URL"

    def __init__(self, **kwargs):
        super().__init__(
            r'(?:http|https)://[^\s]+\.(?:png|jpg|jpeg)',
            **kwargs
        )


class UrlValidator(RegexValidator):
    """
    Validates a URL.
    """
    error_embed_title = "Invalid URL"

    def __init__(self, **kwargs):
        super().__init__(r'(?:http|https)://[^\s]+', **kwargs)
