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

# pylint: disable=unused-argument, too-many-lines

from __future__ import annotations
from dataclasses import MISSING, fields
import os
import json
import re
from typing import (
    Dict, Optional,
    Type, TYPE_CHECKING
)

import discord
from dotenv import load_dotenv

from ..helpers.utils import (
    dedent, get_embed,
    is_admin, is_owner
)
from ..helpers.validators import (
    HexValidator, ImageUrlValidator, IntegerValidator,
    ItemNameValidator, MinValidator
)
from ..base.modals import CallbackReplyModal
from ..base.models import Blacklist, Inventory, Profiles
from ..base.items import Item, Tradable, Treasure
from ..base.shop import Shop, PremiumShop
from ..base.views import (
    BaseView, CallbackConfirmButton,
    SelectConfirmView
)
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

    # pylint: disable=no-self-use
    @admin_only
    async def cmd_announce(
        self, message: Message,
        ping: Optional[discord.Role] = None,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param ping: The role to ping when the announcement is made.
        :type ping: Optional[:class:`discord.Role`]

        .. meta::
            :description: Send an announcement.

        .. rubric:: Syntax
        .. code:: coffee

            /announce

        .. rubric:: Description

        ``🛡️ Admin Command``
        Make PokeGambler send an announcement in the announcement channel.
        """
        async def callback(modal):
            content = modal.results[0]
            if ping:
                content = f"Hey {ping.mention}\n{content}"
            chan = message.guild.get_channel(
                int(os.getenv("ANNOUNCEMENT_CHANNEL"))
            )
            msg = await chan.send(content=content)
            await msg.publish()
            return {
                "embed": get_embed(
                    title="Sent Announcement"
                )
            }
        modal = CallbackReplyModal(
            title='Announcement',
            callback=callback
        )
        modal.add_long(
            'Enter the message.',
            placeholder="Markdown is supported."
        )
        await message.response.send_modal(modal)
        await modal.wait()

    # pylint: disable=too-many-arguments
    @admin_only
    @model(Profiles)
    @alias("chips+")
    async def cmd_add_chips(
        self, message: Message,
        user: discord.User, amount: int,
        purchased: Optional[bool] = False,
        deduct: Optional[bool] = False,
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
        :param deduct: Whether to deduct the amount from the user's balance.
        :type deduct: Optional[bool]
        :default deduct: False

        .. meta::
            :description: Add chips to a user's balance.
            :aliases: chips+

        .. rubric:: Syntax
        .. code:: coffee

            /add_chips user:@user amount:chips
            [purchased:True/False] [deduct:True/False]

        .. rubric:: Description

        ``🛡️ Admin Command``
        Adds {pokechip_emoji} to a user's account.
        Use the purchased option in case of Pokebonds.

        .. rubric:: Examples

        * To give 50 {pokechip_emoji} to user ABCD#1234

        .. code:: coffee
            :force:

            /add_chips user:@ABCD#1234 amount:50

        * To add 50 exchanged {pokebond_emoji} to user ABCD#1234

        .. code:: coffee
            :force:

            /add_chips user:ABCD#1234 amount:50 purchased:True

        * To deduct 500 {pokechip_emoji} from user ABCD#1234

        .. code:: coffee
            :force:

            /add_chips user:@ABCD#1234 amount:500 deduct:True
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
        if deduct:
            profile.debit(amount, bonds=bonds)
        else:
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

        async def oneshotview(view, interaction):
            chosen = None
            for child in view.children:
                if child.custom_id == interaction.data.get(
                    'custom_id', None
                ):
                    chosen = child
                child.disabled = True
            await interaction.message.edit(view=view)
            if chosen is None:
                await interaction.response.send_message(
                    embed=get_embed(
                        "You need to choose an option.",
                        embed_type="error",
                        title="Invalid Choice"
                    )
                )
                return
            modal = CallbackReplyModal(
                title="Update User"
            )
            field_dict = self.__upd_usr_field_dict(message)
            chosen_fields = field_dict[chosen.label]
            for field_name in chosen_fields:
                modal.add_short(
                    text=field_name,
                    required=False
                )

            async def modal_callback(modal):
                to_update = {}
                updates = []
                for child in modal.children:
                    if child.value:
                        validator = chosen_fields[child.label][1]
                        if validator is not None:
                            validator.error_embed_title = \
                                f"Invalid Value for {child.label}"
                            cleaned = await validator.cleaned(
                                child.value
                            )
                            if cleaned is None:
                                continue
                            to_update[chosen_fields[child.label][0]] = cleaned
                        else:
                            to_update[chosen_fields[child.label][0]] = child.value
                        updates.append(f"**{child.label}**")
                if chosen.label == "Currency":
                    curr_bal = profile.balance
                    if increment := int(to_update.get("won_chips", 0)) + (
                        int(to_update.get("pokebonds", 0)) * 10
                    ):
                        new_bal = curr_bal + increment
                        to_update["balance"] = new_bal
                profile.update(**to_update)
                field_str = ", ".join(updates)
                return {
                    "embed": get_embed(
                        f"Succesfully updated the fields: {field_str}.",
                    ) if field_str else get_embed(
                        "No fields were updated.",
                        embed_type="warning"
                    )
                }

            modal.add_callback(modal_callback)
            await interaction.response.send_modal(modal)
            return

        btn_view = await self.__upd_usr_send_buttons(message, oneshotview)
        await btn_view.dispatch(self)
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
            * RewardBoxes and Lootbags are yet to be implemented.
            * Owner(s) can create Premium items using the Premium option.

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

        def get_desc(cls):
            cls_patt = re.compile(r':class:`(.+)`')
            cleaned_doc = dedent(cls_patt.sub(r'\1', cls.__doc__))
            first_sentence = cleaned_doc.split('.', maxsplit=1)[0]
            return f"{first_sentence[:49]}."

        if premium and not is_owner(self.ctx, message.author):
            await message.reply(
                embed=get_embed(
                    "You need to be an owner to create a premium item.",
                    embed_type="error",
                    title="Premium Item Creation"
                )
            )
            return

        categories = {}
        self.__create_item_populate_categories(Item, categories, curr_recc=0)

        async def callback(view, interaction):
            catogclass = categories[view.value]
            labels = self.__item_get_labels(message, catogclass)
            if premium and "price" in labels:
                labels["price (pokebonds)"] = labels.pop("price")
            elif "price" in labels:
                labels["price (pokechips)"] = labels.pop("price")

            async def modal_callback(modal):
                details = await self.__item_get_details(modal, labels)
                if details is None:
                    return {
                        "embed": get_embed(
                            "All fields must be filled out correctly.",
                            embed_type="error"
                        )
                    }
                if premium:
                    details["premium"] = True
                    if "price (pokebonds)" in details:
                        details["price"] = details.pop("price (pokebonds)")
                if "price (pokechips)" in details:
                    details["price"] = details.pop("price (pokechips)")
                item = self.__create_item__item_factory(
                    category=catogclass, **details
                )
                # pylint: disable=no-member
                item.save()
                return {
                    "embed": get_embed(
                        f"Item **{item.name}** with ID `{item.itemid}` has been "
                        "created succesfully.",
                        title="Succesfully Created"
                    )
                }

            modal = CallbackReplyModal(
                title="Create Item",
                callback=modal_callback
            )
            for label in labels:
                modal.add_short(
                    text=label,
                    required=True
                )
            await interaction.response.send_modal(modal)

        choice_view = SelectConfirmView(
            placeholder="Choose the Item Category",
            options={
                catog: get_desc(cls)
                for catog, cls in sorted(categories.items())
            },
            check=lambda x: x.user.id == message.author.id,
            callback=callback
        )
        await message.reply(
            content="What Item would you like to create?",
            view=choice_view
        )
        await choice_view.dispatch(self)

    @admin_only
    @os_only
    @ensure_item
    @model([Item, Tradable])
    @alias("upd_itm")
    async def cmd_update_item(
        self, message: Message,
        itemid: str,
        modify_all: Optional[bool] = False,
        **kwargs
    ):
        """
        :param message: The message which triggered the command.
        :type message: :class:`discord.Message`
        :param itemid: The ID of the item to update.
        :type itemid: str
        :param modify_all: Whether or not to modify all copies of the item.
        :type modify_all: Optional[bool]
        :default modify_all: False

        .. meta::
            :description: Updates an existing Item in the database.
            :aliases: upd_itm

        .. rubric:: Syntax
        .. code:: coffee

            /update_item itemid:Id [modify_all:True/False]

        .. rubric:: Description

        ``🛡️ Admin Command``
        Updates an existing Item/all copies of the Item in the database.

        .. tip::

            Check :class:`~scripts.base.items.Item` for available parameters.

        .. note::

            Category & Premium status change is not yet supported.

        .. rubric:: Examples

        * To update a Golden Cigar with ID 0000FFFF

        .. code:: coffee
            :force:

            /update_item itemid:0000FFFF

        * To update all copies of the item with ID 0000FFFF

        .. code:: coffee
            :force:

            /update_item itemid:0000FFFF modify_all:True
        """
        item: Item = kwargs.get("item")
        if not item:
            return
        labels = self.__item_get_labels(message, item.category_class)

        async def modal_callback(modal):
            details = await self.__item_get_details(modal, labels)
            if details is None:
                return {
                    "embed": get_embed(
                        "All fields must be filled out correctly.",
                        embed_type="error"
                    )
                }
            item.update(
                **details,
                modify_all=modify_all
            )
            if issubclass(item.__class__, Tradable):
                Shop.refresh_tradables()
                PremiumShop.refresh_tradables()
            return {
                "embed": get_embed(
                    f"Item **{item.name}** with ID `{item.itemid}` has been "
                    "updated succesfully.",
                    title="Succesfully Updated"
                )
            }

        modal = CallbackReplyModal(
            title="Update Item",
            callback=modal_callback
        )
        for label in labels:
            placeholder = str(getattr(item, label, 'Enter a value...'))
            if len(placeholder) > 100:
                placeholder = 'Enter a value...'
            modal.add_short(
                text=label,
                required=False,
                placeholder=placeholder
            )
        await message.response.send_modal(modal)

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
                subcatog.__name__ != 'Treasure',
                not issubclass(subcatog, Treasure),
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

    @staticmethod
    def __item_get_labels(message, catogclass):
        labels = {
            "name": {
                "validator": ItemNameValidator(
                    message=message
                )
            }
        }
        labels.update({
            field.name: {
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
                "validator": MinValidator(
                    message=message,
                    min_value=1
                )
            }
        for key, value in labels.items():
            if value['validator']:
                value['validator'].error_embed_title = \
                    f"Invalid Input for {key.title()}."
        return labels

    @staticmethod
    async def __item_get_details(modal, labels):
        details = {}
        for child in modal.children:
            validator = labels[child.label]['validator']
            if validator and child.value:
                value = await validator.cleaned(child.value)
                if not value:
                    return None
                details[child.label] = value
            elif child.value:
                details[child.label] = child.value
        return details

    def __upd_usr_field_dict(self, message):
        field_dict = {
            "Currency": {
                "Pokechips": (
                    "won_chips",
                    IntegerValidator(
                        message=message,
                    )
                )
            },
            "Other": {
                "Name": ("name", None),
                "Matches Won": (
                    "num_wins",
                    IntegerValidator(
                        message=message
                    )
                ),
                "Matches Played": (
                    "num_matches",
                    IntegerValidator(
                        message=message
                    )
                ),
                "Background": (
                    "background",
                    ImageUrlValidator(
                        message=message
                    )
                ),
                "Embed Color": (
                    "embed_color",
                    HexValidator(
                        message=message
                    )
                )
            }
        }
        if is_owner(self.ctx, message.author):
            field_dict["Currency"]["Pokebonds"] = (
                "pokebonds",
                IntegerValidator(
                    message=message
                )
            )
        return field_dict

    async def __upd_usr_send_buttons(self, message, callback):
        btn_view = BaseView(
            check=lambda intcrn: intcrn.user.id == message.author.id
        )
        btn_view.add_item(
            CallbackConfirmButton(
                label='Currency',
                style=discord.ButtonStyle.primary,
                callback=callback
            )
        )
        btn_view.add_item(
            CallbackConfirmButton(
                label="Other",
                style=discord.ButtonStyle.secondary,
                callback=callback
            )
        )
        await message.reply(
            embed=get_embed(
                "Which field would you like to update?",
                title="Update User"
            ),
            view=btn_view
        )
        return btn_view
