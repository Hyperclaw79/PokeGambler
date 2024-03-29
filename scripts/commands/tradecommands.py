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

Trade Commands Module
"""

# pylint: disable=too-many-locals, too-many-lines
# pylint: disable=unused-argument

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from typing import (
    List, Optional, TYPE_CHECKING, Tuple,
    Type, Union, Dict
)

import discord
from bson import ObjectId

from ..base.enums import CurrencyExchange
from ..base.handlers import CustomInteraction
from ..base.items import Chest, Item, LegendaryChest, Lootbag, Rewardbox
from ..base.modals import CallbackReplyModal
from ..base.models import (
    Blacklist, Exchanges, Inventory, Loots,
    Profiles, Trades, Transactions
)
from ..base.shop import (
    BoostItem, PremiumBoostItem,
    PremiumShop, Shop, Title
)
from ..base.views import (
    CallbackButton, CallbackButtonView, ConfirmView,
    ConfirmOrCancelView, LinkView, SelectConfirmView
)

from ..helpers.utils import (
    EmbedFieldsConfig, dedent, dm_send,
    get_embed, get_formatted_time, get_modules,
    is_admin, is_owner
)
from ..helpers.validators import (
    ChainValidator, HexValidator,
    MaxLengthValidator, MinLengthValidator,
    MaxValidator, MinValidator
)

from .basecommand import (
    Commands, alias, check_completion,
    dealer_only, defer, ensure_item, model,
    os_only, suggest_actions
)

if TYPE_CHECKING:
    from discord import Embed, Member, Message


class TradeCommands(Commands):
    """
    Commands that deal with the trade system of PokeGambler.
    Shop related commands fall under this category as well.
    """

    verbose_names: Dict[str, str] = {
        'Rewardbox': 'Reward Boxe',
        'Giftbox': 'Gift Boxe'
    }

    redeem_lock: Dict[Tuple[str, int], str] = {}

    @defer
    @model([Profiles, Loots, Inventory])
    async def cmd_buy(
        self, message: Message,
        itemid: str,
        quantity: Optional[int] = 1,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param itemid: The ID of the item to buy.
        :type itemid: str
        :param quantity: The quantity of the item to buy.
        :type quantity: Optional[int]
        :min_value quantity: 1
        :default quantity: 1

        .. meta::
            :description: Buy an item from the Shop.

        .. rubric:: Syntax
        .. code:: coffee

            /buy itemid:Id [quantity:number]

        .. rubric:: Description

        Buys an item from the Shop.
        You can provide a quantity to buy multiple items.
        To see the list of purchasable items, check the
        :class:`~scripts.base.shop.Shop`.

        .. rubric:: Examples

        * To buy a Loot boost with ID boost_lt

        .. code:: coffee
            :force:

            /buy itemid:boost_lt

        * To buy 10 items with ID 0000FFFF

        .. code:: coffee
            :force:

            /buy itemid:0000FFFF quantity:10
        """
        shop, item = await self.__buy_get_item(message, itemid.lower())
        if item is None:
            return
        status = shop.validate(message.author, item, quantity)
        if status != "proceed":
            await message.reply(
                embed=get_embed(
                    status,
                    embed_type="error",
                    title="Unable to Purchase item."
                )
            )
            return
        success = await self.__buy_perform(message, quantity, item)
        if not success:
            return
        spent = item.price * quantity
        if item.__class__ in [BoostItem, PremiumBoostItem]:
            tier = Loots(message.author).tier
            spent *= (10 ** (tier - 1))
        curr = self.chip_emoji
        if item.premium:
            spent //= 10
            curr = self.bond_emoji
        ftr_txt = None
        if isinstance(item, Title):
            ftr_txt = "Your nickname might've not changed " + \
                "if it's too long.\nBut the role has been " + \
                "assigned succesfully."
        quant_str = f"x {quantity}" if quantity > 1 else ''
        await message.reply(
            embed=get_embed(
                f"Successfully purchased **{item}**{quant_str}.\n"
                "Your account has been debited: "
                f"**{spent}** {curr}",
                title="Success",
                footer=ftr_txt,
                color=Profiles(message.author).get('embed_color')
            )
        )

    @os_only
    @check_completion
    @model(Profiles)
    @alias("cashin")
    async def cmd_deposit(
        self, message: Message,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`

        .. meta::
            :description: Deposit other pokebot credits.
            :aliases: deposit

        .. rubric:: Syntax
        .. code:: coffee

            /deposit

        .. rubric:: Description

        Deposit other currencies to exchange them for Pokechips.
        """
        pokebot, quantity = await self.__get_inputs(message)
        if pokebot is None:
            return
        req_msg, admin = await self.__admin_accept(
            message, pokebot, quantity
        )
        if admin is None:
            return
        chips = CurrencyExchange[pokebot.name].value * quantity
        thread = await self.__get_thread(message, pokebot, req_msg)
        await self.__handle_transaction(
            message, thread,
            admin, pokebot, chips
        )

    @model(Item)
    @ensure_item
    @alias(['item', 'detail'])
    async def cmd_details(  # pylint: disable=no-self-use
        self, message: Message,
        itemid: str, **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param itemid: The ID of the item to get details for.
        :type itemid: str

        .. meta::
            :description: Check the details of an Item.
            :aliases: item, detail

        .. rubric:: Syntax
        .. code:: coffee

            /details itemid:Id

        .. rubric:: Description

        Check the details of a PokeGambler item, like

        * Description

        * Price

        * Category

        .. rubric:: Examples

        * To check the details of an Item with ID 0000FFFF

        .. code:: coffee
            :force:

            /details itemid:0000FFFF
        """
        item = kwargs["item"]
        await message.reply(embed=item.details)

    @alias("rates")
    async def cmd_exchange_rates(  # pylint: disable=no-self-use
        self, message: Message,
        pokebot: Optional[str] = None,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param pokebot: The name of the Pokebot to get the rates for.
        :type pokebot: Optional[str]

        .. meta::
            :description: Check the exchange rates of pokebot credits.
            :aliases: rates

        .. rubric:: Syntax
        .. code:: coffee

            /exchange_rates [pokebot:Name]

        .. rubric:: Description

        Check the exchange rates for different pokebot credits.

        .. rubric:: Examples

        * To check the exchange rates for all the bots

        .. code:: coffee
            :force:

            /exchange_rates

        * To check the exchange rates for PokeTwo

        .. code:: coffee
            :force:

            /rates pokebot:pokétwo
        """
        enums = CurrencyExchange
        if pokebot:
            res = enums[pokebot]
            if res is not enums.DEFAULT:
                enums = [res]
        rates_str = '\n'.join(
            f"```fix\n1 {bot.name} Credit = {bot.value} Pokechips\n```"
            for bot in enums
            if bot is not CurrencyExchange.DEFAULT
        )
        await message.reply(
            embed=get_embed(
                rates_str,
                title="Exchange Rates"
            )
        )

    @dealer_only
    @model([Profiles, Trades])
    @alias(["transfer", "pay"])
    async def cmd_give(
        self, message: Message,
        chips: int,
        user: discord.Member,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param chips: The amount of chips to transfer.
        :type chips: int
        :min_value chips: 10
        :param user: The user to transfer the chips to.
        :type user: :class:`discord.Member`

        .. meta::
            :description: Transfer credits to other users.
            :aliases: transfer, pay

        .. rubric:: Syntax
        .. code:: coffee

            /give chips:Amount user:@User

        .. rubric:: Description

        Transfer some of your own {pokechip_emoji} to another user.

        .. warning::
            If you're being generous, we respect you.
            But if found abusing it, you will be blacklisted.

        .. rubric:: Examples

        * To give user ABCD#1234 500 chips

        .. code:: coffee
            :force:

            /give chips:500 user:ABCD#1234
        """
        if error_tuple := self.__give_santize(message, user, chips):
            await message.reply(
                embed=get_embed(
                    error_tuple[1],
                    embed_type="error",
                    title=error_tuple[0]
                )
            )
            return
        author_prof = Profiles(message.author)
        mention_prof = Profiles(user)
        if author_prof.get("balance") < chips:
            await self.handle_low_balance(message, author_prof)
            return
        author_prof.debit(chips)
        mention_prof.credit(chips)
        Trades(
            message.author,
            user, chips
        ).save()
        await message.reply(
            embed=get_embed(
                f"chips transferred: **{chips}** {self.chip_emoji}"
                f"\nRecipient: **{user}**",
                title="Transaction Successful",
                color=author_prof.get('embed_color')
            )
        )

    @model(Inventory)
    async def cmd_ids(
        self, message: Message,
        item_name: str, **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param item_name: The name of the item to get IDs for.
        :type item_name: str

        .. meta::
            :description: Check IDs of your items.

        .. rubric:: Syntax
        .. code:: coffee

            /ids item_name:Name

        .. rubric:: Description

        Get a list of IDs of an item you own using its name.

        .. rubric:: Examples

        * To get the list of IDs for the Common Chest

        .. code:: coffee
            :force:

            /ids item_name:Common Chest
        """
        ids = Inventory(
            message.author
        ).from_name(item_name.title())
        if not ids:
            await message.reply(
                embed=get_embed(
                    f'**{item_name}**\nYou have **0** of those.',
                    title=f"{message.author.name}'s Item IDs",
                    color=Profiles(message.author).get('embed_color')
                )
            )
            return
        embeds = self.__ids_get_embeds(message, item_name, ids)
        await self.paginate(message, embeds)

    @model(Inventory)
    @alias('inv')
    async def cmd_inventory(self, message: Message, **kwargs):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`

        .. meta::
            :description: Check your inventory.
            :aliases: inv

        .. rubric:: Syntax
        .. code:: coffee

            /inventory

        .. rubric:: Description

        Check your inventory for collected Chests, Treasures, etc.
        """
        inv = Inventory(message.author)
        catog_dict, net_worth = inv.get()
        emb = get_embed(
            "Your personal inventory categorized according to item type.\n"
            "You can get the list of IDs for an item using "
            f"`/ids item_name`.\n"
            "\n> Your inventory's net worth, excluding Chests, is "
            f"**{net_worth}** {self.chip_emoji}.",
            title=f"{message.author.name}'s Inventory",
            color=Profiles(message.author).get('embed_color')
        )
        for idx, (catog, items) in enumerate(catog_dict.items()):
            catog_name = self.verbose_names.get(catog, catog)
            unique_items = []
            for item in items:
                if item['name'] not in (
                    itm['name']
                    for itm in unique_items
                ):
                    item['count'] = [
                        itm['name']
                        for itm in items
                    ].count(item['name'])
                    unique_items.append(item)
            unique_str = "\n".join(
                f"『{item['emoji']}』 **{item['name']}** x{item['count']}"
                for item in unique_items
            )
            emb.add_field(
                name=f"**{catog_name}s** ({len(items)})",
                value=unique_str,
                inline=True
            )
            if idx % 2 == 0:
                emb.add_field(
                    name="\u200B",
                    value="\u200B",
                    inline=True
                )
        await message.reply(embed=emb)

    @defer
    @model([Loots, Profiles, Chest, Inventory])
    @suggest_actions([
        ("profilecommands", "loot"),
        ("profilecommands", "daily")
    ])
    async def cmd_open(
        self, message: Message,
        itemid: Optional[str] = None,
        item_name: Optional[str] = None,
        quantity: Optional[int] = None,
        **kwargs
    ):

        # pylint: disable=no-member

        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param itemid: The ID of the item to open.
        :type itemid: Optional[str]
        :param item_name: The name of the item to open.
        :type item_name: Optional[str]
        :param quantity: The number of items to open.
        :type quantity: Optional[int]
        :min_value quantity: 1

        .. meta::
            :description: Open a Treasure Chest, Lootbag or Reward Box.

        .. rubric:: Syntax
        .. code:: coffee

            /open (itemid:Id or item_name:Name) [quantity:Number]

        .. rubric:: Description

        Opens any of these that you own

        * Treasure :class:`~scripts.base.items.Chest`

        * :class:`~scripts.base.items.Lootbag`

        * :class:`~scripts.base.items.Rewardbox`

        There are 3 different chests and scale with your tier.
        Here's a drop table

        .. code:: py

            ╔════╦═════════╦═════════╦════════════╗
            ║Tier║  Chest  ║Drop Rate║ Pokechips  ║
            ╠════╬═════════╬═════════╬════════════╣
            ║  1 ║ Common  ║   66%   ║  34 - 191  ║
            ║  2 ║  Gold   ║   25%   ║ 192 - 1110 ║
            ║  3 ║Legendary║    9%   ║1111 - 10000║
            ╚════╩═════════╩═════════╩════════════╝

        Lootbags are similar to Chests but they will contain items for sure.
        They can either be Normal or Premium.
        Premium Lootbag will contain a guaranteed Premium Item.
        All the items will be of a separate category.
        Reward Boxes are similar to Lootbags but the items are fixed.

        .. rubric:: Examples

        * To open all Common Chests

        .. code:: coffee
            :force:

            /open item_name:common chest

        * To open 3 Gold Chests

        .. code:: coffee
            :force:

            /open item_name:gold chest quantity:3

        * To open a lootbag/reward box with ID 0000AAAA

        .. code:: coffee
            :force:

            /open itemid:0000AAAA
        """
        openables = self.__open_get_openables(
            message, itemid, item_name, quantity
        )
        if not openables:
            await message.reply(
                embed=get_embed(
                    "Make sure you actually own this Item.",
                    embed_type="error",
                    title="Invalid Chest/Lootbag ID"
                ),
                view=kwargs.get('view')
            )
            return
        await self.__open_handle_rewards(message, openables)

    @model([Transactions, Inventory, Profiles])
    @check_completion
    async def cmd_redeem(
        self, message: Message,
        code: str, **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param code: The code to redeem.
        :type code: str

        .. meta::
            :description: Redeem the webshop code for rewards.

        .. rubric:: Syntax
        .. code:: coffee
            :force:

            /redeem code:Code

        .. rubric:: Description

        Redeem the webshop code for rewards.

        .. rubric:: Examples

        * To redeem the code `0000AAAA`

        .. code:: coffee
            :force:

            /redeem code:0000AAAA
        """
        transaction = await self.__redeem_get_transaction(message, code)
        if not transaction:
            return
        emb = self.__redeem_get_embed(transaction)
        confirm_view = self.__redeem_get_confirm_view(
            message, transaction, code
        )
        await message.reply(
            embed=emb,
            view=confirm_view
        )

    @model(Profiles)
    async def cmd_redeem_chips(
        self, message: Message,
        chips: int, **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param chips: The chips of chips to redeem.
        :type chips: int
        :min_value chips: 10

        .. meta::
            :description: Convert pokebonds to pokechips.

        .. rubric:: Syntax
        .. code:: coffee

            /redeem_chips chips:amount

        .. rubric:: Description

        Redeem your pokebonds as x10 pokechips.

        .. rubric:: Examples

        * To redeem 500 pokechips

        .. code:: coffee
            :force:

            /redeem_chips chips:500
        """
        if chips % 10 != 0:
            await message.reply(
                embed=get_embed(
                    "The number of chips must be a multiple of 10.",
                    embed_type="error",
                    title="Invalid chips"
                )
            )
            return
        profile = Profiles(message.author)
        if profile.get("pokebonds") < chips // 10:
            await message.reply(
                embed=get_embed(
                    f"You cannot afford that many chips.\n"
                    f"You'll need {chips // 10} {self.bond_emoji} for that.",
                    embed_type="error",
                    title="Insufficient Balance"
                )
            )
            return
        profile.debit(chips // 10, bonds=True)
        profile.credit(chips)
        await message.reply(
            embed=get_embed(
                f"Succesfully converted **{chips // 10}** {self.bond_emoji}"
                f" into **{chips}** {self.chip_emoji}",
                title="Redeem Succesfull",
                color=profile.get('embed_color')
            )
        )

    @model([Profiles, Item, Inventory])
    async def cmd_sell(
        self, message: Message,
        itemid: Optional[str] = None,
        item_name: Optional[str] = None,
        quantity: Optional[int] = 1,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param itemid: The ID of the item to sell.
        :type itemid: Optional[str]
        :param item_name: The name of the item to sell.
        :type item_name: Optional[str]
        :param quantity: The quantity of the item to sell.
        :type quantity: Optional[int]
        :min_value quantity: 1
        :default quantity: 1

        .. meta::
            :description: Sells item from inventory.

        .. rubric:: Syntax
        .. code:: coffee

            /sell (itemid:Id or item_name:Name) [quantity:value]

        .. rubric:: Description

        Sells a :class:`~scripts.base.items.Tradable` from your inventory
        to the PokeGambler Shop. You can either provide a name or an itemid.
        If name is provided, you can sell multiples by specifying quantity.

        .. note::

            :class:`~scripts.base.items.Tradable` items aren't yet implemented.

        .. note::

            Quantity option is ignored if itemid is provided. Only one is sold.

        .. rubric:: Examples

        * To sell an item with ID 0000FFFF

        .. code:: coffee
            :force:

            /sell itemid:0000FFFF

        * To sell 10 Gears (Tradables)

        .. code:: coffee
            :force:

            /sell item_name:Gear quantity:10
        """
        # pylint: disable=no-member
        inventory = Inventory(message.author)
        if itemid is None:
            item = inventory.from_id(itemid)
            if not item:
                await message.reply(
                    embed=get_embed(
                        "You do not possess that Item.",
                        embed_type="error",
                        title="Invalid Item ID"
                    )
                )
                return
            new_item = Item.from_id(itemid)
            if not new_item.sellable:
                await message.reply(
                    embed=get_embed(
                        "You cannot sell that Item.",
                        embed_type="error",
                        title="Invalid Item type"
                    )
                )
                return
            deleted = inventory.delete(itemid, 1)
        elif item_name is None:
            new_item = Item.from_name(item_name)
            deleted = inventory.delete(
                item_name, quantity, is_name=True
            )
        else:
            await message.reply(
                embed=get_embed(
                    "You should mention either an Item ID or a name.",
                    embed_type="error",
                    title="Invalid Item"
                )
            )
            return
        if deleted == 0:
            await message.reply(
                embed=get_embed(
                    "Couldn't sell anything cause no items were found.",
                    embed_type="warning",
                    title="No Items sold"
                )
            )
            return
        bonds = False
        curr = self.chip_emoji
        gained = new_item.price * quantity
        if new_item.premium:
            gained //= 10
            curr = self.bond_emoji
            bonds = True
        profile = Profiles(message.author)
        profile.credit(
            gained, bonds=bonds
        )
        Shop.refresh_tradables()
        await message.reply(
            embed=get_embed(
                f"Succesfully sold `{deleted}` of your listed item(s).\n"
                "Your account has been credited: "
                f"**{gained}** {curr}",
                title="Item(s) Sold",
                color=profile.get('embed_color')
            )
        )

    @defer
    @model([Item, Profiles])
    @suggest_actions([
        ("tradecommands", "shop")
    ])
    async def cmd_shop(
        self, message: Message,
        category: Optional[str] = None,
        premium: Optional[bool] = False,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param category: The category of items to display.
        :type category: Optional[str]
        :param premium: Whether to display premium items.
        :type premium: Optional[bool]
        :default premium: False

        .. meta::
            :description: Access the PokeGambler Shop.

        .. rubric:: Syntax
        .. code:: coffee

            /shop [category:Name] [premium:True/False]

        .. rubric:: Description

        Used to access the PokeGambler :class:`~scripts.base.shop.Shop`.
        If a category is provided, list of items will be shown.
        Otherwise a list of categories will be displayed.
        To access the secret shop, use the Premium option.

        .. note::

            You need to own PokeBonds to access the Premium Shop.

        .. rubric:: Examples

        * To view the shop categoies

        .. code:: coffee
            :force:

            /shop

        * To view the shop for Titles

        .. code:: coffee
            :force:

            /shop category:Titles

        * To view the Premium shop for Gladiators

        .. code:: coffee
            :force:

            /shop category:Gladiators premium:True
        """
        shop = Shop
        profile = Profiles(message.author)
        if premium:
            shop = PremiumShop
            if profile.get("pokebonds") == 0:
                await message.reply(
                    embed=get_embed(
                        "This option is available only to users"
                        " who purchased PokeBonds.",
                        embed_type="error",
                        title="Premium Only"
                    ),
                    view=LinkView(
                        url="https://pokegambler.vercel.app/store",
                        label="Buy Pokebonds",
                        emoji=self.bond_emoji
                    )
                )
                return
        shop.refresh_tradables()
        categories = shop.categories
        shop_alias = shop.alias_map
        if category and category.title() not in shop_alias:
            cat_str = "\n".join(
                f"+ {catog}" if shop.categories[catog].items
                else f"- {catog} (To Be Implemented)"
                for catog in sorted(
                    categories,
                    key=lambda x: -len(shop.categories[x].items)
                )
            )
            await message.reply(
                embed=get_embed(
                    "That category does not exist. "
                    f"Try one of these:\n```diff\n{cat_str}\n```",
                    embed_type="error",
                    title="Invalid Category"
                ),
                view=kwargs.get("view")
            )
            return
        if not category:
            embeds = self.__shop_get_catogs(shop, profile)
        else:
            emb = self.__shop_get_page(
                shop,
                category.title(),
                message.author
            )
            embeds = [emb]
        if kwargs.get("premium"):
            for emb in embeds:
                emb.set_image(
                    url="https://cdn.discordapp.com/attachments/"
                    "874623706339618827/874627340523700234/pokebond.png"
                )
        await self.paginate(message, embeds)

    @model([Inventory, Item])
    async def cmd_use(
        self, message: Message,
        ticket: str, **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param ticket: The ID of the ticket to use.
        :type ticket: str

        .. meta::
            :description: Use a consumable ticket.

        .. rubric:: Syntax
        .. code:: coffee

            /use ticket:id

        .. rubric:: Description

        Use a consumable ticket and trigger it's related command.

        .. rubric:: Examples

        * To use the Background Change ticket with ID FFF000

        .. code:: coffee
            :force:

            /use ticket:FFF000
        """
        valid = await HexValidator(
            message=message,
            on_error={
                'title': "Invalid Ticket ID",
                'description': "You need to enter a valid ticket ID."
            },
            on_null={
                'title': "No Ticket ID specified",
                'description': "You need to enter a ticket ID."
            }
        ).validate(ticket)
        if not valid:
            return
        ticket = Inventory(message.author).from_id(ticket)
        # pylint: disable=no-member
        if (
            not ticket
            or "Change" not in ticket.name
        ):
            if ticket is None:
                content = "You don't have that ticket."
            else:
                content = "That is not a valid ticket."
            await dm_send(
                message, message.author,
                embed=get_embed(
                    content,
                    embed_type="error",
                    title="Invalid Ticket"
                )
            )
            return
        for module in get_modules(self.ctx):
            for cmd in dir(module):
                command = getattr(module, cmd)
                if hasattr(command, "__dict__") and command.__dict__.get(
                    "ticket"
                ) == ticket.name:
                    await command(message, **kwargs)
                    return
        await dm_send(
            message, message.author,
            embed=get_embed(
                "This ticket cannot be used yet.\n"
                "Stay tuned for future updates.",
                embed_type="warning",
                title="Not Yet Usable"
            )
        )

    @os_only
    @check_completion
    @model(Profiles)
    @alias("cashout")
    async def cmd_withdraw(
        self, message: Message,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`

        .. meta::
            :description: Withdraw other pokebot credits.

        .. rubric:: Syntax
        .. code:: coffee

            /withdraw

        .. rubric:: Description

        Exchange Pokechips as other pokemon bot credits.
        """
        pokebot, quantity = await self.__get_inputs(
            message, mode="withdraw"
        )
        if pokebot is None:
            return
        req_msg, admin = await self.__admin_accept(
            message, pokebot, quantity,
            mode="withdraw"
        )
        if admin is None:
            return
        thread = await self.__get_thread(message, pokebot, req_msg)
        await self.__handle_transaction(
            message, thread,
            admin, pokebot, quantity,
            mode="withdraw"
        )

    async def __admin_accept(
        self, message, pokebot,
        quantity, mode="deposit"
    ):
        admins = discord.utils.get(message.guild.roles, name="Admins")
        confirm_view = ConfirmView(
            check=lambda intcn: any([
                is_admin(intcn.user),
                is_owner(self.ctx, intcn.user)
            ]),
            timeout=600
        )
        req_msg = await message.channel.send(
            content=admins.mention,
            embed=get_embed(
                title=f"New {mode.title()} Request",
                content=f"**{message.author}** has requested to {mode} "
                f"**{quantity:,}**『{pokebot.name}』credits."
            ),
            view=confirm_view
        )
        await confirm_view.dispatch(self)
        if confirm_view.value is None:
            if confirm_view.notify:
                await dm_send(
                    message, message.author,
                    embed=get_embed(
                        "Looks like none of our Admins are free.\n"
                        "Please try again later.",
                        embed_type="warning",
                        title="Unable to Start Transaction."
                    )
                )
            return req_msg, None
        return req_msg, confirm_view.user

    async def __get_inputs(self, message, mode="deposit"):
        def get_rate(bot: Member) -> int:
            rate = CurrencyExchange[bot.name].value
            return f"Exchange Rate: x{rate} Pokechips"
        already_exchanged = Exchanges(
            user=message.author
        ).get_daily_exchanges(mode.title())
        bounds = (1000, 2_500_000 - already_exchanged)
        if mode == "withdraw":
            bounds = (10000, 250_000 - already_exchanged)
        if bounds[1] < bounds[0]:
            remaining = (
                (datetime.now().replace(
                    hour=0, minute=0, second=0,
                ) + timedelta(days=1)) - datetime.now()
            ).total_seconds()
            rem_str = get_formatted_time(remaining)
            await dm_send(
                message, message.author,
                embed=get_embed(
                    "You have maxed out for today.\n"
                    f"Try again after {rem_str}.",
                    embed_type="warning",
                    title="Unable to Start Transaction."
                )
            )
            return None, None

        async def create_modal(view, interaction):
            async def modal_callback(modal, intcn):
                proceed = await ChainValidator(
                    intcn,
                    {
                        MinValidator: {
                            "message": intcn,
                            "min_value": bounds[0],
                            "dm_user": True
                        },
                        MaxValidator: {
                            "message": intcn,
                            "max_value": bounds[1],
                            "dm_user": True
                        }
                    }
                ).validate(modal.results[0])
                if not proceed:
                    modal.results = [None]
                else:
                    return {
                        "embed": get_embed(
                            content="Our admins have been notified.\n"
                            "Please wait till one of them accepts"
                            " or retry after 10 minutes.",
                            title="Request Registered."
                        )
                    }

            if view.value is None:
                return
            pokename = str(view.value).split('#', maxsplit=1)[0]
            amount_modal = CallbackReplyModal(
                callback=modal_callback,
                title=f"Exchange Amount for {pokename} Credits",
                timeout=120
            )
            amount_modal.add_short(
                f"How much do you want to {mode}?",
                placeholder=f"Min: {bounds[0]:,}, Max: {bounds[1]:,}"
            )
            await interaction.response.send_modal(
                amount_modal
            )
            await amount_modal.wait()
            return amount_modal.results[0]

        pokebots = discord.utils.get(
            message.guild.roles,
            name="Pokebot"
        ).members
        choices_view = SelectConfirmView(
            placeholder="Choose the Pokebot from this list",
            options={
                bot: get_rate(bot)
                for bot in pokebots
            },
            check=lambda x: x.user.id == message.author.id,
            callback=create_modal
        )
        await dm_send(
            message, message.author,
            content="Which pokemon themed bot's credits"
            " do you want to exchange?",
            view=choices_view
        )
        await choices_view.dispatch(self)
        pokebot = choices_view.value
        if not pokebot or not choices_view.callback_result:
            return None, None
        quantity = int(choices_view.callback_result.replace(',', ''))
        return pokebot, quantity

    # pylint: disable=too-many-arguments
    async def __handle_transaction(
        self, message, thread,
        admin, pokebot, chips,
        mode="deposit"
    ):
        confirm_or_cancel = ConfirmOrCancelView(timeout=None)
        await thread.send(
            embed=get_embed(
                title="Starting the transaction."
            ),
            content=f"**User**: {message.author.mention}\n"
            f"**Admin**: {admin.mention}",
            view=confirm_or_cancel
        )
        await confirm_or_cancel.dispatch(self)
        if confirm_or_cancel.value:
            content = (
                None if mode == "deposit"
                else f"{message.author.mention}, check your balance"
                " using the `/balance` command."
            )
            getattr(
                Profiles(message.author),
                "credit" if mode == "deposit" else "debit"
            )(chips)
            Profiles(admin).credit(int(chips * 0.1))
            Exchanges(
                message.author, admin,
                pokebot, chips, mode.title()
            ).save()
            await dm_send(
                message, admin,
                embed=get_embed(
                    title=f"Credited {int(chips * 0.1):,} chips to"
                    " your account."
                )
            )
        else:
            content = "Transaction cancelled."
        await thread.send(
            content=content,
            embed=get_embed(
                title=f"Closing the transaction for {message.author}."
            )
        )
        await thread.edit(
            archived=True,
            locked=True
        )

    @staticmethod
    async def __get_thread(message, pokebot, req_msg):
        tname = f"Transaction for {message.author.id}"
        thread = await req_msg.channel.create_thread(
            name=tname,
            message=req_msg
        )
        await req_msg.delete()
        await thread.add_user(message.author)
        await thread.add_user(pokebot)
        return thread

    async def __buy_get_item(
        self, message, itemid
    ) -> Tuple[Shop, Item]:
        shop = Shop
        shop.refresh_tradables()
        try:
            item = shop.get_item(itemid, force_new=True)
            if not item:
                shop = PremiumShop
                shop.refresh_tradables()
                item = shop.get_item(itemid, force_new=True)
            if not item:
                await message.reply(
                    embed=get_embed(
                        "This item was not found in the Shop.\n"
                        "Since the Shop is dynamic, maybe it's too late.",
                        embed_type="error",
                        title="Item not in Shop"
                    )
                )
                return shop, None
            if all([
                isinstance(item, Title),
                message.guild.id != self.ctx.official_server
            ]):
                official_server = self.ctx.get_guild(self.ctx.official_server)
                await message.reply(
                    embed=get_embed(
                        f"You can buy titles only in [『{official_server}』]"
                        "(https://discord.gg/g4TmVyfwj4).",
                        embed_type="error",
                        title="Cannot buy Titles here."
                    )
                )
                return shop, None
            return shop, item
        except (ValueError, ZeroDivisionError):
            await message.reply(
                embed=get_embed(
                    "The provided ID seems to be of wrong format.\n",
                    embed_type="error",
                    title="Invalid Item ID"
                )
            )
            return shop, None

    async def __buy_perform(self, message, quantity, item):
        task = item.buy(
            message=message,
            quantity=quantity,
            ctx=self.ctx
        )
        res = (await task) if asyncio.iscoroutinefunction(
            item.buy
        ) else task
        if res != "success":
            await message.reply(
                embed=get_embed(
                    f"{res}\nYour account has not been charged.",
                    embed_type="error",
                    title="Purchase failed"
                )
            )
            return False
        return True

    @staticmethod
    def __give_santize(message, user, chips):
        error_tuple = ()
        if not user:
            error_tuple = (
                "No user mentioned.",
                "Please mention whom you want to give it to."
            )
        elif not chips:
            error_tuple = (
                "Invalid amount.",
                "Please provide a valid amount. (Min 10 chips)"
            )
        elif message.author.id == user.id:
            error_tuple = (
                "Invalid user.",
                "Nice try mate, but it wouldn't have made a difference."
            )
        elif user.bot:
            error_tuple = (
                "Bot account found.",
                "We don't allow shady deals with bots."
            )
        elif Blacklist.is_blacklisted(str(user.id)):
            error_tuple = (
                "Blacklisted user.",
                "That user is blacklisted and cannot receive any chips."
            )
        return error_tuple

    @staticmethod
    def __ids_get_embeds(message, item_name, ids):
        embeds = []
        for idx in range(0, len(ids), 10):
            cnt_str = f'{idx + 1} - {min(idx + 11, len(ids))} / {len(ids)}'
            emb = get_embed(
                f'**{item_name}**『{cnt_str}』',
                title=f"{message.author.name}'s Item IDs",
                footer="Use 『/details itemid』"
                "for detailed view.",
                color=Profiles(message.author).get('embed_color')
            )
            for id_ in ids[idx:idx+10]:
                emb.add_field(
                    name="\u200B",
                    value=f"**{id_}**",
                    inline=False
                )
            embeds.append(emb)
        return embeds

    @staticmethod
    def __open_get_openables(
        message: Message,
        itemid: str,
        item_name: str,
        quantity: int
    ) -> List[Item]:
        if itemid is not None:
            openable = Inventory(
                message.author
            ).from_id(itemid)
            return [openable] if openable else []
        if item_name is None:
            return []
        lb_name = item_name.title()
        chest_name = lb_name.replace(
            'Chest', ''
        ).strip()
        chest_patt = re.compile(
            fr"{chest_name}.*Chest",
            re.IGNORECASE
        )
        if any(
            chest_patt.match(chest.__name__)
            for chest in Chest.__subclasses__()
        ):
            chests = Inventory(
                message.author
            ).from_name(fr"{chest_name}.*Chest")
            if not chests:
                return []
            openables = [
                Item.from_id(itemid)
                for itemid in chests
            ]
        else:
            bags = Inventory(
                message.author
            ).from_name(lb_name)
            openables = [
                Item.from_id(itemid)
                for itemid in bags
            ]
            if not openables or openables[0].category not in (
                "Rewardbox", "Lootbag"
            ):
                return []
        return (
            openables[:quantity] if quantity is not None
            else openables
        )

    async def __open_handle_rewards(
        self, message: Message,
        openables: List[Union[Chest, Lootbag, Rewardbox]]
    ) -> str:
        chips = sum(
            openable.chips
            for openable in openables
        )
        profile = Profiles(message.author)
        profile.credit(chips)
        loot_model = Loots(message.author)
        earned = loot_model.get("earned")
        loot_model.update(
            earned=(earned + chips)
        )
        content = f"You have recieved **{chips}** {self.chip_emoji}."
        items = []
        for openable in openables:
            embedded_items = None
            if openable.name == "Legendary Chest":
                embedded_items = LegendaryChest.get_items(openable.itemid)
            if openable.category == 'Lootbag':
                embedded_items = Lootbag.get_items(openable.itemid)
            if openable.category == 'Rewardbox':
                embedded_items = Rewardbox.get_items(openable.itemid)
            if embedded_items:
                items.extend(embedded_items)
        if items:
            item_str = '\n'.join(
                f"**『{item.emoji}』 {item} x{items.count(item)}**"
                for item in set(items)
            )
            content += f"\nAnd woah, you also got:\n{item_str}"
        inv = Inventory(message.author)
        for embedded_items in items:
            inv.save(embedded_items.itemid)
        inv.delete([
            openable.itemid
            for openable in openables
        ])
        quant_str = f"x{len(openables)} " if len(openables) > 1 else ''
        await message.reply(
            embed=get_embed(
                content,
                title=f"Opened {quant_str}{openables[0].name}",
                color=profile.get('embed_color')
            )
        )

    def __redeem_get_confirm_view(self, message, transaction, code):
        async def claim_callback(view, intcn, **kwargs):
            async def balance_callback(view, intcn, **kwargs):
                await self.ctx.profilecommands.cmd_balance(
                    CustomInteraction(intcn)
                )

            async def inventory_callback(view, intcn, **kwargs):
                await self.ctx.tradecommands.cmd_inventory(
                    CustomInteraction(intcn)
                )

            buttons = []
            checklist = []

            if transaction.webitem.meta.get('has_currency'):
                profile = Profiles(message.author)
                # pylint: disable=no-member
                won_chips = profile.won_chips
                pokebonds = profile.pokebonds
                balance = profile.balance
                profile.update(
                    won_chips=won_chips + (
                        transaction.webitem.reward_pokechips
                        * transaction.quantity
                    ),
                    pokebonds=pokebonds + (
                        transaction.webitem.reward_pokebonds
                        * transaction.quantity
                    ),
                    balance=(
                        balance
                        + (
                            transaction.webitem.reward_pokechips
                            * transaction.quantity
                        )
                        + (
                            transaction.webitem.reward_pokebonds
                            * transaction.quantity
                            * 10
                        )
                    )
                )
                buttons.append(
                    CallbackButton(
                        callback=balance_callback,
                        label="Check Balance"
                    )
                )
                checklist.append('`Balance`')
            if transaction.webitem.meta.get('is_bundle'):
                inventory = Inventory(message.author)
                inventory.bulk_insert([
                    item['item'].itemid
                    for item in transaction.webitem.reward_items
                    for _ in range(item['quantity'])
                    for _ in range(transaction.quantity)
                ])
                buttons.append(
                    CallbackButton(
                        callback=inventory_callback,
                        label="Open Inventory"
                    )
                )
                checklist.append('`Inventory`')
            self.redeem_lock[
                (code, message.author.id)
            ] = "You have already claimed this code."
            transaction.redeem()
            btn_view = CallbackButtonView(
                buttons=buttons,
                check=lambda intcn: intcn.user.id == message.author.id,
            )
            check_msg = (
                checklist[0]
                if len(checklist) == 1
                else ' and '.join(checklist)
            )
            await CustomInteraction(intcn).reply(
                embed=get_embed(
                    content="You have successfully claimed your rewards.\n"
                    f"Check your {check_msg}.",
                ),
                view=btn_view
            )
        confirm_view = CallbackButtonView(
            buttons=[
                CallbackButton(
                    callback=claim_callback,
                    label="Claim",
                )
            ],
            check=lambda intcn: intcn.user.id == message.author.id
        )
        return confirm_view

    @staticmethod
    def __redeem_get_embed(transaction):
        fields = {}
        emb_config_map = {}
        webitem = transaction.webitem
        if webitem.meta['has_currency']:
            if pokechips := webitem.reward_pokechips:
                fields['Pokechips'] = pokechips * transaction.quantity
                emb_config_map['Pokechips'] = {
                    'highlight_lang': 'py'
                }
            if pokebonds := webitem.reward_pokebonds:
                fields['Pokebonds'] = pokebonds * transaction.quantity
                emb_config_map['Pokebonds'] = {
                    'highlight_lang': 'py'
                }
        if webitem.meta['is_bundle']:
            fields['Items'] = '\n'.join(
                f"【{item['item'].name}】 x {item['quantity'] * transaction.quantity}"
                for item in webitem.reward_items
            )
            emb_config_map['Items'] = {
                'inline': False,
                'highlight': True,
                'highlight_lang': 'py'
            }
        name = f'【{webitem.name}】'
        if transaction.quantity > 1:
            name += f'x {transaction.quantity}'
        emb = get_embed(
            title=f"{name} - Claim Your Rewards",
            content="You can claim all these items.",
            # image=webitem.image,
            fields=fields,
            fields_config=EmbedFieldsConfig(
                highlight=True,
                field_config_map=emb_config_map
            )
        )
        return emb

    async def __redeem_get_transaction(self, message, code):
        if (code, message.author.id) in self.redeem_lock:
            await message.reply(
                embed=get_embed(
                    title="Duplicate Claim Request",
                    content=self.redeem_lock[(code, message.author.id)],
                    embed_type="warning"
                )
            )
            return
        self.redeem_lock[
            (code, message.author.id)
        ] = "You have a pending claim request."
        validator_kwargs = {
            "message": message,
            "on_error": {
                'title': "Invalid Claim Code",
                'description': "You need to enter a valid claim code."
            },
            "on_null": {
                'title': "No Claim Code specified",
                'description': "You need to enter a claim code."
            }
        }
        validator_spec = {
            HexValidator: validator_kwargs,
            MinLengthValidator: {
                **validator_kwargs,
                'min_length': 24
            },
            MaxLengthValidator: {
                **validator_kwargs,
                'max_length': 24
            }
        }
        valid = await ChainValidator(
            message, validator_spec
        ).validate(code)
        if not valid:
            return
        transactions = Transactions(message.author).get(
            _id=ObjectId(code)
        )
        if not transactions:
            await message.reply(
                embed=get_embed(
                    title="Invalid Claim Code",
                    content="You need to enter a valid claim code.",
                    embed_type="error"
                )
            )
            return
        transaction = transactions[0]
        if transaction.redeemed:
            await message.reply(
                embed=get_embed(
                    content="This claim code has already been redeemed.",
                    embed_type='error'
                ),
                view=LinkView(
                    url="https://pokegambler.vercel.app/store",
                    label="Visit Store",
                    emoji=self.bond_emoji
                )
            )
            return
        return transaction

    @staticmethod
    def __shop_get_catogs(shop, profile):
        categories = {
            key: catog
            for key, catog in sorted(
                shop.categories.items(),
                key=lambda x: len(x[1].items),
                reverse=True
            )
            if catog.items
        }
        catogs = list(categories.values())
        embeds = []
        for i in range(0, len(catogs), 3):
            emb = get_embed(
                "**To view the items in a specific category:**\n"
                "**`/shop category`**",
                title="PokeGambler Shop",
                footer="All purchases except Tradables "
                "are non-refundable.",
                color=profile.get('embed_color')
            )
            for catog in catogs[i:i+3]:
                emb.add_field(
                    name=str(catog),
                    value=f"```diff\n{dedent(catog.description)}\n"
                    "To view the items:\n"
                    f"/shop {catog.name}\n```",
                    inline=False
                )
            embeds.append(emb)
        return embeds

    def __shop_get_page(
        self, shop: Type[Shop],
        catog_str: str, user: Member
    ) -> Embed:
        shopname = re.sub('([A-Z]+)', r' \1', shop.__name__).strip()
        categories = shop.categories
        catog = categories[shop.alias_map[catog_str]]
        user_tier = Loots(user).tier
        if shop.alias_map[catog_str] in [
            "Tradables", "Consumables", "Gladiators"
        ]:
            shop.refresh_tradables()
        if len(catog.items) < 1:
            emb = get_embed(
                    f"`{catog.name} {shopname}` seems to be empty right now.\n"
                    "Please try again later.",
                    embed_type="warning",
                    title="No items found",
                    thumbnail="https://raw.githubusercontent.com/twitter/"
                    f"twemoji/master/assets/72x72/{ord(catog.emoji):x}.png"
                )
        else:
            profile = Profiles(user)
            balance = (
                f"`{profile.get('pokebonds'):,}` {self.bond_emoji}"
                if shop is PremiumShop
                else f"`{profile.get('won_chips'):,}` {self.chip_emoji}"
            )
            emb = get_embed(
                    f"**To buy any item, use `/buy itemid`**"
                    f"\n**You currently have: {balance}**",
                    title=f"{catog} {shopname}",
                    no_icon=True,
                    color=profile.get('embed_color')
                )
            for item in catog.items:
                itemid = f"{item.itemid:0>8X}" if isinstance(
                    item.itemid, int
                ) else item.itemid
                price = item.price
                curr = self.chip_emoji
                if item.premium:
                    price //= 10
                    curr = self.bond_emoji
                if shop.alias_map[catog_str] == "Boosts":
                    price *= (10 ** (user_tier - 1))
                emb.add_field(
                        name=f"『{itemid}』 _{item}_ "
                        f"{price:,} {curr}",
                        value=f"```\n{item.description}\n```",
                        inline=False
                    )
            # pylint: disable=undefined-loop-variable
            emb.set_footer(text=f"Example:『/buy {itemid}』")
        return emb
