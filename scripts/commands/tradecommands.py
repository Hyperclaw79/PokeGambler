"""
Trade Commands Module
"""

# pylint: disable=unused-argument, too-many-locals

from ..base.items import Item
from ..helpers.utils import get_embed
from .basecommand import Commands, alias, model


class TradeCommands(Commands):
    """
    Commands that deal with the trade system of PokeGambler.
    Shop related commands fall under this category as well.
    """

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
