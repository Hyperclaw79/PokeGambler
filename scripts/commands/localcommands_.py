"""
Local Commands Module
"""

# pylint: disable=unused-argument, import-outside-toplevel, no-member

import asyncio
import sys

from .basecommand import (
    owner_only, no_log, alias, Commands
)


class LocalCommands(Commands):
    '''
    Commands that execute only on the Local PC.
    Examples: Shutdown
    '''

    @owner_only
    @no_log
    @alias(['kill', 'close', 'off'])
    async def cmd_shutdown(self, message, **kwargs):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`

        .. meta::
            :description: Closes the bot gracefully.
            :aliases: kill, close, off

        .. rubric:: Syntax
        .. code:: coffee

            {command_prefix}shutdown

        .. rubric:: Description

        ``👑 Owner Command``
        Closes the bot gracefully.
        """
        self.logger.pprint(
            "Shutdown initiated...\n"
            "Closing all running Tasks.\n"
            "Quitting gracefully.\n",
            color="yellow",
            timestamp=True
        )
        await self.ctx.sess.close()
        for task in asyncio.all_tasks():
            task.cancel()
        await self.ctx.close()
        sys.exit(0)

    @owner_only
    @no_log
    @alias("del_dm")
    async def cmd_delete_dms(self, message, **kwargs):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`

        .. meta::
            :description: Deletes messages in PokeGambler's DM with the owner.
            :aliases: del_dm

        .. rubric:: Syntax
        .. code:: coffee

            {command_prefix}delete_dms

        .. rubric:: Description

        👑 Owner Command
        Deletes messages in PokeGambler's DM with the owner.
        """
        chan = self.ctx.owner.dm_channel
        if not chan:
            chan = self.ctx.owner.create_dm()
        async for msg in chan.history():
            if msg.author.id == self.ctx.user.id:
                await msg.delete()
