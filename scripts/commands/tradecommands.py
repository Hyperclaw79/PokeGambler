"""
Trade Commands Module
"""

# pylint: disable=unused-argument, too-many-locals

import asyncio
from datetime import datetime

from ..base.items import Item, Chest
from ..base.models import Inventory, Loots, Profile
from ..base.shop import Shop, TradebleItem

from ..helpers.utils import (
    dedent, get_embed, get_formatted_time
)

from .basecommand import (
    Commands, alias, dealer_only,
    model, ensure_item, no_thumb
)


class TradeCommands(Commands):
    """
    Commands that deal with the trade system of PokeGambler.
    Shop related commands fall under this category as well.
    """

    def __get_shop_page(self, args, categories):
        catog = categories[Shop.alias_map[args[0].title()]]
        if Shop.alias_map[args[0].title()] in [
                "Tradables", "Consumables", "Gladiators"
            ]:
            Shop.refresh_tradables(self.database)
        if len(catog.items) < 1:
            emb = get_embed(
                    f"`{catog.name} Shop` seems to be empty right now.\n"
                    "Please try again later.",
                    embed_type="warning",
                    title="No items found",
                    thumbnail="https://raw.githubusercontent.com/twitter/"
                    f"twemoji/master/assets/72x72/{ord(catog.emoji):x}.png"
                )
        else:
            emb = get_embed(
                    f"**To buy any item, use `{self.ctx.prefix}buy itemid`**",
                    title=f"{catog} Shop",
                    no_icon=True
                )
            for item in catog.items:
                itemid = f"{item.itemid:0>8X}" if isinstance(
                        item.itemid, int
                    ) else item.itemid
                emb.add_field(
                        name=f"『{itemid}』 _{item}_ "
                        f"{item.price:,} <:pokechip:840469159242760203>",
                        value=f"```\n{item.description}\n```",
                        inline=False
                    )
            # pylint: disable=undefined-loop-variable
            emb.set_footer(text=f"Example:『{self.ctx.prefix}buy {itemid}』")
        return emb

    @model([Loots, Profile, Chest, Inventory])
    @alias("chest")
    @no_thumb
    async def cmd_open(self, message, args=None, **kwargs):
        """Opens a PokeGambler treasure chest.
        $```scss
        {command_prefix}open chest_id
        ```$

        @Opens a treasure chest that you own.
        There are 3 different chests and scale with your tier.
        Here's a drop table:
        ```py
        ╔══════╦═══════════╦═══════════╦══════════════╗
        ║ Tier ║   Chest   ║ Drop Rate ║  Pokechips   ║
        ╠══════╬═══════════╬═══════════╬══════════════╣
        ║   1  ║  Common   ║    66%    ║   34 - 191   ║
        ║   2  ║   Gold    ║    25%    ║  192 - 1110  ║
        ║   3  ║ Legendary ║     9%    ║ 1111 - 10000 ║
        ╚══════╩═══════════╩═══════════╩══════════════╝
        ```@

        ~To open a chest with ID 0000FFFF:
            ```
            {command_prefix}open 0000FFFF
            ```~
        """
        if not args:
            return
        try:
            itemid = int(args[0], 16)
            chest = Chest.from_id(self.database, itemid)
        except (ValueError, ZeroDivisionError):
            chest = None
        if not chest:
            await message.channel.send(
                embed=get_embed(
                    "Make sure you actually own this chest.",
                    embed_type="error",
                    title="Invalid Chest ID"
                )
            )
            return
        if not (
            str(message.author.id) in chest.description
            or Inventory(
                self.database, message.author
            ).from_id(itemid)
        ):
            await message.channel.send(
                embed=get_embed(
                    "That's not your own chest.",
                    embed_type="error",
                    title="Invalid Chest ID"
                )
            )
            return
        chips = chest.chips
        Profile(self.database, message.author).credit(chips)
        loot_model = Loots(self.database, message.author)
        earned = loot_model.get()["earned"]
        loot_model.update(
            earned=(earned + chips)
        )
        content = f"You have recieved **{chips}** <:pokechip:840469159242760203>."
        if chest.name == "Legendary Chest":
            item = chest.get_random_collectible(self.database)
            if item:
                content += f"\nAnd woah, you also got a **『{item.emoji}』 {item}**!"
                Inventory(self.database, message.author).save(item.itemid)
        chest.delete(self.database)
        await message.channel.send(
            embed=get_embed(
                content,
                title=f"Opened a {chest.name}"
            )
        )

    @model(Item)
    @ensure_item
    @alias(['item', 'detail'])
    async def cmd_details(self, message, args=None, **kwargs):
        """Check the details of a PokeGambler Item.
        $```scss
        {command_prefix}details chest_id
        ```$

        @Check the details, of a PokeGambler item, like Description, Price, etc.@

        ~To check the details of an Item with ID 0000FFFF:
            ```
            {command_prefix}details 0000FFFF
            ```~
        """

        item = kwargs["item"]
        await message.channel.send(embed=item.details)

    @model(Inventory)
    @alias('inv')
    async def cmd_inventory(self, message, **kwargs):
        """Check personal inventory.
        $```scss
        {command_prefix}inventory
        ```$

        @Check your personal inventory for collected Chests, Treasures, etc.@
        """
        inv = Inventory(self.database, message.author)
        catog_dict, net_worth = inv.get(counts_only=True)
        emb = get_embed(
            "This is your personal inventory categorized according to item type.\n"
            "You can get the list of IDs for an item using "
            f"`{self.ctx.prefix}ids item_name`.\n"
            "\n> Your net worth, excluding Chests, is "
            f"**{net_worth}** <:pokechip:840469159242760203>.",
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
    async def cmd_ids(self, message, args=None, **kwargs):
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
                footer=f"Use 『{self.ctx.prefix}details itemid』for detailed view."
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
    async def cmd_shop(self, message, args=None, **kwargs):
        """Access PokeGambler Shop.
        $```scss
        {command_prefix}shop [category]
        ```$

        @Used to access the **PokeGambler Shop.**
        If no arguments are provided, a list of categories will be displayed.
        If a category is provided, list of items will be shown.

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
            ```~
        """
        categories = Shop.categories
        shop_alias = Shop.alias_map
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
            categories = {
                key: catog
                for key, catog in sorted(
                    Shop.categories.items(),
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
            emb = self.__get_shop_page(args, categories)
            embeds.append(emb)
        await self.paginate(message, embeds)

    async def cmd_buy(self, message, args=None, **kwargs):
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
        Shop.refresh_tradables(self.database)
        try:
            item = Shop.get_item(self.database, itemid)
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
                    "Given the dynamic nature of the shop, maybe it's too late.",
                    embed_type="error",
                    title="Item not in Shop"
                )
            )
            return
        status = Shop.validate(self.database, message.author, item)
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
        quant_str = f"x {quantity}" if isinstance(item, TradebleItem) else ''
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
        await message.channel.send(
            embed=get_embed(
                f"Successfully purchased **{item}**{quant_str}.\n"
                "Your account has been debited: "
                f"**{item.price * quantity}** <:pokechip:840469159242760203>",
                title="Success"
            )
        )

    @model([Profile, Item])
    async def cmd_sell(self, message, args=None, **kwargs):
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
        except ValueError: # Item Name
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
        Profile(self.database, message.author).credit(
            new_item.price * quantity
        )
        Shop.refresh_tradables(self.database)
        await message.channel.send(
            embed=get_embed(
                f"Succesfully sold `{deleted}` of your listed item(s).\n"
                "Your account has been credited: "
                f"**{new_item.price * quantity}** <:pokechip:840469159242760203>",
                title="Item(s) Sold"
            )
        )

    async def cmd_boosts(self, message, **kwargs):
        """Check active boosts.
        $```scss
        {command_prefix}boosts
        ```$

        @Check your active purchased boosts.@
        """
        def __get_desc(boost):
            desc_str = f"{boost['description']}\nStack: {boost['stack']}"
            expires_in = (30 * 60) - (datetime.now() - boost["added_on"]).total_seconds()
            if expires_in > 0 and boost['stack'] > 0:
                expires_in = get_formatted_time(
                    expires_in, show_hours=False
                ).replace('**', '')
            else:
                expires_in = "Expired / Not Purchased Yet"
            desc_str += f"\nExpires in: {expires_in}"
            return f"```css\n{desc_str}\n```"
        boosts = self.ctx.boost_dict.get(message.author.id, None)
        if not boosts:
            await message.channel.send(
                embed=get_embed(
                    "You don't have any active boosts.",
                    title="No Boosts"
                )
            )
            return
        emb = get_embed(
            "\u200B",
            title="Active Boosts"
        )
        for val in boosts.values():
            emb.add_field(
                name=val["name"],
                value=__get_desc(val),
                inline=False
            )
        await message.channel.send(embed=emb)

    @dealer_only
    @model(Profile)
    @alias(["transfer", "pay"])
    async def cmd_give(
        self, message, args=None,
        mentions=None, **kwargs
    ):
        """Transfer credits.
        $```scss
        {command_prefix}give quantity @mention
        ```$

        @`🎲 Dealer Command`
        Transfer some of your own <:pokechip:840469159242760203> to another user.
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
        if self.database.is_blacklisted(str(mentions[0].id)):
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
        if author_prof.get()["balance"] < amount:
            await message.channel.send(
                embed=get_embed(
                    "You don't have enough <:pokechip:840469159242760203>.",
                    embed_type="error",
                    title="Low Balance"
                )
            )
            return
        author_prof.debit(amount)
        mention_prof.credit(amount)
        await message.channel.send(
            embed=get_embed(
                f"Amount transferred: **{amount}** <:pokechip:840469159242760203>"
                f"\nRecipient: **{mentions[0]}**",
                title="Transaction Successful"
            )
        )
