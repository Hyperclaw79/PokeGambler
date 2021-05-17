"""
Administration Commands
"""

# pylint: disable=unused-argument

import asyncio
import os

import discord
from ..helpers.checks import user_check
from ..helpers.utils import (
    dedent, get_embed, get_profile,
    is_admin, is_owner, wait_for
)
from ..base.models import Blacklist
from .basecommand import Commands, admin_only, alias


class AdminCommands(Commands):
    """
    Commands that deal with the moderation tasks.
    Only Admins and Owners will have access to these.
    """

    @admin_only
    @alias("upd_bal")
    async def cmd_update_balance(self, message, args=None, **kwargs):
        """Updates user's balance.
        $```scss
        {command_prefix}update_balance user_id balance
        ```$

        @`🛡️ Admin Command`
        Overwrite a user's account balance.@

        ~To overwrite balance of user with ID 12345:
            ```
            {command_prefix}update_balance 12345 100
            ```~
        """
        if not args:
            await message.channel.send(
                embed=get_embed(
                    "You need to provide a user ID.",
                    embed_type="error",
                    title="No User ID"
                )
            )
            return
        if len(args) < 2:
            await message.channel.send(
                embed=get_embed(
                    "You need to provide a user ID and balance.",
                    embed_type="error",
                    title="Not enough args"
                )
            )
            return
        user_id = int(args[0])
        try:
            balance = int(args[1])
        except ZeroDivisionError:
            await message.channel.send(
                embed=get_embed(
                    "Good try but bad luck.",
                    embed_type="error",
                    title="Invalid input"
                )
            )
            return
        profile = await get_profile(self.database, message, user_id)
        if not profile:
            return
        profile.update(balance=balance)
        await message.add_reaction("👍")

    @admin_only
    @alias("chips+")
    async def cmd_add_chips(self, message, args=None, **kwargs):
        """Adds chips to user's balance.
        $```scss
        {command_prefix}add_chips user_id amount [--purchased]
        ```$

        @`🛡️ Admin Command`
        Adds <:pokechip:840469159242760203> to a user's account.
        Use the `--purchased` kwarg if the chips were bought.@

        ~To give 50 <:pokechip:840469159242760203> to user with ID 12345:
            ```
            {command_prefix}add_chips 12345 50
            ```
        To add 500 bought/exchanged <:pokechip:840469159242760203> to user 67890:
            ```
            {command_prefix}add_chips 67890 500 --purchased
            ```~
        """
        if not args:
            await message.channel.send(
                embed=get_embed(
                    "You need to provide a user ID.",
                    embed_type="error",
                    title="No User ID"
                )
            )
            return
        if len(args) < 2:
            await message.channel.send(
                embed=get_embed(
                    "You need to provide a user ID and pokechips.",
                    embed_type="error",
                    title="Not enough args"
                )
            )
            return
        user_id = int(args[0])
        try:
            increment = int(args[1])
        except ZeroDivisionError:
            await message.channel.send(
                embed=get_embed(
                    "Good try but bad luck.",
                    embed_type="error",
                    title="Invalid input"
                )
            )
            return
        profile = await get_profile(self.database, message, user_id)
        if not profile:
            return
        data = profile.get()
        balance = data["balance"]
        purchased_chips = data["purchased_chips"]
        balance += increment
        if kwargs.get("purchased", False):
            purchased_chips += increment
        profile.update(
            balance=balance,
            purchased_chips=purchased_chips
        )
        await message.add_reaction("👍")

    @admin_only
    @alias("rst_usr")
    async def cmd_reset_user(self, message, args=None, **kwargs):
        """Completely resets a user's profile.
        $```scss
        {command_prefix}reset_user user_id
        ```$

        @`🛡️ Admin Command`
        Completely resets a user's profile to the starting stage.@

        ~To reset user with ID 12345:
            ```
            {command_prefix}reset_user 12345
            ```~
        """
        if not args:
            await message.channel.send(
                embed=get_embed(
                    "You need to provide a user ID.",
                    embed_type="error",
                    title="No User ID"
                )
            )
            return
        user_id = int(args[0])
        profile = await get_profile(self.database, message, user_id)
        profile.reset()
        await message.add_reaction("👍")

    @admin_only
    @alias("upd_usr")
    async def cmd_update_user(self, message, args=None, **kwargs):
        """Updates a user's profile.
        $```scss
        {command_prefix}update_user user_id --param value
        ```$

        @`🛡️ Admin Command`
        Updates a user's profile based on the kwargs.@

        ~To update num_wins of user with ID 12345:
            ```
            {command_prefix}update_user 12345 --num_wins 10
            ```~
        """
        if not args:
            await message.channel.send(
                embed=get_embed(
                    "You need to provide a user ID.",
                    embed_type="error",
                    title="No User ID"
                )
            )
            return
        user_id = int(args[0])
        kwargs.pop("mentions", [])
        profile = await get_profile(self.database, message, user_id)
        if not profile:
            return
        try:
            profile.update(**kwargs)
        except Exception as excp: # pylint: disable=broad-except
            await message.channel.send(
                embed=get_embed(
                    "Good try but bad luck.",
                    embed_type="error",
                    title="Invalid input"
                )
            )
            self.logger.pprint(
                f"{message.author} triggered cmd_update_user with {kwargs}.\n"
                f"Error: {excp}",
                color="red",
                timestamp=True
            )
            return
        await message.add_reaction("👍")

    @admin_only
    @alias("bl")
    async def cmd_blacklist_user(self, message, args=None, **kwargs):
        """Blacklists a user from using PokeGambler.
        $```scss
        {command_prefix}blacklist_user user_id [--reason text]
        ```$

        @`🛡️ Admin Command`
        Blacklists a user from using PokeGambler until pardoned.
        A reason can be provided (recommended) using --reason kwarg.@

        ~To blacklist a user with ID 12345:
            ```
            {command_prefix}blacklist_user 12345
            ```
        ~To blacklist a user with ID 67890 for spamming:
            ```
            {command_prefix}blacklist_user 67890 --reason spamming
            ```~
        """
        if not args:
            await message.channel.send(
                embed=get_embed(
                    "You need to provide a user ID.",
                    embed_type="error",
                    title="No User ID"
                )
            )
            return
        user_id = int(args[0])
        user = message.guild.get_member(user_id)
        if any([
            is_admin(user),
            is_owner(self.ctx, user)
        ]):
            await message.channel.send(
                embed=get_embed(
                    "You cannot blacklist owners and admins!",
                    embed_type="error",
                    title="Invalid User"
                )
            )
            return
        Blacklist(
            self.database,
            user, message.author,
            reason=kwargs.get("reason", None)
        ).save()
        await message.add_reaction("👍")

    @admin_only
    @alias("pardon")
    async def cmd_pardon_user(self, message, args=None, **kwargs):
        """Pardons a blacklisted user.
        $```scss
        {command_prefix}pardon_user user_id
        ```$

        @`🛡️ Admin Command`
        Pardons a blacklisted user so that they can use PokeGambler again.@

        ~To pardon a user with ID 12345:
            ```
            {command_prefix}pardon 12345
            ```~
        """
        if not args:
            await message.channel.send(
                embed=get_embed(
                    "You need to provide a user ID.",
                    embed_type="error",
                    title="No User ID"
                )
            )
            return
        user_id = int(args[0])
        user = message.guild.get_member(user_id)
        if any([
            is_admin(user),
            is_owner(self.ctx, user)
        ]):
            await message.channel.send(
                embed=get_embed(
                    "Owners and Admins are never blacklisted.",
                    embed_type="error",
                    title="Invalid User"
                )
            )
            return
        if not self.database.is_blacklisted(args[0]):
            await message.channel.send(
                embed=get_embed(
                    "User is not blacklisted.",
                    embed_type="error",
                    title="Invalid User"
                )
            )
            return
        Blacklist(self.database, user, message.author).pardon()
        await message.add_reaction("👍")

    @admin_only
    async def cmd_announce(self, message, **kwargs):
        """Send an announcement.
        $```scss
        {command_prefix}announce
        ```$

        @`🛡️ Admin Command`
        Make PokeGambler send an announcement in the announcement channel.@

        ~To start an announcement:
            ```
            {command_prefix}announce
            ```~
        """
        start_msg = await message.channel.send(
            embed=get_embed(
                'Enter your announcement message:\n>_'
            )
        )
        reply = await wait_for(
            message.channel, self.ctx, init_msg=start_msg,
            check=lambda msg: user_check(msg, message),
            timeout="inf"
        )
        content = reply.content
        chan = message.guild.get_channel(
            int(os.getenv("ANNOUNCEMENT_CHANNEL"))
        )
        await chan.send(content=content)
        await reply.add_reaction("👍")

    @admin_only
    async def cmd_autogambler(self, message, **kwargs):
        """Self-assign Gambler Role.
        $```scss
        {command_prefix}autogambler
        ```$

        @`🛡️ Admin Command`
        Creates a self-assign message, for Gamblers role, in the announcement channel.@
        """
        async def role_assign(self, gamb_msg, chan):
            # pylint: disable=inconsistent-return-statements
            def rctn_check(rctn, usr):
                if usr.id != self.ctx.user.id:
                    checks = [
                        rctn.emoji.name == "pokechip",
                        rctn.message.id == gamb_msg.id,
                        not usr.bot
                    ]
                    if all(checks):
                        return True
            gambler_role = [
                role
                for role in message.guild.roles
                if role.name.lower() == "gamblers"
            ][0]
            while True:
                _, user = await wait_for(
                    chan, self.ctx, event="reaction_add",
                    init_msg=gamb_msg,
                    check=rctn_check,
                    timeout="inf"
                )
                if gambler_role not in user.roles:
                    await user.add_roles(gambler_role)
        chan = message.guild.get_channel(
            int(os.getenv("ANNOUNCEMENT_CHANNEL"))
        )
        content = """React with <:pokechip:840469159242760203> to be assigned the `Gamblers` role.
        With this role you'll be able to participate in the special gamble matches.
        You'll also be pinged for random Treasure drops (TBI).
        """
        gamb_msg = await message.guild.get_channel(
            int(os.getenv("ANNOUNCEMENT_CHANNEL"))
        ).send(
            content="Hey @everyone",
            embed=get_embed(
                dedent(content),
                title="React for Gamblers Role"
            )
        )
        await gamb_msg.add_reaction("<:pokechip:840469159242760203>")
        await asyncio.sleep(2.0)
        gamb_msg = discord.utils.find(
            lambda msg: msg.id == gamb_msg.id,
            self.ctx.cached_messages
        )
        self.ctx.loop.create_task(
            role_assign(self, gamb_msg, chan)
        )
