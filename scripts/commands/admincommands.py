"""
Administration Commands
"""

# pylint: disable=unused-argument

from ..helpers.utils import (
    get_embed, get_profile,
    is_admin, is_owner
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
