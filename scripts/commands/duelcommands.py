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

Gambling Commands Module
"""

# pylint: disable=too-few-public-methods, too-many-locals, unused-argument

from __future__ import annotations
import asyncio
from collections import namedtuple
import random
import re
from typing import Dict, List, Optional, TYPE_CHECKING
from cachetools import TTLCache, cached

import discord

from ..base.items import Gladiator, Item
from ..base.models import (
    Blacklist, DuelActionsModel, Inventory, Profiles, Duels
)
from ..base.views import ConfirmView, SelectView
from ..base.modals import CallbackReplyModal
from ..helpers.checks import user_check
from ..helpers.imageclasses import GladitorMatchHandler
from ..helpers.utils import (
    dedent, get_embed,
    img2file, wait_for, dm_send
)
from ..helpers.validators import (
    ItemNameValidator, MinValidator,
    RegexValidator
)
from .basecommand import (
    Commands, alias, autocomplete, check_completion,
    cooldown, model, needs_ticket, suggest_actions
)

if TYPE_CHECKING:
    from bot import PokeGambler
    from discord import Message, Member


class DuelActions:
    """
    Holder class for different types of duel attacks.
    """
    def __init__(self, ctx: PokeGambler):
        self.ctx = ctx
        self.refresh()
        if not self.normal or not self.crit:
            self.normal = [
                "<g1> kicks <g2> to the ground.",
                "<g1> pokes <g2> in the eye.",
                "<g1> punches <g2> in the face.",
                "<g1> cuts <g2> with a kitchen knife.",
                "<g1> stikes <g2> from above.",
                "<g1> trips <g2> with finesse.",
                "<g1> bashes <g2> with force."
            ]
            self.crit = [
                "<g1> releases a charged 🅴🅽🅴🆁🅶🆈 🆁🅰🆈.",
                "<g1> infuses weapon with mana and unleashes\n"
                "🅴🅻🅴🅼🅴🅽🆃🅰🅻 🆂🆃🆁🅸🅺🅴.",
                "<g1> carries out a 🅵🅻🆄🆁🆁🆈 of 🆂🆃🆁🅸🅺🅴🆂.",
                "<g1> cracks <g2>'s armor with\n"
                "🅰🆁🅼🅾🆁 🅿🅴🅽🅴🆃🆁🅰🆃🅸🅾🅽.",
                "<g1> aims for vitals and makes <g2> 🅱🅻🅴🅴🅳."
            ]
            User = namedtuple("User", ['id'])
            owner = User(id=ctx.owner_id)
            for key, val in {
                "Normal": self.normal,
                "Critical": self.crit
            }.items():
                for action in val:
                    DuelActionsModel(
                        owner,
                        action, key
                    ).save()

    def get(self, damage: int) -> str:
        """
        Returns a random attack based on damage.
        """
        if damage >= 300:
            return "<g1> uses 🅳🅸🆅🅸🅽🅴 🆆🆁🅰🆃🅷 and finishes off <g2>."
        if damage > 150:
            return random.choice(self.crit)
        return random.choice(self.normal)

    def refresh(self):
        """
        Populates DuelActions class with all actions in DB.
        """
        self.normal = []
        self.crit = []
        for action in DuelActionsModel.get_actions():
            if action["level"] == "Normal":
                self.normal.append(action["action"])
            else:
                self.crit.append(action["action"])


@cached(
    cache=TTLCache(maxsize=10, ttl=360),
    key=lambda intc: intc.user.id
)
def get_gladiators(
    interaction: discord.Interaction
) -> List[Dict[str, str]]:
    """
    Returns list of user owned Gladiator.

    :param interaction: The interaction which triggered this command.
    :type interaction: :class:`discord.Interaction`
    :return: List of user owned Gladiator.
    :rtype: List[Dict[str, str]]
    """
    author = interaction.user
    glads, _ = Inventory(author).get(category='Gladiator')
    return [
        {
            "name": glad['name'],
            "value": glad['_id']
        }
        for glad in glads['Gladiator']
    ]


class DuelCommands(Commands):
    """
    Commands which are related to 1v1 Duel matches.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.duelactions = DuelActions(self.ctx)

    @alias("action+")
    @model([DuelActionsModel, Profiles])
    @check_completion
    async def cmd_create_action(self, message: Message, **kwargs):
        """
        :param message: The message that triggered this command.
        :type message: :class:`discord.Message`

        .. meta::
            :description: Create a custom Duel Action

        .. rubric:: Syntax
        .. code:: coffee

            /create_action

        .. rubric:: Description

        Create your own attack actions for the Duels.

        .. note::

            * Actions created will be added to the global action list.
            * Others will also get this action for their gladiator.
            * It might take a while for your action to show up.

        .. admonition:: Actions

            1. **Normal**: Damage < 150, Costs: 200 Pokechips
            2. **Critical**: Damage > 150, Costs: 300 Pokechips
        """
        levels = ["Normal", "Critical"]
        desc_info = [
            "Damage < 150, Costs: 200 Pokechips",
            "Damage >= 150, Costs: 200 Pokebonds"
        ]
        charges = ["won_chips", "pokebonds"]
        profile = Profiles(message.author)
        choice_view = SelectView(
            heading="Choose the action level",
            options={
                levels[idx]: desc_info[idx]
                for idx in range(len(levels))
            },
            check=lambda x: x.user.id == message.author.id
        )
        await dm_send(
            message, message.author,
            content="Which type of attack do you wanna create?",
            view=choice_view
        )
        await choice_view.dispatch(self)
        choice = choice_view.result
        if choice is None:
            return
        if profile.get(
            charges[levels.index(choice)]
        ) < 200:
            await self.handle_low_balance(
                message, message.author,
                is_pokebonds=bool(levels.index(choice))
            )
            return
        action_inp_msg = await dm_send(
            message, message.author,
            embed=get_embed(
                dedent(
                    """
                    Use `<g1>` and `<g2>` as placeholders for gladiator names.
                    Default formatting won't work, so use unicode characters
                    for emphasising any word.
                    Max Characters Limit: 100

                    For example:
                        ```
                        <g1> slams <g2> to the ground.
                        <g1> activates 🆅🅴🅽🅶🅴🅰🅽🅲🅴.
                        ```

                    **Mention me in the message with your action.**
                    """
                ),
                title="Enter the action message",
                color=profile.get("embed_color")
            )
        )
        reply = await wait_for(
            action_inp_msg.channel, self.ctx,
            init_msg=action_inp_msg,
            check=lambda msg: user_check(
                msg, message,
                chan=action_inp_msg.channel
            ) and msg.content,
            timeout="inf"
        )
        reply_msg = re.sub(
            fr'<@!?{self.ctx.user.id}>',
            '',
            reply.content
        ).strip()
        proceed = await RegexValidator(
            pattern=r"<g1>\s.+",
            message=message,
            on_error={
                "title": "No Gladiator 1 Placeholder",
                "description": "You need to include at "
                "least <g1> in the action.\n"
                "Please reuse the command."
            },
            dm_user=True
        ).validate(reply_msg)
        if not proceed:
            return
        action = "\n".join(reply_msg.splitlines()[:2])
        # Ensure there's only one placeholder for each gladiator.
        for placeholder in ["<g1>", "<g2>"]:
            action = action.replace(
                placeholder,
                "placeholder",
                1
            ).replace(placeholder, " ").replace(
                "placeholder",
                placeholder
            )
        DuelActionsModel(
            message.author,
            action[:100], choice
        ).save()
        await dm_send(
            message, message.author,
            embed=get_embed(
                "Successfully saved your duel action.\n"
                "Let's hope it shows up soon.",
                title="Duel Action saved",
                color=profile.get("embed_color")
            )
        )
        profile.debit(200, bonds=levels.index(choice))
        self.duelactions.refresh()

    @cooldown(300)
    @model([Blacklist, Duels, Inventory, Item, Profiles])
    @alias(["fight", "gladiator", "battle"])
    @suggest_actions([
        ("tradecommands", "shop", {"category": "Gladiator"})
    ])
    async def cmd_duel(
        self, message: Message,
        opponent: Member,
        chips: Optional[int] = 50,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param opponent: The user to duel against
        :type opponent: :class:`discord.Member`
        :param chips: Amount of Pokechips to bet on the duel.
        :type chips: Optional[int]
        :default chips: 50
        :min_value chips: 50

        .. meta::
            :description: 1v1 Gladiator duels
            :aliases: fight, gladiator, battle

        .. rubric:: Syntax
        .. code:: coffee

            /duel opponent:@player [chips:amount]

        .. rubric:: Description

        Start a 1v1 Gladiator match against any valid player.
        Cost defaults to 50 {pokechip_emoji} (minimum) if not provided.
        Both the players must own at least 1 Gladiator
        & have enough balance.

        .. tip::

            You can purchase Gladiators from the
            :class:`~scripts.base.shop.Shop`.

        .. rubric:: Examples

        * To battle user ABCD#1234 for 50 chips

        .. code:: coffee
            :force:

            /duel opponent:@ABCD#1234

        * To battle user EFGH#5678 for 50,000 chips

        .. code:: coffee
            :force:

            /duel opponent:@EFGH#5678 chips:50000
        """
        if not opponent or opponent.id == message.author.id:
            await dm_send(
                message, message.author,
                embed=get_embed(
                    "You need to mention whom you want to duel.",
                    embed_type="error",
                    title="No Player 2"
                )
            )
            return
        user_profile = Profiles(message.author)
        amount = await self.__duel_get_cost(message, user_profile, chips)
        if not amount:
            return
        gladiator1 = await self.__duel_get_gladiator(
            message, message.author, user_profile,
            **kwargs
        )
        if not gladiator1:
            return
        na_checks = [
            opponent.bot,
            Blacklist.is_blacklisted(opponent.id)
        ]
        if any(na_checks):
            reasons = [
                "Bot account",
                "Blacklisted User"
            ]
            reason = reasons[
                na_checks.index(True)
            ]
            await dm_send(
                message, message.author,
                embed=get_embed(
                    f"You cannot challenge a **{reason}.**",
                    embed_type="error",
                    title="Invalid Opponent"
                )
            )
            return
        other_profile = Profiles(opponent)
        confirmed = await self.__duel_confirmation(
            message, opponent,
            amount, other_profile
        )
        if not confirmed:
            return
        gladiator2 = await self.__duel_get_gladiator(
            message, opponent, other_profile,
            notify=False, **kwargs
        )
        if not gladiator2:
            await message.channel.send(
                embed=get_embed(
                    f"Gladiator Match cancelled cause **{opponent.name}**"
                    " has no gladiator.",
                    embed_type="warning",
                    title="Duel cancelled."
                )
            )
            return
        proceed = await self.__duel_proceed(
            message, opponent, other_profile,
            gladiator2, amount
        )
        if proceed:
            glads = [gladiator1, gladiator2]
            profiles = [user_profile, other_profile]
            await self.__duel_play(
                message, glads,
                profiles, amount
            )

    @autocomplete({
        'gladiator': get_gladiators
    })
    @needs_ticket("Gladiator Nickname Change")
    @check_completion
    @model(Inventory)
    # pylint: disable=no-self-use
    async def cmd_gladnick(
        self, message: Message,
        gladiator: str, **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param gladiator: The ID of gladiator whose nickname should be changed.
        :type gladiator: str
        :autocomplete gladiator: True

        .. meta::
            :description: Rename your gladiator

        .. rubric:: Syntax
        .. code:: coffee

            /gladnick

        .. rubric:: Description

        You can rename your gladiator using a
        **Gladiator Name Change** ticket.

        .. tip::

            You can buy a ticket from the :class:`~scripts.base.shop.Shop`.

        .. seealso::

            :class:`~scripts.base.items.Gladiator`

        """
        profile = Profiles(message.author)
        glad = Item.from_id(gladiator)

        async def callback(modal):
            if not modal.results:
                return
            new_nick = modal.results[0]
            proceed = await ItemNameValidator(
                message=message,
                on_error={
                    "title": "Invalid Nickname",
                    "description": "That name is not allowed, keep it simple."
                },
                dm_user=True
            ).validate(new_nick)
            if not proceed:
                return
            new_name = re.sub(
                r"[^\x00-\x7F]+", "",
                new_nick[:10].title()
            ).strip()
            # pylint: disable=no-member
            glad.rename(new_name)
            inv = Inventory(message.author)
            tickets = kwargs["tickets"]
            inv.delete(tickets[0], quantity=1)
            return {
                "embed": get_embed(
                    f"Successfully renamed your Gladiator to **{glad}**.",
                    title="Rename Complete",
                    color=profile.get("embed_color")
                )
            }

        modal = CallbackReplyModal(
            callback=callback,
            title="Gladiator Nickname Change",
        )
        modal.add_short(
            "Enter new nickname.",
            placeholder="Use a sensible name (Max 10 chars)"
        )
        await message.response.send_modal(modal)
        await modal.wait()

    async def __duel_confirmation(
        self, message: Message,
        user: Member, amount: int,
        user_profile: Profiles
    ) -> bool:
        confirm_view = ConfirmView(
            check=lambda intcn: intcn.user.id == user.id,
            timeout=60
        )
        await message.channel.send(
            content=f"Hey {user.mention}, you have been invited "
            f"to a Gladiator match by **{message.author.name}**",
            embed=get_embed(
                f"Bet Amount: **{amount}** {self.chip_emoji}",
                title="Do you accept?",
                color=user_profile.get("embed_color")
            ),
            view=confirm_view
        )
        await confirm_view.dispatch(self)
        return confirm_view.value is not None

    def __duel_get_action(
        self, glads: List[Gladiator],
        damages: List[int]
    ) -> str:
        return "\n".join(
            self.duelactions.get(damages[idx]).replace(
                '<g1>', glads[idx].name
            ).replace(
                '<g2>', glads[1 - idx].name
            ) + f'\n<Damage: {damages[idx]}>'
            for idx in range(2)
        )

    async def __duel_get_cost(
        self, message: Message,
        user_profile: Profiles,
        chips: int = None
    ) -> int:
        if chips:
            amount = await MinValidator(
                50, message=message
            ).cleaned(chips)
            if not amount:
                return 0
        else:
            amount = 50
            if user_profile.get('balance') >= 50:
                await dm_send(
                    message, message.author,
                    embed=get_embed(
                        "Amount of chips not specified, "
                        "will be set to **50**.",
                        embed_type="warning",
                        title="No Pokechips count"
                    )
                )
        if user_profile.get('balance') < amount:
            await self.handle_low_balance(
                message, message.author
            )
            return 0
        return amount

    async def __duel_get_gladiator(
        self, message: Message, user: Member,
        profile: Profiles, notify: bool = True,
        **kwargs
    ) -> Gladiator:
        inv = Inventory(user)
        glads, _ = inv.get(category='Gladiator')
        if not glads:
            if notify:
                await dm_send(
                    message, message.author,
                    embed=get_embed(
                        "You do not own any Gladitor.\n"
                        "Buy one form the Shop first.",
                        embed_type="error",
                        title="No Gladiators Found"
                    ),
                    view=kwargs.get("view")
                )
            return None
        available = []
        for glad in glads['Gladiator']:
            gld = Item.from_id(glad['_id'])
            available.append(gld)
        if len(available) > 1:
            choices_view = SelectView(
                heading="Choose a gladiator:",
                options={
                    gld: gld.description.split(' as')[0]
                    for gld in available
                },
                no_response=True,
                check=lambda x: x.user.id == message.author.id
            )
            await dm_send(
                message, user,
                content="Whom do you wanna fight with?",
                view=choices_view
            )
            await choices_view.dispatch(self)
            gladiator = choices_view.result
            if gladiator is None:
                gladiator = available[0]
        else:
            gladiator = available[0]
        await dm_send(
            message, user,
            embed=get_embed(
                f"Successfully chosen 『**{gladiator}**』"
                "for this command/match.",
                title="Gladiator Confirmed",
                color=profile.get("embed_color")
            )
        )
        gladiator.image = await gladiator.get_image(self.ctx.sess)
        gladiator.owner = user
        return gladiator

    async def __duel_play(
        self, message: Message,
        glads: List[Gladiator],
        profiles: List[Profiles],
        amount: int
    ):
        dmg_dict = {
            usr.user.id: []
            for usr in profiles
        }
        players = [
            prof.user
            for prof in profiles
        ]
        if not self.duelactions.normal:
            self.duelactions.refresh()
        gladhandler = GladitorMatchHandler(self.ctx.assets_path)
        base, thread = await self.__duel_start(message, gladhandler, glads)
        if base is None:
            return
        emb = discord.Embed()
        adjust = 1
        for idx, (img, dmg1, dmg2) in enumerate(gladhandler.get(glads)):
            if dmg1 == dmg2 == 0:
                adjust -= 1
                continue
            dmg_dict[players[0].id].append(dmg1)
            dmg_dict[players[1].id].append(dmg2)
            round_fl = img2file(img, f"duel_{idx}.jpg")
            action = self.__duel_get_action(glads, [dmg1, dmg2])
            emb.add_field(
                name=f"Round {idx + adjust}",
                value=f"```md\n{dedent(action)}\n```",
                inline=False
            )
            emb.set_image(url=f"attachment://duel_{idx}.jpg")
            await asyncio.sleep(3.0)
            await thread.send(
                embed=emb, file=round_fl
            )
        winner = max(
            profiles,
            key=lambda x: sum(dmg_dict[x.user.id])
        )
        other = [
            prof
            for prof in profiles
            if prof.user.id != winner.user.id
        ][0]
        winner_glad = glads[profiles.index(winner)]
        other_glad = glads[profiles.index(other)]
        await thread.send(
            embed=get_embed(
                f"**{winner.name}**'s『{winner_glad}』"
                f"destroyed **{other.name}**'s『{other_glad}』",
                title=f"💀 Match won by **{winner.name}**!",
                no_icon=True,
                color=winner.get("embed_color")
            )
        )
        winner.credit(amount)
        other.debit(amount)
        Duels(
            players[0], glads[0].name,
            players[1], glads[1].name,
            str(winner.user.id), amount
        ).save()
        await thread.edit(
            archived=True,
            locked=True
        )

    @staticmethod
    async def __duel_proceed(
        message: Message, user: Member,
        profile: Profiles, gladiator: Gladiator,
        cost: int
    ) -> bool:
        if profile.get("balance") < cost:
            await message.channel.send(
                embed=get_embed(
                    f"Match cancelled cause **{user.name}** can't afford it.",
                    embed_type="error",
                    title="Insufficient Balance"
                )
            )
            return False
        if not gladiator:
            await message.channel.send(
                embed=get_embed(
                    f"Match cancelled cause **{user.name}** has no gladiator.",
                    embed_type="error",
                    title="No Gladiator"
                )
            )
            return False
        return True

    @staticmethod
    async def __duel_start(
        message: Message,
        gladhandler: GladitorMatchHandler,
        glads: List[Gladiator]
    ) -> Message:
        fresh_emb = discord.Embed(
            title="Match Starting..."
        )
        try:
            start_fl = img2file(
                next(gladhandler.get(glads))[0],
                "start.jpg"
            )
            fresh_emb.set_image(
                url="attachment://start.jpg"
            )
            base = await message.channel.send(
                content=" vs ".join(
                    glad.owner.mention
                    for glad in glads
                ),
                embed=fresh_emb,
                file=start_fl
            )
            thread = await message.channel.create_thread(
                name=" vs ".join(
                    f"{glad.owner.name}『{glad}』"
                    for glad in glads
                ),
                message=base
            )
            return base, thread
        except StopIteration:
            await message.channel.send(
                embed=get_embed(
                    "Something went wrong.",
                    embed_type="error",
                    title="Could Not Start Duel"
                )
            )
            return None, None
