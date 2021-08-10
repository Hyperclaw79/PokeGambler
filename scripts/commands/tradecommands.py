"""
Trade Commands Module
"""

# pylint: disable=too-many-locals, too-many-lines
# pylint: disable=unused-argument

from __future__ import annotations
import asyncio
from typing import (
    List, Optional, TYPE_CHECKING, Tuple,
    Type, Union, Dict
)
import re

import discord

from ..base.items import Item, Chest, Lootbag, Rewardbox
from ..base.models import (
    Blacklist, CurrencyExchange, Exchanges, Inventory, Loots,
    Profiles, Trades
)
from ..base.shop import (
    BoostItem, PremiumBoostItem,
    PremiumShop, Shop, Title
)
from ..base.views import Confirm, SelectView

from ..helpers.utils import (
    dedent, dm_send,
    get_embed, get_modules,
    is_admin, is_owner
)
from ..helpers.validators import MinMaxValidator

from .basecommand import (
    Commands, alias, check_completion, dealer_only,
    model, ensure_item, no_thumb, os_only
)

if TYPE_CHECKING:
    from discord import Embed, Message, Member


class TradeCommands(Commands):
    """
    Commands that deal with the trade system of PokeGambler.
    Shop related commands fall under this category as well.
    """

    verbose_names: Dict[str, str] = {
        'Rewardbox': 'Reward Boxe',
        'Giftbox': 'Gift Boxe'
    }

    @model([Profiles, Loots, Inventory])
    async def cmd_buy(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """Buy item from Shop.
        $```scss
        {command_prefix}buy itemid [--quantity]
        ```$

        @Buys an item from the PokeGambler Shop.
        You can provide a quantity to buy multiple Tradables.
        To see the list of purchasable items, check out:
        ```diff
        {command_prefix}shop
        ```@

        ~To buy a Loot boost with ID boost_lt:
            ```
            {command_prefix}buy boost_lt
            ```
        ~To buy 10 items with ID 0000FFFF:
            ```
            {command_prefix}buy 0000FFFF --quantity 10
            ```~
        """
        if not args:
            return
        itemid = args[0].lower()
        quantity = int(kwargs.get('quantity', 1))
        shop, item = await self.__buy_get_item(message, itemid)
        if item is None:
            return
        status = shop.validate(message.author, item, quantity)
        if status != "proceed":
            await message.channel.send(
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
        await message.channel.send(
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
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Deposit other pokebot credits.
        $```scss
        {command_prefix}deposit
        ```$

        @Deposit other currencies to exchange them for Pokechips.@
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
    async def cmd_details(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """Check the details of a PokeGambler Item.
        $```scss
        {command_prefix}details chest_id
        ```$

        @Check the details, of a PokeGambler item, like:
            Description, Price, Category
        @

        ~To check the details of an Item with ID 0000FFFF:
            ```
            {command_prefix}details 0000FFFF
            ```~
        """

        item = kwargs["item"]
        await message.channel.send(embed=item.details)

    @alias("rates")
    async def cmd_exchange_rates(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """Check the exchange rates of pokebot credits.
        $```scss
        {command_prefix}exchange_rates [currency]
        ```$

        @Check the exchange rates for different pokebots credits.@

        ~To check all the exchange rates:
            ```
            {command_prefix}exchange_rates
            ```
        To check the exchange rates for Pokétwo:
            ```
            {command_prefix}rates pokétwo
            ```~
        """
        enums = CurrencyExchange
        if args:
            res = enums[args[0]]
            if res is not enums.DEFAULT:
                enums = [res]
        rates_str = '\n'.join(
            f"```fix\n1 {bot.name} Credit = {bot.value} Pokechips\n```"
            for bot in enums
            if bot is not CurrencyExchange.DEFAULT
        )
        await message.channel.send(
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
        args: Optional[List] = None,
        mentions: Optional[List[Member]] = None,
        **kwargs
    ):
        """Transfer credits.
        $```scss
        {command_prefix}give quantity @mention
        ```$

        @`🎲 Dealer Command`
        Transfer some of your own {pokechip_emoji} to another user.
        If you're being generous, we respect you.
        But if found abusing it, you will be blacklisted.@

        ~To give user ABCD#1234 500 chips:
            ```
            {command_prefix}give @ABCD#1234 500
            ```~
        """
        error_tuple = self.__give_santize(message, args, mentions)
        if error_tuple:
            await message.channel.send(
                embed=get_embed(
                    error_tuple[1],
                    embed_type="error",
                    title=error_tuple[0]
                )
            )
            return
        author_prof = Profiles(message.author)
        mention_prof = Profiles(mentions[0])
        amount = int(args[0])
        if author_prof.get("balance") < amount:
            await message.channel.send(
                embed=get_embed(
                    f"You don't have enough {self.chip_emoji}.",
                    embed_type="error",
                    title="Low Balance"
                )
            )
            return
        author_prof.debit(amount)
        mention_prof.credit(amount)
        Trades(
            message.author,
            str(mentions[0].id), amount
        ).save()
        await message.channel.send(
            embed=get_embed(
                f"Amount transferred: **{amount}** {self.chip_emoji}"
                f"\nRecipient: **{mentions[0]}**",
                title="Transaction Successful",
                color=author_prof.get('embed_color')
            )
        )

    @model(Inventory)
    async def cmd_ids(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """Check IDs of possessed items.
        $```scss
        {command_prefix}ids item_name
        ```$

        @Get a list of IDs of an item you own using its name.@

        ~To get the list of IDs for Common Chest:
            ```
            {command_prefix}ids Common Chest
            ```~
        """
        if not args:
            return
        item_name = " ".join(arg.title() for arg in args)
        ids = Inventory(
            message.author
        ).from_name(item_name)
        if not ids:
            await message.channel.send(
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
        """Check personal inventory.
        $```scss
        {command_prefix}inventory
        ```$

        @Check your personal inventory for collected Chests, Treasures, etc.@
        """
        inv = Inventory(message.author)
        catog_dict, net_worth = inv.get()
        emb = get_embed(
            "Your personal inventory categorized according to item type.\n"
            "You can get the list of IDs for an item using "
            f"`{self.ctx.prefix}ids item_name`.\n"
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
        await message.channel.send(embed=emb)

    @model([Loots, Profiles, Chest, Inventory])
    @no_thumb
    async def cmd_open(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):

        # pylint: disable=no-member

        """Opens a PokeGambler treasure chest, Lootbag or Reward Box.
        $```scss
        {command_prefix}open itemid/chest name
        ```$

        @Opens a treasure chest, a Lootbag or a Reward Box that you own.
        There are 3 different chests and scale with your tier.
        Here's a drop table:
        ```py
        ╔════╦═════════╦═════════╦════════════╗
        ║Tier║  Chest  ║Drop Rate║ Pokechips  ║
        ╠════╬═════════╬═════════╬════════════╣
        ║  1 ║ Common  ║   66%   ║  34 - 191  ║
        ║  2 ║  Gold   ║   25%   ║ 192 - 1110 ║
        ║  3 ║Legendary║    9%   ║1111 - 10000║
        ╚════╩═════════╩═════════╩════════════╝
        ```
        Lootbags are similar to Chests but they will contain items for sure.
        They can either be Normal or Premium.
        Premium Lootbag will contain a guaranteed Premium Item.
        All the items will be of a separate category.
        Reward Boxes are similar to Lootbags but the items are fixed.@

        ~To open a chest with ID 0000FFFF:
            ```
            {command_prefix}open 0000FFFF
            ```
        To open a lootbag/reward box with ID 0000AAAA:
            ```
            {command_prefix}open 0000AAAA
            ```
        To open all Gold Chests in your inventory:
            ```
            {command_prefix}open gold chest
            ```~
        """
        if not args:
            return
        openables = self.__open_get_openables(message, args)
        if not openables:
            await message.channel.send(
                embed=get_embed(
                    "Make sure you actually own this Item.",
                    embed_type="error",
                    title="Invalid Chest/Lootbag ID"
                )
            )
            return
        await self.__open_handle_rewards(message, openables)

    @model(Profiles)
    async def cmd_redeem_chips(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """Convert Bonds to Chips.
        $```scss
        {command_prefix}redeem_chips amount
        ```$

        @Redeem your pokebonds as x10 pokechips.@

        ~To redeem 500 chips:
            ```
            {command_prefix}redeem_chips 500
            ```~
        """
        if (
            not args
            or not args[0].isdigit()
            or int(args[0]) < 10
            or int(args[0]) % 10  # Must be a multiple of 10, 0 -> False
        ):
            await message.channel.send(
                embed=get_embed(
                    "You need to enter the number of chips to redeem.",
                    embed_type="error",
                    title="Invalid Amount"
                )
            )
            return
        chips = int(args[0])
        profile = Profiles(message.author)
        if profile.get("pokebonds") < chips // 10:
            await message.channel.send(
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
        await message.channel.send(
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
        args: Optional[List] = None,
        **kwargs
    ):
        """Sells item from inventory.
        $```scss
        {command_prefix}sell itemid/name [--quantity]
        ```$

        @Sells an item from your inventory to the PokeGambler Shop.
        You can either provide a name or an itemid.
        If name is provided, you can sell multiples by specifying quantity.@

        ~To sell an item with ID 0000FFFF:
            ```
            {command_prefix}sell 0000FFFF
            ```
        To sell 10 Gears (Tradables):
            ```
            {command_prefix}sell Gear --quantity 10
            ```~
        """
        # pylint: disable=no-member
        if not args:
            return
        inventory = Inventory(message.author)
        try:
            itemid = args[0]
            item = inventory.from_id(args[0])
            if not item:
                await message.channel.send(
                    embed=get_embed(
                        "You do not possess that Item.",
                        embed_type="error",
                        title="Invalid Item ID"
                    )
                )
                return
            new_item = Item.from_id(itemid)
            if not new_item.sellable:
                await message.channel.send(
                    embed=get_embed(
                        "You cannot sell that Item.",
                        embed_type="error",
                        title="Invalid Item type"
                    )
                )
                return
            deleted = inventory.delete(itemid, 1)
        except ValueError:  # Item Name
            quantity = int(kwargs.get('quantity', 1))
            name = args[0].title()
            new_item = Item.from_name(name)
            deleted = inventory.delete(name, quantity, is_name=True)
        if deleted == 0:
            await message.channel.send(
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
        await message.channel.send(
            embed=get_embed(
                f"Succesfully sold `{deleted}` of your listed item(s).\n"
                "Your account has been credited: "
                f"**{gained}** {curr}",
                title="Item(s) Sold",
                color=profile.get('embed_color')
            )
        )

    @model([Item, Profiles])
    @no_thumb
    async def cmd_shop(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """Access PokeGambler Shop.
        $```scss
        {command_prefix}shop [category] [--premium]
        ```$

        @Used to access the **PokeGambler Shop.**
        If no arguments are provided, a list of categories will be displayed.
        If a category is provided, list of items will be shown.
        To access the Premium shop, use the kwarg `--premium` at the end.
        > You need to own PokeBonds to access this shop.

        There are currently 3 shop categories:
        ```md
            1. Titles - Special Purchasable Roles
            2. Boosts - Temporary Boosts to gain an edge
            3. Tradables - Purchasable assets of trade
        ```@

        ~To view the shop categoies:
            ```
            {command_prefix}shop
            ```
        To view the shop for Titles:
            ```
            {command_prefix}shop titles
            ```
        To view the Premium shop for Gladiators:
            ```
            {command_prefix}shop gladiators --premium
            ```~
        """
        shop = Shop
        profile = Profiles(message.author)
        if kwargs.get('premium'):
            shop = PremiumShop
            if profile.get("pokebonds") == 0:
                await message.channel.send(
                    embed=get_embed(
                        "This option is available only to users"
                        " who purchased PokeBonds.",
                        embed_type="error",
                        title="Premium Only"
                    )
                )
                return
        shop.refresh_tradables()
        categories = shop.categories
        shop_alias = shop.alias_map
        if args and args[0].title() not in shop_alias:
            cat_str = "\n".join(
                f"+ {catog}" if shop.categories[catog].items
                else f"- {catog} (To Be Implemented)"
                for catog in sorted(
                    categories,
                    key=lambda x: -len(shop.categories[x].items)
                )
            )
            await message.channel.send(
                embed=get_embed(
                    "That category does not exist. "
                    f"Try one of these:\n```diff\n{cat_str}\n```",
                    embed_type="error",
                    title="Invalid Category"
                )
            )
            return
        if not args:
            embeds = self.__shop_get_catogs(shop, profile)
        else:
            emb = self.__shop_get_page(
                shop,
                args[0].title(),
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
        args: Optional[List] = None,
        **kwargs
    ):
        """Use a consumable ticket.
        $```scss
        {command_prefix}use ticket_name
        ```$

        @Use a consumable ticket and trigger it's related command.@

        ~To use the Background Change ticket with ID FFF000:
            ```
            {command_prefix}use FFF000
            ```~
        """
        if not args or not re.match(r"[0-9a-fA-F]{6}", args[0]):
            await message.channel.send(
                embed=get_embed(
                    "You need to enter a valid ticket ID.",
                    embed_type="error",
                    title="Invalid Ticket ID"
                )
            )
            return
        ticket = Inventory(message.author).from_id(args[0])
        # pylint: disable=no-member
        if (
            not ticket
            or "Change" not in ticket.name
        ):
            if ticket is None:
                content = "You don't have that ticket."
            else:
                content = "That is not a valid ticket."
            await message.channel.send(
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
                    await command(message, args=args, **kwargs)
                    return
        await message.channel.send(
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
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Withdraw other pokebot credits.
        $```scss
        {command_prefix}withdraw
        ```$

        @Exchange Pokechips as other pokemon bot credits.@
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
        chips = CurrencyExchange[pokebot.name].value
        thread = await self.__get_thread(message, pokebot, req_msg)
        await self.__handle_transaction(
            message, thread,
            admin, pokebot, chips,
            mode="withdraw"
        )

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
                await message.channel.send(
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
                await message.channel.send(
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
            await message.channel.send(
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
            await message.channel.send(
                embed=get_embed(
                    f"{res}\nYour account has not been charged.",
                    embed_type="error",
                    title="Purchase failed"
                )
            )
            return False
        return True

    @staticmethod
    def __give_santize(message, args, mentions):
        error_tuple = ()
        if not mentions:
            error_tuple = (
                "No user mentioned.",
                "Please mention whom you want to give it to."
            )
        elif not args or (
            args and (
                not args[0].isdigit()
                or int(args[0]) <= 0
            )
        ):
            error_tuple = (
                "Invalid amount.",
                "Please provide a valid amount."
            )
        elif message.author.id == mentions[0].id:
            error_tuple = (
                "Invalid user.",
                "Nice try mate, but it wouldn't have made a difference."
            )
        elif mentions[0].bot:
            error_tuple = (
                "Bot account found.",
                "We don't allow shady deals with bots."
            )
        elif Blacklist.is_blacklisted(str(mentions[0].id)):
            error_tuple = (
                "Blacklisted user.",
                "That user is blacklisted and cannot receive any chips."
            )
        return error_tuple

    def __ids_get_embeds(self, message, item_name, ids):
        embeds = []
        for idx in range(0, len(ids), 10):
            cnt_str = f'{idx + 1} - {min(idx + 11, len(ids))} / {len(ids)}'
            emb = get_embed(
                f'**{item_name}**『{cnt_str}』',
                title=f"{message.author.name}'s Item IDs",
                footer=f"Use 『{self.ctx.prefix}details itemid』"
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
        args: List[str]
    ) -> List[Item]:
        try:
            chest_name = " ".join(args).title().replace('Chest', '').strip()
            lb_name = " ".join(args).title()
            if chest_name in (
                chest.__name__.replace('Chest', '')
                for chest in Chest.__subclasses__()
            ):
                chests = Inventory(
                    message.author
                ).from_name(f"{chest_name} Chest")
                if not chests:
                    raise ValueError(f"No {chest_name} Chests in Inventory.")
                openables = [
                    Item.from_id(itemid)
                    for itemid in chests
                ]
            elif any(
                word in lb_name
                for word in [
                    "Lootbag", "Reward", "Gift"
                ]
            ):
                bags = Inventory(
                    message.author
                ).from_name(lb_name)
                if not bags:
                    raise ValueError(f"No {lb_name} in Inventory.")
                openables = [
                    Item.from_id(itemid)
                    for itemid in bags
                ]
            else:
                openable = Inventory(
                    message.author
                ).from_id(args[0])
                if openable:
                    openables = [openable]
                else:
                    raise ValueError("Item not found in inventory.")
        except (ValueError, ZeroDivisionError):
            openables = []
        return openables

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
            if openable.name == "Legendary Chest":
                item = openable.get_random_collectible()
                if item:
                    items.append(item)
            elif openable.category == 'Lootbag':
                res = openable.get_random_items()
                if res:
                    items.extend(res)
            elif openable.category == 'Rewardbox':
                res = Rewardbox.get_items(openable.itemid)
                if res:
                    items.extend(res)
        if items:
            item_str = '\n'.join(
                f"**『{item.emoji}』 {item} x{items.count(item)}**"
                for item in set(items)
            )
            content += f"\nAnd woah, you also got:\n{item_str}"
        inv = Inventory(message.author)
        for item in items:
            inv.save(item.itemid)
        inv.delete([
            openable.itemid
            for openable in openables
        ])
        quant_str = f"x{len(openables)} " if len(openables) > 1 else ''
        await message.channel.send(
            embed=get_embed(
                content,
                title=f"Opened {quant_str}{openables[0].name}",
                color=profile.get('embed_color')
            )
        )

    def __shop_get_catogs(self, shop, profile):
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
                f"**`{self.ctx.prefix}shop category`**",
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
                    f"{self.ctx.prefix}shop {catog.name}\n```",
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
                    f"**To buy any item, use `{self.ctx.prefix}buy itemid`**"
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
            emb.set_footer(text=f"Example:『{self.ctx.prefix}buy {itemid}』")
        return emb

    async def __admin_accept(
        self, message, pokebot,
        quantity, mode="deposit"
    ):
        admins = discord.utils.get(message.guild.roles, name="Admins")
        confirm_view = Confirm(
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
        pokebots = discord.utils.get(
            message.guild.roles,
            name="Pokebot"
        ).members
        choices_view = SelectView(
            heading="Choose the Pokebot from this list",
            options={
                bot: get_rate(bot)
                for bot in pokebots
            },
            check=lambda x: x.user.id == message.author.id
        )
        opt_msg = await dm_send(
            message, message.author,
            content="Which pokemon themed bot's credits"
            " do you want to exchange?",
            view=choices_view
        )
        await choices_view.dispatch(self)
        pokebot = choices_view.result
        await opt_msg.delete()
        if not pokebot:
            return None, None
        bounds = (1000, 2_500_000)
        if mode == "withdraw":
            bounds = (10000, 250_000)
        opt_msg = await dm_send(
            message, message.author,
            embed=get_embed(
                content="```yaml\n>________\n```",
                title=f"How much do you want to {mode}?",
                footer=f"Min: {bounds[0]:,}, Max: {bounds[1]:,}"
            )
        )
        reply = await self.ctx.wait_for(
            "message",
            check=lambda msg: (
                msg.channel == opt_msg.channel
                and msg.author == message.author
            )
        )
        proceed = await MinMaxValidator(
            *bounds,
            message=message,
            dm_user=True
        ).validate(reply.content)
        if not proceed:
            await opt_msg.delete()
            return None, None
        quantity = int(reply.content)
        await opt_msg.edit(
            embed=get_embed(
                content="Our admins have been notified.\n"
                "Please wait till one of them accepts"
                " or retry after 10 minutes.",
                title="Request Registered."
            )
        )
        return pokebot, quantity

    async def __get_thread(self, message, pokebot, req_msg):
        tname = f"Transaction for {message.author.id}"
        thread = await req_msg.channel.start_thread(
            name=tname,
            message=req_msg
        )
        await req_msg.delete()
        await thread.add_user(message.author)
        await thread.add_user(pokebot)
        return thread

    # pylint: disable=too-many-arguments
    async def __handle_transaction(
        self, message, thread,
        admin, pokebot, chips,
        mode="deposit"
    ):
        await thread.send(
            embed=get_embed(
                title="Starting the transaction."
            ),
            content=f"**User**: {message.author.mention}\n"
            f"**Admin**: {admin.mention}"
        )
        await self.ctx.wait_for(
            "message",
            check=lambda msg: (
                msg.channel.id == thread.id
                and msg.author == admin
                and "complete" in msg.content.lower()
            )
        )
        content = None
        if mode == "deposit":
            content = f"{message.author.mention}, check your balance" + \
                f" using the `{self.ctx.prefix}balance` command."
        await thread.send(
            content=content,
            embed=get_embed(
                title=f"Closing the transaction for {message.author}."
            )
        )
        getattr(
            Profiles(message.author),
            "credit" if mode == "deposit" else "debit"
        )(chips)
        Profiles(admin).credit(int(chips * 0.1))
        Exchanges(
            message.author, str(admin.id),
            str(pokebot.id), chips, mode.title()
        ).save()
        await dm_send(
            message, admin,
            embed=get_embed(
                title=f"Credited {int(chips * 0.1):,} chips to"
                " your account."
            )
        )
        await thread.edit(
            archived=True,
            locked=True
        )
