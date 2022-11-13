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

Control Commands Module
"""

# pylint: disable=unused-argument

from __future__ import annotations

import json
import time
from io import BytesIO
from typing import (
    TYPE_CHECKING, List, Optional,
    Tuple, Type, Union
)

import discord

from ..base.items import Item
from ..base.models import (
    Checkpoints, CommandData, Minigame,
    Model, UnlockedModel
)
from ..base.views import SelectView
from ..helpers.utils import (
    get_embed, get_enum_embed,
    get_modules, get_modules_from_path
)
from .basecommand import (
    defer, model, override_docs,
    owner_only, no_log, alias, Commands
)

if TYPE_CHECKING:
    from discord import Message


class ControlCommands(Commands):
    '''
    Commands that help in controlling PokeGambler.

    .. note::

        Only the Owners have access to these commands.
    '''

    # pylint: disable=too-many-locals
    @owner_only
    @defer
    @no_log
    async def cmd_activity_trend(self, message: Message, **kwargs):
        """Activity Trend command

        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`

        .. meta::
            :description: Check the Activity Trend for PokeGambler.

        .. rubric:: Syntax
        .. code:: coffee

            /activity_trend

        .. rubric:: Description

        ``👑 Owner Command``
        Tester command for the activity trend.

        .. rubric:: Examples

        * To check the activity trend:

        .. code:: coffee
            :force:

            /activity_trend
        """
        import pandas as pd  # pylint: disable=import-outside-toplevel

        records = Checkpoints.get_checkpoints()
        if not records:
            await message.reply(
                embed=get_embed(
                    title="0 Checkpoints",
                    content="No checkpoints have been created yet.",
                    embed_type="warning"
                )
            )
            return
        dframe = pd.DataFrame(records)
        dframe['created_on'] = dframe['created_on'].map(lambda x: x.date())
        dframe.index = dframe.pop('created_on')
        colors = ['r', 'g', 'b', 'y']
        embeds = []
        files = []
        columns = dframe.columns
        dframe = dframe.reindex(
            pd.date_range(
                dframe.index.min(),
                dframe.index.max() + pd.Timedelta(days=1)
            ),
            fill_value=0
        )
        for record in CommandData.trend(
            include_os=False,
            start_time=dframe.index[0].to_pydatetime(),
            end_time=dframe.index[-1].to_pydatetime()
        ):
            dframe.loc[record['date'], 'num_commands_unofficial'] = record['count']
        dframe[['num_commands_unofficial']] = dframe[
            ['num_commands_unofficial']
        ].fillna(0).astype(int)
        dframe = dframe[dframe['num_commands'] > 0]
        for column, color in zip(columns, colors):
            byio = BytesIO()
            if column == 'num_commands':
                axes = dframe[[column, 'num_commands_unofficial']].plot(
                    subplots=True,
                    layout=(2, 1)
                )
                axes[0, 0].set_title('All Commands till Date')
                axes[1, 0].set_title('Unofficial Commands Trend')
                axes[1, 0].xaxis.set_visible(False)
                fig = axes[0, 0].get_figure()
                fig.tight_layout()
                fig.savefig(byio)
            else:
                axes = dframe[[column]].plot(color=color)
                axes.xaxis.set_visible(False)
                axes.figure.savefig(byio)
            byio.seek(0)
            d_fl = discord.File(byio, f"{column}.jpeg")
            emb = discord.Embed(
                title=f"{column.split('_')[1].title()} Activity Trend",
                description="",
                color=discord.Colour.dark_theme()
            )
            embeds.append(emb)
            files.append(d_fl)
        await self.paginate(message, embeds, files)

    # pylint: disable=too-many-arguments
    @owner_only
    @no_log
    @model(CommandData)
    @alias('cmd_hist')
    async def cmd_command_history(
        self, message: Message,
        limit: Optional[int] = 5,
        admin_cmd: Optional[bool] = None,
        user: Optional[discord.Member] = None,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param limit: The number of commands to show.
        :type limit: Optional[int]
        :default limit: 5
        :min_value limit: 1
        :max_value limit: 50
        :param user: The user to show commands for.
        :type user: Optional[:class:`discord.Member`]
        :default user: None
        :param admin_cmd: Whether or not to show admin commands.
        :type admin_cmd: Optional[bool]
        :default admin_cmd: None

        .. meta::
            :description: Retrieves the latest command history based \
                on provided filters.
            :aliases: cmd_hist

        .. rubric:: Syntax
        .. code:: coffee

            /command_history [limit:number] [user:@User] [admin_cmd:True/False]

        .. rubric:: Description

        ``👑 Owner Command``
        Retrieves the latest command history based on provided kwargs.
        Defaults to a limit of 5 commands.
        Filter must be comma-separated key value pairs of format key:value.

        .. rubric:: Examples

        * To retrieve the 10 latest commands

        .. code:: coffee
            :force:

            /cmd_hist limit:10

        * To retrieve latest commands used by admins

        .. code:: coffee
            :force:

            /cmd_hist admin_cmd:True
        """
        filter_ = {}
        if user is not None:
            filter_["user_id"] = str(user.id)
        if admin_cmd is not None:
            filter_["admin_cmd"] = admin_cmd
        history = CommandData.history(limit=limit, **filter_)
        if not history:
            await message.reply(
                embed=get_embed(
                    "No commands logged yet."
                )
            )
            return
        embeds = [self.__cmd_hist_parse(cmd) for cmd in history]
        await self.paginate(message, embeds)

    # pylint: disable=no-self-use
    @owner_only
    @no_log
    async def cmd_export_items(
        self, message: Message,
        pretty: Optional[int] = 3,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param pretty: The number of spaces to indent the JSON.
        :type pretty: Optional[int]
        :default pretty: 3
        :min_value pretty: 1
        :max_value pretty: 4

        .. meta::
            :description: Exports the :class:`~scripts.base.items.Item` \
                Collection as JSON.

        .. rubric:: Syntax
        .. code:: coffee

            /export_items [pretty:level]

        .. rubric:: Description

        ``👑 Owner Command``
        Exports the dynamicall_y created items from the database as JSON.
        The JSON is uploaded as a file in the channel.
        The pretty option can be used to provide indentation level.

        .. rubric:: Examples

        * To export the items as a JSON file

        .. code:: coffee
            :force:

            /export_items

        * To see a pretty version of items JSON file

        .. code:: coffee
            :force:

            /export_items pretty:3
        """
        items = Item.get_unique_items()
        for item in items:
            item.pop("created_on", None)
        jsonified = json.dumps(
            items,
            indent=pretty,
            sort_keys=False
        )
        byio = BytesIO()
        byio.write(jsonified.encode())
        byio.seek(0)
        export_fl = discord.File(byio, "items.json")
        await message.reply(file=export_fl)

    # pylint: disable=no-self-use
    @owner_only
    @no_log
    async def cmd_import_items(
        self, message: Message,
        items_json: discord.Attachment,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param items_json: The JSON file to import.
        :type items_json: :class:`discord.Attachment`

        .. meta::
            :description: Imports the items from a JSON file.

        .. rubric:: Syntax
        .. code:: coffee

            /import_items

        .. rubric:: Description

        ``👑 Owner Command``
        Waits for JSON file attachment and loads the data
        into the Items collection.

        .. warning::
            Do not import :class:`~scripts.base.items.Rewardbox` using this.
        """
        data_bytes = await items_json.read()
        data = json.loads(data_bytes.decode())
        Item.insert_many(data)
        await message.add_reaction("👍")

    @owner_only
    @no_log
    async def cmd_latest(
        self, message: Message,
        limit: Optional[int] = 5,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param limit: The number of documents to show.
        :type limit: Optional[int]
        :default limit: 5
        :min_value limit: 1
        :max_value limit: 50

        .. meta::
            :description: Retrieves the latest documents \
                from a Collection.

        .. rubric:: Syntax
        .. code:: coffee

            /latest [limit:number]

        .. rubric:: Description

        ``👑 Owner Command``
        Retrieves the latest documents from a Collection.
        Defaults to a limit of 5 documents.
        """
        locked, unlocked = self.__get_collections()
        cltn = await self.__get_model_view(
            message, (locked + unlocked)
        )
        if not cltn:
            return
        documents = cltn.latest(limit=limit)
        if not documents:
            await message.reply(
                embed=get_embed(
                    title="No documents found.",
                    embed_type="warning"
                )
            )
            return
        embeds = []
        for doc in documents:
            emb = get_embed(
                title=f"Latest entries from {cltn.__name__}"
            )
            for key, val in doc.items():
                if key in [
                    "background", "asset_url"
                ]:
                    if val:
                        emb.set_thumbnail(url=val)
                    continue
                emb.add_field(
                    name=key,
                    value=str(val)
                )
            embeds.append(emb)
        await self.paginate(message, embeds)

    @owner_only
    @no_log
    @alias('prg_tbl')
    async def cmd_purge_tables(
        self, message: Message,
        all_: Optional[bool] = False,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param all_: Whether to purge all tables.
        :type all_: Optional[bool]
        :default all_: False

        .. meta::
            :description: Purges the tables in the database.
            :aliases: prg_tbl

        .. rubric:: Syntax
        .. code:: coffee

            /purge_tables [all_:True/False]

        .. rubric:: Description

        ``👑 Owner Command``
        Purges the tables in the database.

        .. rubric:: Examples

        * To choose a table to purge

        .. code:: coffee
            :force:

            /purge_tables

        * To purge all the tables

        .. code:: coffee
            :force:

            /purge_tables all_:True
        """
        locked, unlocked = self.__get_collections()
        if all_:
            collections = locked + unlocked
        else:
            cltn = await self.__get_model_view(
                message, (locked + unlocked)
            )
            if not cltn:
                return
            collections = [cltn]
        for cls in collections:
            purger = (
                cls.purge if cls in locked
                else cls.reset_all
            )
            purger()
        await message.add_reaction("👍")

    @override_docs(
        lambda docs: docs.replace(
            "%MODULES%",
            get_modules_from_path(__file__)
        )
    )
    @owner_only
    @no_log
    async def cmd_reload(
        self, message: Message,
        module: str,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param module: The module to reload.
        :type module: str
        :choices module: %MODULES%

        .. meta::
            :description: Reloads a command module.

        .. rubric:: Syntax
        .. code:: coffee

            /reload module:name

        .. rubric:: Description

        ``👑 Owner Command``
        Hot reloads a command module without having to restart.

        .. rubric:: Examples

        * To reload the Normalcommands module

        .. code:: coffee
            :force:

            /reload module:normal
        """
        module = module.lower()
        possible_modules = self.__possible_modules
        if module not in possible_modules:
            embed = get_enum_embed(
                possible_modules,
                title="List of reloadable modules"
            )
            await message.reply(embed=embed)
        else:
            self.ctx.load_commands(module, reload_module=True)
            await self.ctx.slash_sync()
            await message.reply(
                embed=get_embed(f"Successfully reloaded {module}.")
            )

    @owner_only
    @no_log
    async def cmd_timeit(
        self, message: Message,
        command: str,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param command: The command to time.
        :type command: str

        .. meta::
            :description: Executes a command and displays time taken to run it.

        .. rubric:: Syntax
        .. code:: coffee

            /timeit command:name

        .. rubric:: Description

        ``👑 Owner Command``
        A utility commands that is used for timing other commands.

        .. rubric:: Examples

        * To time the leaderboard command

        .. code:: coffee
            :force:

            /timeit command:leaderboard
        """
        modules = get_modules(self.ctx)
        cmd = command.lower()
        for module in modules:
            command = getattr(
                module,
                f"cmd_{cmd}",
                None
            )
            if command:
                break
        start = time.time()
        await command(message=message, **kwargs)
        end = time.time()
        tot = round(end - start, 2)
        await message.reply(
            embed=get_embed(
                f"Command `/{cmd}` "
                f"took **{tot}** seconds to execute."
            )
        )

    @property
    def __possible_modules(self):
        return [
            cmd.replace("commands", "")
            for cmd in dir(self.ctx)
            if all([
                not cmd.startswith("_"),
                cmd.endswith("commands"),
                cmd != "load_commands"
            ])
        ]

    def __cmd_hist_parse(self, cmd):
        user = self.ctx.get_user(int(cmd["user_id"]))
        is_admin = cmd["admin_cmd"]
        channel = cmd["channel"]["name"]
        guild = cmd["guild"]["name"]
        timestamp = cmd["used_at"].strftime("%Y-%m-%d %H:%M:%S")
        emb = discord.Embed(
            title="Command History",
            description='\u200B'
        )
        emb.add_field(
            name="Command",
            value=f'**/{cmd["command"]}**',
            inline=True
        )
        emb.add_field(
            name="Used By",
            value=user,
            inline=True
        )
        emb.add_field(
            name="Is Admin",
            value=is_admin,
            inline=True
        )
        emb.add_field(
            name="Channel",
            value=channel,
            inline=True
        )
        emb.add_field(
            name="Guild",
            value=guild,
            inline=True
        )
        emb.add_field(
            name="Args",
            value=cmd["args"] or "None",
            inline=True
        )
        if cmd["kwargs"]:
            kwarg_json = json.dumps(cmd["kwargs"], indent=3)
            emb.add_field(
                name="Kwargs",
                value=f'```json\n{kwarg_json}\n```',
                inline=True
            )
        emb.set_footer(
            text=f"Command was used at {timestamp}."
        )
        return emb

    @staticmethod
    def __get_collections() -> Tuple[List]:
        locked = [
            cls
            for cls in Model.__subclasses__()
            if cls not in (UnlockedModel, Minigame)
        ] + [Item]
        unlocked = UnlockedModel.__subclasses__()
        locked.extend(Minigame.__subclasses__())
        return locked, unlocked

    @staticmethod
    async def __get_model_view(
        message: Message,
        models: List[Union[Type[Item], Type[Model]]],
        content: str = None
    ) -> Union[Type[Item], Type[Model]]:
        choices_view = SelectView(
            heading="Select a Collection",
            options={
                opt: ""
                for opt in sorted(
                    models,
                    key=lambda x: x.__name__
                )
            },
            serializer=lambda x: x.__name__
        )
        await message.reply(
            "Which table do you wanna select?",
            view=choices_view
        )
        await choices_view.wait()
        return choices_view.result
