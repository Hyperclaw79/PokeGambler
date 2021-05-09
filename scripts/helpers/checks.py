"""
A couple of wait_for checks.
"""
# pylint: skip-file

def user_check(msg, message, chan=None):
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
    message, user,
    rctn, usr,
    chan=None, emoji=None
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
