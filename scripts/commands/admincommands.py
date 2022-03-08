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

Administration Commands
"""

# pylint: disable=unused-argument

from __future__ import annotations
from dataclasses import MISSING, fields
import os
import json
from typing import (
    Dict, Optional,
    Type, TYPE_CHECKING
)

import discord
from dotenv import load_dotenv

from ..helpers.checks import user_check
from ..helpers.utils import (
    dedent, get_embed, is_admin,
    is_owner, wait_for
)
from ..helpers.validators import (
    ImageUrlValidator, ItemNameValidator, MinValidator
)
from ..base.models import Blacklist, Inventory, Profiles
from ..base.items import Item, Rewardbox, Tradable
from ..base.shop import Shop, PremiumShop
from ..base.views import SelectView
from .basecommand import (
    Commands, admin_only, alias,
    check_completion, ensure_item,
    get_profile, model, os_only
)

if TYPE_CHECKING:
    from discord import Message

load_dotenv()


class AdminCommands(Commands):
    """
    Commands that deal with the moderation tasks.

    .. note::

        Only Admins and Owners will have access to these.
    """

    @admin_only
    async def cmd_announce(self, message: Message, **kwargs):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`

        .. meta::
            :description: Send an announcement.

        .. rubric:: Syntax
        .. code:: coffee

            /announce

        .. rubric:: Description

        ``🛡️ Admin Command``
        Make PokeGambler send an announcement in the announcement channel.
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

    @admin_only
    @model(Profiles)
    @alias("chips+")
    async def cmd_add_chips(
        self, message: Message,
        user: discord.User, amount: int,
        purchased: Optional[bool] = False,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param user: The user whom the chips are being added to.
        :type user: :class:`discord.User`
        :param amount: The amount of chips to add.
        :type amount: int
        :min_value amount: 10
        :param purchased: Whether Pokebonds were purchased instead of chips.
        :type purchased: Optional[bool]
        :default purchased: False

        .. meta::
            :description: Add chips to a user's balance.
            :aliases: chips+

        .. rubric:: Syntax
        .. code:: coffee

            /add_chips user:@user amount:chips [purchased:True/False]

        .. rubric:: Description

        ``🛡️ Admin Command``
        Adds {pokechip_emoji} to a user's account.
        Use the purchased option in case of Pokebonds.

        .. rubric:: Examples

        * To give 50 {pokechip_emoji} to user ABCD#1234

        .. code:: coffee
            :force:

            /add_chips user:@ABCD#1234 amount:50

        * To add 500 exchanged {pokechip_emoji} to user 67890

        .. code:: coffee
            :force:

            /add_chips user:@67890 amount:500 purchased:True
        """
        profile = await get_profile(self.ctx, message, user)
        if not profile:
            return
        valid = await MinValidator(
            min_value=10, message=message,
            on_null={
                "title": "Invalid Amount",
                "description": "Specify how many chips to add."
            }
        ).validate(amount)
        if not valid:
            return
        bonds = purchased and is_owner(self.ctx, message.author)
        profile.credit(amount, bonds=bonds)
        await message.add_reaction("👍")

    @admin_only
    @os_only
    @model([Blacklist, Profiles])
    @alias("bl")
    async def cmd_blacklist_user(
        self, message: Message,
        user: discord.Member,
        reason: Optional[str] = None,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param user: The user to blacklist.
        :type user: :class:`discord.Member`
        :param reason: The reason for blacklisting the user.
        :type reason: Optional[str]

        .. meta::
            :description: Blacklist a user from using PokeGambler.
            :aliases: bl

        .. rubric:: Syntax
        .. code:: coffee

            /blacklist_user user:@user [reason:reason]

        .. rubric:: Description

        ``🛡️ Admin Command``
        Blacklists a user from using PokeGambler until pardoned.
        Use the Reason option to provide a reason for the blacklist.

        .. rubric:: Examples

        * To blacklist user ABCD#1234 from using PokeGambler

        .. code:: coffee
            :force:

            /blacklist_user user:@ABCD#1234

        * To blacklist user ABCD#1234 from using PokeGambler for spamming

        .. code:: coffee
            :force:

            /blacklist_user user:@ABCD#1234 reason:Spamming
        """
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
            user, message.author,
            reason=reason
        ).save()
        await message.add_reaction("👍")

    @admin_only
    @model(Profiles)
    @alias("usr_pr")
    async def cmd_user_profile(  # pylint: disable=no-self-use
        self, message: Message,
        user: discord.User,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param user: The user whose profile is being requested.
        :type user: :class:`discord.User`

        .. meta::
            :description: Get the complete profile of a user.
            :aliases: usr_pr

        .. rubric:: Syntax
        .. code:: coffee

            /user_profile user:@user

        .. rubric:: Description

        ``🛡️ Admin Command``
        Get the complete profile of a user, including their
        loot information.

        .. rubric:: Examples

        * To get the complete profile of user ABCD#1234

        .. code:: coffee
            :force:

            /user_profile user:@ABCD#1234
        """
        profile = await get_profile(self.ctx, message, user)
        if not profile:
            return
        data = profile.full_info
        if not data:
            return
        content = f'```json\n{json.dumps(data, indent=3, default=str)}\n```'
        await message.channel.send(content)

    @admin_only
    @os_only
    @model([Blacklist, Profiles])
    @alias("pardon")
    async def cmd_pardon_user(
        self, message: Message,
        user: discord.Member,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param user: The user to pardon.
        :type user: :class:`discord.Member`

        .. meta::
            :description: Pardons a blacklisted user.
            :aliases: pardon

        .. rubric:: Syntax
        .. code:: coffee

            /pardon_user user:@user

        .. rubric:: Description

        ``🛡️ Admin Command``
        Pardons a blacklisted user so that they can use
        PokeGambler again.

        .. rubric:: Examples

        * To pardon user ABCD#1234

        .. code:: coffee
            :force:

            /pardon user:@ABCD#1234
        """
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
        if not Blacklist.is_blacklisted(str(user.id)):
            await message.channel.send(
                embed=get_embed(
                    "User is not blacklisted.",
                    embed_type="error",
                    title="Invalid User"
                )
            )
            return
        Blacklist(user, message.author).pardon()
        await message.add_reaction("👍")

    @admin_only
    @os_only
    @model(Profiles)
    @alias("rst_usr")
    async def cmd_reset_user(  # pylint: disable=no-self-use
        self, message: Message,
        user: discord.User,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param user: The user whose profile is being reset.
        :type user: :class:`discord.User`

        .. meta::
            :description: Completely resets a user's profile.
            :aliases: rst_usr

        .. rubric:: Syntax
        .. code:: coffee

            /reset_user user:@user

        .. rubric:: Description

        ``🛡️ Admin Command``
        Completely resets a user's profile to the starting stage.

        .. rubric:: Examples

        * To reset user ABCD#1234

        .. code:: coffee
            :force:

            /reset_user user:@ABCD#1234
        """
        profile = await get_profile(self.ctx, message, user)
        if not profile:
            return
        profile.reset()
        await message.add_reaction("👍")

    @admin_only
    @os_only
    @model(Profiles)
    @check_completion
    @alias("upd_usr")
    async def cmd_update_user(
        self, message: Message,
        user: discord.User,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param user: The user whose profile is being updated.
        :type user: :class:`discord.User`

        .. meta::
            :description: Updates a user's profile.
            :aliases: upd_usr

        .. rubric:: Syntax
        .. code:: coffee

            /update_user user:@user

        .. rubric:: Description

        ``🛡️ Admin Command``
        Updates a user's profile.

        .. rubric:: Examples

        * To update user ABCD#1234

        .. code:: coffee
            :force:

            /update_user user:@ABCD#1234
        """
        profile = await get_profile(self.ctx, message, user)
        if not profile:
            return
        try:
            choice_view = SelectView(
                heading="Choose the Field",
                options={
                    field: ""
                    for field in profile.get()
                    if field != "pokebonds" or is_owner(
                        self.ctx, message.author
                    )
                },
                no_response=True,
                check=lambda x: x.user.id == message.author.id
            )
            await message.channel.send(
                content="Which field would you like to edit?",
                view=choice_view
            )
            await choice_view.dispatch(self)
            if choice_view.result is None:
                return
            field = choice_view.result
            await message.channel.send(
                content=f"What would you like to set {field} to?",
                embed=get_embed(
                    "Enter a value",
                    title=field,
                    color=profile.get('embed_color')
                )
            )
            reply = await self.ctx.wait_for(
                "message",
                check=lambda msg: user_check(msg, message),
                timeout=None
            )
            profile.update(**{field: reply.content})
            await message.add_reaction("👍")
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

    @check_completion
    @admin_only
    @os_only
    @model(Item)
    @alias("item+")
    async def cmd_create_item(
        self, message: Message,
        premium: Optional[bool] = False,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param premium: Whether or not the item is premium.
        :type premium: Optional[bool]
        :default premium: False

        .. meta::
            :description: Creates a PokeGambler world [Item] \
                and saves it in the database.
            :aliases: item+

        .. rubric:: Syntax
        .. code:: coffee

            /create_item [premium:True/False]

        .. rubric:: Description

        ``🛡️ Admin Command``
        Creates a PokeGambler world Item and saves it in the database.

        .. seealso::
            :class:`~scripts.base.items.Item`

        .. note::

            * Chests cannot be created using this.
            * Owner(s) can create Premium items using the --premium kwarg.
            * In case of Reward Boxes, the items should be a comma-separated \
                list of IDs.

        .. rubric:: Examples

        * To create a non premium item

        .. code:: coffee
            :force:

            /create_item

        * To create a premium item

        .. code:: coffee
            :force:

            /create_item premium:True
        """
        # pylint: disable=no-member

        categories = {}
        self.__create_item_populate_categories(Item, categories, curr_recc=0)
        choice_view = SelectView(
            heading="Choose the Item Category",
            options={
                catog: dedent(
                    cls.__doc__
                ).split(
                    '.', maxsplit=1
                )[0][:49] + '.'
                for catog, cls in sorted(categories.items())
            },
            no_response=True,
            check=lambda x: x.user.id == message.author.id
        )
        await message.channel.send(
            content="What Item would you like to create?",
            view=choice_view
        )
        await choice_view.dispatch(self)
        if choice_view.result is None:
            return
        catogclass = categories[choice_view.result]
        details = {}
        labels = {
            "name": {
                "dtype": str,
                "validator": ItemNameValidator(
                    message=message
                )
            }
        }
        labels.update({
            field.name: {
                "dtype": field.type,
                "validator": None
            }
            for field in fields(catogclass)
            if all([
                field.default is MISSING,
                field.name != 'category'
            ])
        })
        labels['asset_url']['validator'] = ImageUrlValidator(message=message)
        if issubclass(catogclass, Tradable):
            labels["price"] = {
                "dtype": int,
                "validator": MinValidator(
                    message=message,
                    min_value=1
                )
            }
        if catogclass is Rewardbox:
            labels.update({
                "chips": {
                    "dtype": int,
                    "validator": MinValidator(
                        message=message,
                        min_value=1
                    )
                },
                "items": {
                    "dtype": str,
                    "validator": None
                }
            })
        for col, params in labels.items():
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
            if params["validator"] is not None:
                # pylint: disable=not-callable
                proceed = await params["validator"].validate(reply.content)
                if not proceed:
                    return
            if params["dtype"] == int:
                details[col] = int(reply.content)
            elif col == "items":
                details[col] = [
                    itemid.strip()
                    for itemid in reply.content.split(',')
                ]
            else:
                details[col] = reply.content
            await inp_msg.delete()
        if premium and is_owner(self.ctx, message.author):
            details["premium"] = True
        item = self.__create_item__item_factory(
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
    @os_only
    @ensure_item
    @model(Item)
    @alias("item-")
    async def cmd_delete_item(
        self, message: Message,
        itemid: str, **kwargs
    ):
        """
        :param message: The message which triggered the command.
        :type message: :class:`discord.Message`
        :param itemid: The item ID to delete.
        :type itemid: str

        .. meta::
            :description: Deletes an Item from the database.
            :aliases: item-

        .. rubric:: Syntax
        .. code:: coffee

            /delete_item itemid:Id

        .. rubric:: Description

        ``🛡️ Admin Command``
        Delete an item from the database.
        If the item was in anyone\'s inventory, it will be gone.

        .. rubric:: Examples

        * To delete a Golden Cigar with ID 0000FFFF

        .. code:: coffee
            :force:

            /delete_item itemid:0000FFFF
        """
        item: Item = kwargs.get("item")
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
    @os_only
    @ensure_item
    @model([Inventory, Item, Profiles])
    @alias("item_all")
    async def cmd_distribute_item(
        self, message: Message,
        itemid: str, **kwargs
    ):
        """
        :param message: The message which triggered the command.
        :type message: :class:`discord.Message`
        :param itemid: The item ID to distribute.
        :type itemid: str

        .. meta::
            :description: Distributes an item to everyone.
            :aliases: item_all

        .. rubric:: Syntax
        .. code:: coffee

            /distribute_item itemid:Id

        .. rubric:: Description

        ``🛡️ Admin Command``
        Distributes an item to everyone who is not blacklisted.

        .. rubric:: Examples

        * To distribute a Golden Cigar with ID 0000FFFF

        .. code:: coffee
            :force:

            /distribute_item itemid:0000FFFF
        """
        item: Item = kwargs["item"]
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
        official_guild = self.ctx.get_guild(
            int(self.ctx.official_server)
        )
        count = 0
        for uid in ids:
            if not uid:
                continue
            user = official_guild.get_member(int(uid))
            if not user:
                continue
            Inventory(user).save(item.itemid)
            count += 1
        await message.reply(
            embed=get_embed(
                f"{count} users have been given the item **{item.name}**.",
                title="Succesfully Distributed"
            )
        )

    @admin_only
    @os_only
    @model([Inventory, Item])
    @alias("usr_itm")
    async def cmd_give_item(
        self, message: Message,
        user: discord.User,
        itemid: str, **kwargs
    ):
        """
        :param message: The message which triggered the command.
        :type message: :class:`discord.Message`
        :param user: The user to give the item to.
        :type user: :class:`discord.User`
        :param itemid: The ID of the item to give.
        :type itemid: str

        .. meta::
            :description: Gives an item to a user.
            :aliases: usr_itm

        .. rubric:: Syntax
        .. code:: coffee

            /give_item user:@User itemid:Id

        .. rubric:: Description

        ``🛡️ Admin Command``
        Gives an item to a user.

        .. note::

            Creates a new copy of existing item before
            giving it to the user.

        .. rubric:: Examples

        * To give a Golden Cigar with ID 0000FFFF to ABCD#1234

        .. code:: coffee
            :force:

            /give_item user:ABCD#1234 itemid:0000FFFF
        """
        if not Item.get(itemid):
            await message.channel.send(
                embed=get_embed(
                    "Make sure those IDs are correct.",
                    embed_type="error",
                    title="Invalid Input"
                )
            )
            return
        item = Item.from_id(itemid, force_new=True)
        # pylint: disable=no-member
        if (
            item.premium
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
        inv = Inventory(user)
        inv.save(item.itemid)
        await message.add_reaction("👍")

    @admin_only
    @os_only
    @ensure_item
    @model([Item, Tradable])
    @alias("upd_itm")
    async def cmd_update_item(
        self, message: Message,
        itemid: str, **kwargs
    ):
        """
        :param message: The message which triggered the command.
        :type message: :class:`discord.Message`
        :param itemid: The ID of the item to update.
        :type itemid: str

        .. meta::
            :description: Updates an existing Item in the database.
            :aliases: upd_itm

        .. rubric:: Syntax
        .. code:: coffee

            /update_item itemid:Id

        .. rubric:: Description

        ``🛡️ Admin Command``
        Updates an existing Item from the database.

        .. tip::

            Check :class:`~scripts.base.items.Item` for available parameters.

        .. rubric:: Examples

        * To update a Golden Cigar with ID 0000FFFF

        .. code:: coffee
            :force:

            /update_item itemid:0000FFFF
        """
        item = kwargs.get("item")
        if not item:
            return
        options = {
            key.lower(): ""
            for key in dict(item)
        }
        if not is_owner(self.ctx, message.author):
            options.pop("premium")
        choices_view = SelectView(
            no_response=True,
            heading="Choose an attribute",
            options=options,
            check=lambda x: x.user.id == message.author.id
        )
        await message.channel.send(
            content="Which attribute do you want to edit?",
            view=choices_view
        )
        await choices_view.dispatch(self)
        if not choices_view.result:
            return
        attribute = choices_view.result
        await message.channel.send(
            embed=get_embed(
                content=f"What do you want to change {attribute} to?",
                title="Update Item",
                color=Profiles(message.author).get("embed_color")
            )
        )
        reply = await self.ctx.wait_for(
            "message",
            check=lambda msg: user_check(msg, message)
        )
        item.update(
            **{attribute: reply.content},
            modify_all=True
        )
        if issubclass(item.__class__, Tradable):
            Shop.refresh_tradables()
            PremiumShop.refresh_tradables()
        await message.add_reaction("👍")

    @staticmethod
    def __create_item__item_factory(
        category: Type[Item],
        name: str, **kwargs
    ) -> Item:
        cls_name = ''.join(
            word.title()
            for word in name.split(' ')
        )
        item_cls = type(cls_name, (category, ), kwargs)
        return item_cls(**kwargs)

    def __create_item_populate_categories(
        self, catog: Type[Item],
        categories: Dict, curr_recc: int
    ):
        for subcatog in catog.__subclasses__():
            if all([
                subcatog.__name__ != 'Chest',
                getattr(
                    subcatog,
                    '__module__',
                    None
                ) == "scripts.base.items"
            ]):
                categories[subcatog.__name__] = subcatog
                curr_recc += 1
                self.__create_item_populate_categories(
                    subcatog, categories, curr_recc
                )
