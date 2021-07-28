"""
Administration Commands
"""

# pylint: disable=unused-argument

from __future__ import annotations
from dataclasses import MISSING, fields
import os
import json
from typing import (
    Dict, List, Optional,
    Type, TYPE_CHECKING
)

from dotenv import load_dotenv

from ..helpers.checks import user_check
from ..helpers.utils import (
    get_embed, get_enum_embed,
    is_admin, is_owner, wait_for
)
from ..base.models import Blacklist, Inventory, Profiles
from ..base.items import Item, Rewardbox, Tradable
from ..base.shop import Shop, PremiumShop
from .basecommand import (
    Commands, admin_only, alias,
    ensure_user, get_profile, ensure_item,
    no_thumb
)

if TYPE_CHECKING:
    from discord import Message

load_dotenv()


class AdminCommands(Commands):
    """
    Commands that deal with the moderation tasks.
    Only Admins and Owners will have access to these.
    """

    @admin_only
    @ensure_user
    @alias("chips+")
    async def cmd_add_chips(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """Adds chips to user's balance.
        $```scss
        {command_prefix}add_chips user_id amount [--purchased]
        ```$

        @`🛡️ Admin Command`
        Adds {pokechip_emoji} to a user's account.
        Use the `--purchased` kwarg if the chips were bought.@

        ~To give 50 {pokechip_emoji} to user with ID 12345:
            ```
            {command_prefix}add_chips 12345 50
            ```
        To add 500 exchanged {pokechip_emoji} to user 67890:
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
        profile = await get_profile(message, user_id)
        if not profile:
            return
        bonds = kwargs.get(
            "purchased", False
        ) and is_owner(self.ctx, message.author)
        profile.credit(increment, bonds=bonds)
        await message.add_reaction("👍")

    @admin_only
    @ensure_user
    @alias("usr_pr")
    async def cmd_get_user_profile(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
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
        profile = await get_profile(message, user_id)
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
    async def cmd_reset_user(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
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
        profile = await get_profile(message, user_id)
        profile.reset()
        await message.add_reaction("👍")

    @admin_only
    @ensure_user
    @alias("upd_usr")
    async def cmd_update_user(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
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
        profile = await get_profile(message, user_id)
        if not profile:
            return
        try:
            profile.update(**kwargs)
        except Exception as excp:  # pylint: disable=broad-except
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
    async def cmd_blacklist_user(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
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
        await Blacklist(
            user,
            str(message.author.id),
            reason=kwargs.get("reason")
        ).save()
        await message.add_reaction("👍")

    @admin_only
    @ensure_user
    @alias("pardon")
    async def cmd_pardon_user(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
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
        if not Blacklist.is_blacklisted(args[0]):
            await message.channel.send(
                embed=get_embed(
                    "User is not blacklisted.",
                    embed_type="error",
                    title="Invalid User"
                )
            )
            return
        Blacklist(
            user,
            str(message.author.id)
        ).pardon()
        await message.add_reaction("👍")

    @admin_only
    async def cmd_announce(self, message: Message, **kwargs):
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
        msg = await chan.send(content=content)
        await msg.publish()
        await reply.add_reaction("👍")

    @no_thumb
    @admin_only
    @alias("item+")
    async def cmd_create_item(self, message: Message, **kwargs):
        """Self-assign Gambler Role.
        $```scss
        {command_prefix}create_item [--premium]
        ```$

        @`🛡️ Admin Command`
        Creates a PokeGambler world [Item] and saves it in the database.
        :information_source: Chests cannot be created using this.
        **Owner(s) can create Premium items using the --premium kwarg.**
        *In case of Reward Boxes, the items should be a comma-separated*
        *list of IDs.*@
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
            labels.update({"price": int})
        if catogclass is Rewardbox:
            labels.update({
                "chips": int,
                "items": str
            })
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
            if dtype == int:
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
            elif col == "items":
                details[col] = [
                    itemid.strip()
                    for itemid in reply.content.split(',')
                ]
            else:
                details[col] = reply.content
            await inp_msg.delete()
        if kwargs.get("premium", False) and is_owner(self.ctx, message.author):
            details["premium"] = True
        item = self.__item_factory(
            category=catogclass, **details
        )
        item.save()
        await message.channel.send(
            embed=get_embed(
                f"Item **{item.name}** with ID _{item.itemid}_ has been "
                "created succesfully.",
                title="Succesfully Created"
            )
        )
        await reply.add_reaction("👍")

    @admin_only
    @ensure_item
    @alias("item-")
    async def cmd_delete_item(
        self, message: Message,
        args: List[str] = None,
        **kwargs
    ):
        """Deletes an Item from the database.
        $```scss
        {command_prefix}delete_item itemid
        ```$

        @`🛡️ Admin Command`
        Delete an item from the database.
        If the item was in anyone's inventory, it will be gone.@

        ~To delete a Golden Cigar with ID 0000FFFF:
            ```
            {command_prefix}item- 0000FFFF
            ```~
        """
        item = kwargs.get("item")
        if item.premium and not is_owner(self.ctx, message.author):
            await message.channel.send(
                embed=get_embed(
                    "Only owners can delete a premium item.",
                    embed_type="error",
                    title="Forbidden"
                )
            )
            return
        item.delete()
        await message.add_reaction("👍")

    @admin_only
    @ensure_item
    @alias("upd_itm")
    async def cmd_update_item(
        self, message: Message,
        args: List[str] = None,
        **kwargs
    ):
        """Updates an existing Item from the database.
        $```scss
        {command_prefix}update_item itemid
        ```$

        @`🛡️ Admin Command`
        Update any attribute of an existing item from the database.@

        ~To make a Golden Cigar with ID 0000FFFF premium:
            ```
            {command_prefix}update_item 0000FFFF --premium True
            ```~
        """
        item = kwargs.get("item")
        updatables = {
            key.lower(): val
            for key, val in kwargs.items()
            if key.lower() in dict(item)
        }
        if not updatables:
            await message.channel.send(
                embed=get_embed(
                    "That's not a valid attribute.",
                    embed_type="warning",
                    title="Unable to Update."
                )
            )
            return
        if not is_owner(self.ctx, message.author):
            updatables.pop("premium", None)
        if not updatables:
            return
        item.update(**updatables, modify_all=True)
        if issubclass(item.__class__, Tradable):
            Shop.refresh_tradables()
            PremiumShop.refresh_tradables()
        await message.add_reaction("👍")

    @admin_only
    @ensure_user
    @alias("usr_itm")
    async def cmd_give_item(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """Adds item to User's inventory.
        $```scss
        {command_prefix}give_item user_id itemid
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
        # pylint: disable=no-member
        try:
            item = Item.get(args[1])
            if not item:
                raise ValueError
            if (
                item["premium"]
                and not is_owner(self.ctx, message.author)
            ):
                await message.channel.send(
                    embed=get_embed(
                        "Only the owners can give Premium Items.",
                        embed_type="error",
                        title="Forbidden"
                    )
                )
                return
            new_item = Item.from_id(
                args[1],
                force_new=True
            )
            itemid = new_item.itemid
        except (ValueError, ZeroDivisionError):
            await message.channel.send(
                embed=get_embed(
                    "Make sure those IDs are correct.",
                    embed_type="error",
                    title="Invalid Input"
                )
            )
            return
        user_id = int(args[0])
        user = message.guild.get_member(user_id)
        inv = Inventory(user)
        inv.save(itemid)
        await message.add_reaction("👍")

    @admin_only
    @ensure_item
    @alias("item_all")
    async def cmd_distribute_item(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
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
        item = kwargs["item"]
        if item.premium and not is_owner(self.ctx, message.author):
            await message.channel.send(
                embed=get_embed(
                    "Only the owners can give Premium Items.",
                    embed_type="error",
                    title="Forbidden"
                )
            )
            return
        ids = Profiles.get_all(ids_only=True)
        for uid in ids:
            if not uid:
                continue
            user = message.guild.get_member(int(uid))
            if not user:
                continue
            Inventory(user).save(args[0])
        await message.add_reaction("👍")

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
        if getattr(catog, '__module__', None) != "scripts.base.items":
            return
        for subcatog in catog.__subclasses__():
            if subcatog.__name__ != 'Chest':
                categories[subcatog.__name__] = subcatog
                curr_recc += 1
                self.__populate_categories(subcatog, categories, curr_recc)
