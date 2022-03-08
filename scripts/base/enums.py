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

Module which contains all the enums used in the bot.
"""

from enum import Enum, EnumMeta


class CustomEnumMeta(EnumMeta):
    """
    Override Enum to allow for case-insensitive enum names.
    Also adds a DEFAULT value to the Enum.

    :meta private:
    """
    def __getitem__(cls, name):
        try:
            return super().__getitem__(name.upper())
        except (TypeError, KeyError):
            return cls.DEFAULT


class CurrencyExchange(Enum, metaclass=CustomEnumMeta):
    """
    Holds exchange values for different pokebot currencies.
    """
    POKÉTWO = 10
    POKETWO = 10
    DEFAULT = 1
    # Add support for more pokebots if required.


class OptionTypes(Enum, metaclass=CustomEnumMeta):
    """
    Enum for the different types of options that can be used in a
    command.
    """
    SUB_COMMAND = 1
    SUB_COMMAND_GROUP = 2
    STRING = 3
    INT = 4
    INTEGER = 4
    BOOL = 5
    BOOLEAN = 5
    USER = 6
    CHANNEL = 7
    ROLE = 8
    MENTIONABLE = 9  # Do not use this.
    FLOAT = 10
    NUMBER = 10
    ATTACHMENT = 11
    DEFAULT = 3
