"""
Administration Commands
"""

# pylint: disable=unused-argument

import asyncio
from dataclasses import MISSING, fields
import os
import json
from typing import Dict, Type

import discord
from ..helpers.checks import user_check
from ..helpers.utils import (
    dedent, get_embed, get_enum_embed,
    is_admin, is_owner, wait_for
)
from ..base.models import Blacklist, Inventory, Profile
from ..base.items import Item, Tradable
from .basecommand import (
    Commands, admin_only, alias,
    ensure_user, get_profile, ensure_item
)


class AdminCommands(Commands):
    """
    Commands that deal with the moderation tasks.
    Only Admins and Owners will have access to these.
    """

    @staticmethod
    def __item_factory(category: Type[Item], name: str, **kwargs) -> Item:
        cls_name = ''.join(
            word.title()
            for word in name.split(' ')
        )
        item_cls = type(cls_name, (category, ), kwargs)
        return item_cls(**kwargs)

    def __populate_categories(
        self, catog: Type[Item],
        categories: Dict, curr_recc: int
    ):
        if curr_recc > 3:
            return
        for subcatog in catog.__subclasses__():
            if subcatog.__name__ != 'Chest':
                categories[subcatog.__name__] = subcatog
                curr_recc += 1
                self.__populate_categories(subcatog, categories, curr_recc)

    @admin_only
    @ensure_user
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
    @ensure_user
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
        won_chips = data["won_chips"]
        balance += increment
        if kwargs.get("purchased", False):
            purchased_chips += increment
        else:
            won_chips += increment
        profile.update(
            balance=balance,
            purchased_chips=purchased_chips,
            won_chips=won_chips
        )
        await message.add_reaction("👍")

    @admin_only
    @ensure_user
    @alias("usr_pr")
    async def cmd_get_user_profile(self, message, args=None, **kwargs):
        """Get Complete User Profile.
        $```scss
        {command_prefix}get_user_profile user_id
        ```$

        @`🛡️ Admin Command`
        Get the complete profile of a user, including their loot information.@

        ~To get the profile of user with ID 12345:
            ```
            {command_prefix}usr_pr 12345
            ```~
        """
        user_id = int(args[0])
        profile = await get_profile(self.database, message, user_id)
        if not profile:
            return
        data = profile.full_info
        if not data:
            return
        content = f'```json\n{json.dumps(data, indent=3, default=str)}\n```'
        await message.channel.send(content)

    @admin_only
    @ensure_user
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
        user_id = int(args[0])
        profile = await get_profile(self.database, message, user_id)
        profile.reset()
        await message.add_reaction("👍")

    @admin_only
    @ensure_user
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
    @ensure_user
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
        Inventory(self.database, user).destroy()
        await message.add_reaction("👍")

    @admin_only
    @ensure_user
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

    @admin_only
    @alias("item+")
    async def cmd_create_item(self, message, **kwargs):
        """Self-assign Gambler Role.
        $```scss
        {command_prefix}create_item
        ```$

        @`🛡️ Admin Command`
        Creates a PokeGambler world [Item] and saves it in the database.
        :information_source: Chests cannot be created using this.@
        """

        # pylint: disable=no-member

        categories = {}
        self.__populate_categories(Item, categories, curr_recc=0)
        inp_msg = await message.channel.send(
            embed=get_enum_embed(
                categories,
                title="Choose the Item Category"
            )
        )
        reply = await wait_for(
            message.channel, self.ctx, init_msg=inp_msg,
            check=lambda msg: user_check(msg, message),
            timeout="inf"
        )
        if reply.content.isdigit():
            category = list(categories.keys())[int(reply.content) - 1]
        elif reply.content.title() in categories:
            category = reply.content.title()
        else:
            await message.channel.send(
                embed=get_embed(
                    "That's not a valid category.",
                    embed_type="error",
                    title="Invalid Category"
                )
            )
            return
        details = {}
        catogclass = categories[category]
        labels = {"name": "str"}
        labels.update({
            field.name: field.type
            for field in fields(catogclass)
            if all([
                field.default is MISSING,
                field.name != 'category'
            ])
        })
        if issubclass(catogclass, Tradable):
            labels.update({"price": "int"})
        for col, dtype in labels.items():
            inp_msg = await message.channel.send(
                embed=get_embed(
                    f"Please enter a value for `{col}`:\n>_",
                    title="Input"
                )
            )
            reply = await wait_for(
                message.channel, self.ctx, init_msg=inp_msg,
                check=lambda msg: user_check(msg, message),
                timeout="inf"
            )
            if dtype == 'int':
                if not reply.content.isdigit():
                    await message.channel.send(
                        embed=get_embed(
                            f"{col.title()} must be an integer.",
                            embed_type="error",
                            title=f"Invalid {col.title()}"
                        )
                    )
                    return
                details[col] = int(reply.content)
            else:
                details[col] = reply.content
            await inp_msg.delete()
        item = self.__item_factory(
            category=catogclass, **details
        )
        item.save(self.database)
        await reply.add_reaction("👍")

    @admin_only
    @ensure_user
    @alias("usr_itm")
    async def cmd_give_item(self, message, args=None, **kwargs):
        """Adds item to User's inventory.
        $```scss
        {command_prefix}give_item itemid
        ```$

        @`🛡️ Admin Command`
        Give the user an item and add it to the inventory.@

        ~To give a user, with ID 12345, a Golden Cigar with ID 0000FFFF:
            ```
            {command_prefix}usr_itm 12345 0000FFFF
            ```~
        """
        if len(args) < 2:
            await message.channel.send(
                embed=get_embed(
                    "You need to provide a user ID and item ID.",
                    embed_type="error",
                    title="Not enough args"
                )
            )
            return
        try:
            user_id = int(args[0])
            itemid = int(args[1], 16)
        except (ValueError, ZeroDivisionError):
            await message.channel.send(
                embed=get_embed(
                    "Make sure those IDs are correct.",
                    embed_type="error",
                    title="Invalid Input"
                )
            )
            return
        user = message.guild.get_member(user_id)
        inv = Inventory(self.database, user)
        inv.save(itemid)
        await message.add_reaction("👍")

    @admin_only
    @ensure_item
    @alias("item_all")
    async def cmd_distribute_item(self, message, args=None, **kwargs):
        """Adds item to User's inventory.
        $```scss
        {command_prefix}distribute_item itemid
        ```$

        @`🛡️ Admin Command`
        Distribute an item to everyone.@

        ~To distribute a Golden Cigar with ID 0000FFFF:
            ```
            {command_prefix}item_all 0000FFFF
            ```~
        """
        itemid = int(args[0], 16)
        ids = Profile.get_all(self.database, ids_only=True)
        for uid in ids:
            user = message.guild.get_member(int(uid))
            if not user:
                continue
            Inventory(
                self.database,
                user
            ).save(itemid)
        await message.add_reaction("👍")
