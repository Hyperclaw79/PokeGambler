"""
Trade Commands Module
"""

# pylint: disable=unused-argument, too-many-locals

from ..base.items import Item, Chest
from ..base.models import Inventory, Loots, Profile
from ..helpers.utils import get_embed
from .basecommand import (
    Commands, alias, model
)


class TradeCommands(Commands):
    """
    Commands that deal with the trade system of PokeGambler.
    Shop related commands fall under this category as well.
    """

    @model([Loots, Profile, Chest, Inventory])
    @alias("chest")
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
        if str(message.author.id) not in chest.description:
            print(chest.description)
            await message.channel.send(
                embed=get_embed(
                    "That's not your own chest.",
                    embed_type="error",
                    title="Invalid Chest ID"
                )
            )
            return
        chips = chest.chips
        profile = Profile(self.database, message.author)
        data = profile.get()
        won_chips = data["won_chips"]
        balance = data["balance"]
        profile.update(
            won_chips=(won_chips + chips),
            balance=(balance + chips)
        )
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
    @alias('item')
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

        # pylint: disable=no-member

        if not args:
            return
        try:
            itemid = int(args[0], 16)
        except (ValueError, ZeroDivisionError):
            await message.channel.send(
                embed=get_embed(
                    "That doesn't seems like a valid Item ID.",
                    embed_type="error",
                    title="Invalid Item ID"
                )
            )
            return
        item = Item.from_id(self.database, itemid)
        if not item:
            await message.channel.send(
                embed=get_embed(
                    "Could not find any item with the given ID.",
                    embed_type="error",
                    title="Item Does Not Exist"
                )
            )
            return
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
        id_str = '\n'.join(ids) if ids else "You have **0** of those."
        await message.channel.send(
            embed=get_embed(
                f'**{item_name}**\n{id_str}',
                title=f"{message.author.name}'s Item IDs"
            )
        )
