"""
Trade Commands Module
"""

# pylint: disable=unused-argument, too-many-locals

from __future__ import annotations
import asyncio
from typing import List, Optional, TYPE_CHECKING, Type
import re

from ..base.items import Item, Chest
from ..base.models import (
    Blacklist, Inventory, Loots,
    Profile, Trades
)
from ..base.shop import (
    BoostItem, PremiumBoostItem,
    PremiumShop, Shop, Title
)

from ..helpers.utils import dedent, get_embed

from .basecommand import (
    Commands, alias, dealer_only,
    model, ensure_item, no_thumb
)

if TYPE_CHECKING:
    from discord import Embed, Message, Member


class TradeCommands(Commands):
    """
    Commands that deal with the trade system of PokeGambler.
    Shop related commands fall under this category as well.
    """

    @model([Loots, Profile, Chest, Inventory])
    @no_thumb
    async def cmd_open(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):

        # pylint: disable=no-member

        """Opens a PokeGambler treasure chest or a Lootbag.
        $```scss
        {command_prefix}open itemid/chest name
        ```$

        @Opens a treasure chest or a Lootbag that you own.
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
        All the items will be of a separate category.@

        ~To open a chest with ID 0000FFFF:
            ```
            {command_prefix}open 0000FFFF
            ```
        To open a lootbag with ID 0000AAAA:
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

    @model(Inventory)
    @alias('inv')
    async def cmd_inventory(self, message: Message, **kwargs):
        """Check personal inventory.
        $```scss
        {command_prefix}inventory
        ```$

        @Check your personal inventory for collected Chests, Treasures, etc.@
        """
        inv = Inventory(self.database, message.author)
        catog_dict, net_worth = inv.get(counts_only=True)
        emb = get_embed(
            "Your personal inventory categorized according to item type.\n"
            "You can get the list of IDs for an item using "
            f"`{self.ctx.prefix}ids item_name`.\n"
            "\n> Your net worth, excluding Chests, is "
            f"**{net_worth}** {self.chip_emoji}.",
            title=f"{message.author.name}'s Inventory"
        )
        for idx, (catog, items) in enumerate(catog_dict.items()):
            emb.add_field(
                name=f"**{catog}s** ({len(items)})",
                value="\n".join(
                    f"『{item['emoji']}』 **{item['name']}** x{item['count']}"
                    for item in items
                ),
                inline=True
            )
            if idx % 2 == 0:
                emb.add_field(
                    name="\u200B",
                    value="\u200B",
                    inline=True
                )
        await message.channel.send(embed=emb)

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
            self.database, message.author
        ).get_ids(item_name)
        if not ids:
            await message.channel.send(
                embed=get_embed(
                    f'**{item_name}**\nYou have **0** of those.',
                    title=f"{message.author.name}'s Item IDs",
                )
            )
            return
        embeds = []
        for i in range(0, len(ids), 10):
            cnt_str = f'{i + 1} - {min(i + 11, len(ids))} / {len(ids)}'
            emb = get_embed(
                f'**{item_name}**『{cnt_str}』',
                title=f"{message.author.name}'s Item IDs",
                footer=f"Use 『{self.ctx.prefix}details itemid』"
                "for detailed view."
            )
            for id_ in ids[i:i+10]:
                emb.add_field(
                    name="\u200B",
                    value=f"**{id_}**",
                    inline=False
                )
            embeds.append(emb)
        await self.paginate(message, embeds)

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
        if kwargs.get('premium'):
            shop = PremiumShop
            if Profile(
                self.database,
                message.author
            ).get()["pokebonds"] == 0:
                await message.channel.send(
                    embed=get_embed(
                        "This option is available only to users"
                        " who purchased PokeBonds.",
                        embed_type="error",
                        title="Premium Only"
                    )
                )
                return
        categories = shop.categories
        shop_alias = shop.alias_map
        if args and args[0].title() not in shop_alias:
            cat_str = "\n".join(categories)
            await message.channel.send(
                embed=get_embed(
                    "That category does not exist. "
                    f"Try one of these:\n{cat_str}",
                    embed_type="error",
                    title="Invalid Category"
                )
            )
            return
        embeds = []
        if not args:
            shop.refresh_tradables(self.database)
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
            for i in range(0, len(catogs), 3):
                emb = get_embed(
                    "**To view the items in a specific category:**\n"
                    f"**`{self.ctx.prefix}shop category`**",
                    title="PokeGambler Shop",
                    footer="All purchases except Tradables are non-refundable."
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
        else:
            emb = self.__get_shop_page(
                shop,
                args[0].title(),
                message.author
            )
            embeds.append(emb)
        if kwargs.get("premium"):
            for emb in embeds:
                emb.set_image(
                    url="https://cdn.discordapp.com/attachments/"
                    "840469669332516904/853990953953525870/pokebond.png"
                )
        await self.paginate(message, embeds)

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
        shop = Shop
        shop.refresh_tradables(self.database)
        try:
            item = shop.get_item(self.database, itemid, force_new=True)
            if not item:
                shop = PremiumShop
                item = shop.get_item(self.database, itemid, force_new=True)
        except (ValueError, ZeroDivisionError):
            await message.channel.send(
                embed=get_embed(
                    "The provided ID seems to be of wrong format.\n",
                    embed_type="error",
                    title="Invalid Item ID"
                )
            )
            return
        if not item:
            await message.channel.send(
                embed=get_embed(
                    "This item was not found in the Shop.\n"
                    "Since the Shop is dynamic, maybe it's too late.",
                    embed_type="error",
                    title="Item not in Shop"
                )
            )
            return
        status = shop.validate(self.database, message.author, item, quantity)
        if status != "proceed":
            await message.channel.send(
                embed=get_embed(
                    status,
                    embed_type="error",
                    title="Unable to Purchase item."
                )
            )
            return
        task = item.buy(
            database=self.database,
            message=message,
            quantity=quantity,
            ctx=self.ctx
        )
        quant_str = f"x {quantity}" if quantity > 1 else ''
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
            return
        spent = item.price * quantity
        if item.__class__ in [BoostItem, PremiumBoostItem]:
            tier = Loots(self.database, message.author).tier
            spent *= (10 ** (tier - 1))
        curr = self.chip_emoji
        if item.premium:
            spent //= 10
            curr = self.bond_emoji
        await message.channel.send(
            embed=get_embed(
                f"Successfully purchased **{item}**{quant_str}.\n"
                "Your account has been debited: "
                f"**{spent}** {curr}",
                title="Success",
                footer=(
                    "Your nickname might've not changed if it's too long.\n"
                    "But the role has been assigned succesfully."
                    if isinstance(item, Title)
                    else None
                )
            )
        )

    @model([Profile, Item])
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
        if not args:
            return
        inventory = Inventory(self.database, message.author)
        try:
            itemid = int(args[0], 16)
            item = inventory.from_id(itemid)
            if not item:
                await message.channel.send(
                    embed=get_embed(
                        "You do not possess that Item.",
                        embed_type="error",
                        title="Invalid Item ID"
                    )
                )
                return
            new_item = Item.from_id(self.database, itemid)
            # pylint: disable=no-member
            if not new_item.sellable:
                await message.channel.send(
                    embed=get_embed(
                        "You cannot sell that Item.",
                        embed_type="error",
                        title="Invalid Item type"
                    )
                )
                return
            deleted = inventory.delete([itemid], 1)
        except ValueError:  # Item Name
            quantity = int(kwargs.get('quantity', 1))
            name = args[0].title()
            new_item = Item.from_name(self.database, name)
            deleted = inventory.delete(name, quantity)
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
        Profile(self.database, message.author).credit(
            gained, bonds=bonds
        )
        Shop.refresh_tradables(self.database)
        await message.channel.send(
            embed=get_embed(
                f"Succesfully sold `{deleted}` of your listed item(s).\n"
                "Your account has been credited: "
                f"**{gained}** {curr}",
                title="Item(s) Sold"
            )
        )

    @dealer_only
    @model([Profile, Trades])
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
        if not mentions:
            await message.channel.send(
                embed=get_embed(
                    "Please mention whom you want to give it to.",
                    embed_type="error",
                    title="No user mentioned."
                )
            )
            return
        if not args or (
            args and (
                not args[0].isdigit()
                or int(args[0]) <= 0
            )
        ):
            await message.channel.send(
                embed=get_embed(
                    "You need to provide a valid amount.",
                    embed_type="error",
                    title="Invalid Amount."
                )
            )
            return
        if message.author.id == mentions[0].id:
            await message.channel.send(
                embed=get_embed(
                    "Nice try mate, but it wouldn't have made a difference.",
                    embed_type="error",
                    title="Invalid User."
                )
            )
            return
        if mentions[0].bot:
            await message.channel.send(
                embed=get_embed(
                    "We don't allow shady deals with bots.",
                    embed_type="error",
                    title="Bot account found."
                )
            )
            return
        if Blacklist.is_blacklisted(self.database, str(mentions[0].id)):
            await message.channel.send(
                embed=get_embed(
                    "That user is blacklisted and cannot receive any chips.",
                    embed_type="error",
                    title="Blacklisted User."
                )
            )
            return
        author_prof = Profile(self.database, message.author)
        mention_prof = Profile(self.database, mentions[0])
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
            self.database, message.author,
            str(mentions[0].id), amount
        ).save()
        await message.channel.send(
            embed=get_embed(
                f"Amount transferred: **{amount}** {self.chip_emoji}"
                f"\nRecipient: **{mentions[0]}**",
                title="Transaction Successful"
            )
        )

    @model(Profile)
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
        profile = Profile(self.database, message.author)
        if profile.get()["pokebonds"] < chips // 10:
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
                title="Redeem Succesfull"
            )
        )

    def __get_shop_page(
        self, shop: Type[Shop],
        catog_str: str, user: Member
    ) -> Embed:
        shopname = re.sub('([A-Z]+)', r' \1', shop.__name__).strip()
        categories = shop.categories
        catog = categories[shop.alias_map[catog_str]]
        user_tier = Loots(self.database, user).tier
        if shop.alias_map[catog_str] in [
            "Tradables", "Consumables", "Gladiators"
        ]:
            shop.refresh_tradables(self.database)
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
            profile = Profile(self.database, user)
            balance = (
                f"`{profile.get('pokebonds'):,}` {self.bond_emoji}"
                if shop is PremiumShop
                else f"`{profile.get('won_chips'):,}` {self.chip_emoji}"
            )
            emb = get_embed(
                    f"**To buy any item, use `{self.ctx.prefix}buy itemid`**"
                    f"\n**You currently have: {balance}**",
                    title=f"{catog} {shopname}",
                    no_icon=True
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

    def __open_get_openables(
        self, message: Message,
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
                    self.database, message.author
                ).from_name(f"{chest_name} Chest")
                if not chests:
                    raise ValueError(f"No {chest_name} Chests in Inventory.")
                openables = [
                    Item.from_id(self.database, itemid)
                    for itemid in chests
                ]
            elif "Lootbag" in lb_name:
                bags = Inventory(
                    self.database, message.author
                ).from_name(lb_name)
                if not bags:
                    raise ValueError(f"No {lb_name} in Inventory.")
                openables = [
                    Item.from_id(self.database, itemid)
                    for itemid in bags
                ]
            else:
                itemid = int(args[0], 16)
                openable = Inventory(
                    self.database, message.author
                ).from_id(itemid)
                if openable:
                    openable = Item.from_id(self.database, itemid)
                openables = [openable]
        except (ValueError, ZeroDivisionError):
            openables = []
        return openables

    async def __open_handle_rewards(
        self, message: Message,
        openables: List[Chest]
    ) -> str:
        chips = sum(
            chest.chips
            for chest in openables
        )
        Profile(self.database, message.author).credit(chips)
        loot_model = Loots(self.database, message.author)
        earned = loot_model.get()["earned"]
        loot_model.update(
            earned=(earned + chips)
        )
        content = f"You have recieved **{chips}** {self.chip_emoji}."
        items = []
        for openable in openables:
            if openable.name == "Legendary Chest":
                item = openable.get_random_collectible(self.database)
                if item:
                    items.append(item)
            elif openable.category == 'Lootbag':
                res = openable.get_random_items(self.database)
                if res:
                    items.extend(res)
        if items:
            item_str = '\n'.join(
                f"**『{item.emoji}』 {item}**"
                for item in items
            )
            content += f"\nAnd woah, you also got:\n{item_str}"
        inv = Inventory(self.database, message.author)
        for item in items:
            inv.save(
                int(item.itemid, 16)
            )
        inv.delete([
            int(openable.itemid, 16)
            for openable in openables
        ])
        quant_str = ''
        if len(openables) > 1:
            quant_str = f"x{len(openables)} "
        await message.channel.send(
            embed=get_embed(
                content,
                title=f"Opened {quant_str}{openables[0].name}"
            )
        )
