"""
Trade Commands Module
"""

# pylint: disable=unused-argument, too-many-locals

from ..base.items import Item, Chest
from ..base.models import Loots, Profile
from ..helpers.utils import get_embed
from .basecommand import Commands, alias, model


class TradeCommands(Commands):
    """
    Commands that deal with the trade system of PokeGambler.
    Shop related commands fall under this category as well.
    """

    @model([Loots, Profile, Chest])
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
                content += f"\nAnd woah, you also got a **[{item.emoji}] {item}**!"
            # Add logic for collectible in inventory.
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
        """Check the detials of a PokeGambler Item.
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
