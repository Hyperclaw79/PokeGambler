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

A couple of wait_for checks.
"""
# pylint: skip-file

from typing import Optional, Union
from discord import (
    Message, TextChannel,
    Member, Reaction, Emoji
)


def user_check(
    msg: Message, message: Message,
    chan: Optional[TextChannel] = None
):
    """ User message check. """
    if not chan:
        chan = message.channel
    checks = [
        msg.channel.id == chan.id,
        msg.author.id == message.author.id,
    ]
    if all(checks):
        return True


def user_rctn(
    message: Message, user: Member,
    rctn: Reaction, usr: Member,
    chan: Optional[TextChannel] = None,
    emoji: Optional[Union[Emoji, str]] = None
):
    """ User reaction check. """
    if not chan:
        chan = message.channel
    checks = [
        usr.id == user.id,
        rctn.message.channel.id == chan.id
    ]
    if emoji:
        checks.append(
            rctn.emoji == emoji
        )
    if all(checks):
        return True
