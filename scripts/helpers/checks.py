"""
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
