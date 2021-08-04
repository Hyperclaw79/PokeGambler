"""
Gambling Commands Module
"""

# pylint: disable=too-few-public-methods, too-many-locals, unused-argument

from __future__ import annotations
import asyncio
from collections import namedtuple
import random
import re
from typing import List, Optional, TYPE_CHECKING

import discord

from ..base.items import Gladiator, Item
from ..base.models import (
    Blacklist, DuelActionsModel, Inventory, Profiles, Duels
)
from ..base.views import Confirm, SelectView
from ..helpers.checks import user_check
from ..helpers.imageclasses import GladitorMatchHandler
from ..helpers.utils import (
    dedent, get_embed,
    img2file, wait_for, dm_send
)
from ..helpers.validators import (
    MaxLengthValidator, MinValidator,
    RegexValidator
)
from .basecommand import (
    Commands, alias, check_completion,
    cooldown, model, needs_ticket, no_thumb
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
        self.normal = []
        self.crit = []
        for action in DuelActionsModel.get_actions():
            if action["level"] == "Normal":
                self.normal.append(action["action"])
            else:
                self.crit.append(action["action"])
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


class DuelCommands(Commands):
    """
    Gamble Commands are the core commands for PokeGambler.
    Currently, the only available command is the Gamble command itself.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.duelactions = DuelActions(self.ctx)

    @alias("action+")
    @model([DuelActionsModel, Profiles])
    @check_completion
    @no_thumb
    async def cmd_create_action(self, message: Message, **kwargs):
        """Create a custom Duel Action.
        $```scss
        {command_prefix}create_action
        ```$

        @Create your own attack action in the Duels.
        > *Note: Actions created will be added to the global action list.*
        > *Other will also get this action for their gladiator.*
        > *Actions are generated using RNG, so it might take a while for yours*
        > *to show up.*@
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
            await dm_send(
                message, message.author,
                embed=get_embed(
                    "You cannot afford to create that action.",
                    embed_type="error",
                    title="Insufficient Balance"
                )
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
            ),
            timeout="inf"
        )
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
        ).validate(reply.content)
        if not proceed:
            return
        action = "\n".join(reply.content.splitlines()[:2])
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
    async def cmd_duel(
        self, message: Message,
        args: Optional[List] = None,
        mentions: List[Member] = None,
        **kwargs
    ):
        """Gladiator Battler 1v1.
        $```scss
        {command_prefix}duel [chips] @player
        ```$

        @Have a 1v1 Gladiator match against any valid player.
        Cost defaults to 50 {pokechip_emoji} (minimum) if not provided.
        Both the players must own at least 1 Gladiator & have enough balance.
        You can purchase Gladiators from the shop.@

        ~To battle user ABCD#1234 for 50 chips:
            ```
            {command_prefix}duel @ABCD#1234
            ```
        To battle user EFGH#5678 for 50,000 chips:
            ```
            {command_prefix}duel @EFGH#5678 50000
            ```~
        """
        if not mentions or mentions[0].id == message.author.id:
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
        amount = await self.__duel_get_cost(message, user_profile, args)
        if not amount:
            return
        gladiator1 = await self.__duel_get_gladiator(
            message, message.author, user_profile
        )
        if not gladiator1:
            return
        user2 = mentions[0]
        na_checks = [
            user2.bot,
            Blacklist.is_blacklisted(user2.id)
        ]
        if any(na_checks):
            reasons = [
                "Bot account",
                "Blacklisted User"
            ]
            reason = reasons[
                na_checks.index(True)
            ]
            await message.channel.send(
                embed=get_embed(
                    f"You cannot challenge a **{reason}.**",
                    embed_type="error",
                    title="Invalid Opponent"
                )
            )
            return
        other_profile = Profiles(user2)
        confirmed = await self.__duel_confirmation(
            message, user2,
            amount, other_profile
        )
        if not confirmed:
            return
        gladiator2 = await self.__duel_get_gladiator(
            message, user2, other_profile,
            notify=False
        )
        if not gladiator2:
            await message.channel.send(
                embed=get_embed(
                    f"Gladiator Match cancelled cause **{user2.name}**"
                    " has no gladiator.",
                    embed_type="warning",
                    title="Duel cancelled."
                )
            )
            return
        proceed = await self.__duel_proceed(
            message, user2, other_profile,
            gladiator2, amount
        )
        if proceed:
            glads = [gladiator1, gladiator2]
            profiles = [user_profile, other_profile]
            await self.__duel_play(
                message, glads,
                profiles, amount
            )

    @needs_ticket("Gladiator Nickname Change")
    @check_completion
    @model(Inventory)
    async def cmd_gladnick(self, message: Message, **kwargs):
        """Rename your Gladiator.
        $```scss
        {command_prefix}gladnick
        ```$

        @You can rename your gladiator using a Gladiator Name Change ticket.
        The ticket can be purchased from the Consumables Shop.@
        """
        profile = Profiles(message.author)
        glad = await self.__duel_get_gladiator(
            message, message.author,
            profile
        )
        if not glad:
            return
        inp_msg = await dm_send(
            message,
            message.author,
            embed=get_embed(
                "Use a sensible name (Max 10 chars) for your gladiator.",
                title="Enter New Nickname",
                color=profile.get("embed_color")
            )
        )
        reply = await wait_for(
            inp_msg.channel, self.ctx,
            init_msg=inp_msg,
            check=lambda msg: all([
                msg.author.id == message.author.id,
                msg.channel.id == inp_msg.channel.id
            ]),
            timeout="inf"
        )
        proceed = await MaxLengthValidator(
            10,
            message=message,
            on_error={
                "title": "Invalid Nickname",
                "description": "That name is not allowed, keep it simple."
            },
            dm_user=True
        ).validate(reply.content)
        if not proceed:
            return
        new_name = re.sub(
            r"[^\x00-\x7F]+", "",
            reply.content[:10].title()
        ).strip()
        glad.rename(new_name)
        inv = Inventory(message.author)
        tickets = kwargs["tickets"]
        inv.delete(tickets[0], quantity=1)
        await dm_send(
            message,
            message.author,
            embed=get_embed(
                f"Successfully renamed your Gladiator to {new_name}.",
                title="Rename Complete",
                color=profile.get("embed_color")
            )
        )

    async def __duel_confirmation(
        self, message: Message,
        user: Member, amount: int,
        user_profile: Profiles
    ) -> bool:
        confirm_view = Confirm(
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
        args: Optional[List] = None
    ) -> int:
        if args:
            proceed = await MinValidator(
                50, message=message
            ).validate(args[0])
            if not proceed:
                return 0
            amount = int(args[0])
        else:
            amount = 50
            if user_profile.get('balance') >= 50:
                await message.channel.send(
                    embed=get_embed(
                        "Amount of chips not specified, "
                        "will be set to **50**.",
                        embed_type="warning",
                        title="No Pokechips count"
                    )
                )
        if user_profile.get('balance') < amount:
            await dm_send(
                message, message.author,
                embed=get_embed(
                    f"You do not have enough {self.chip_emoji}\n"
                    "Contact an admin for details on how to get more.",
                    embed_type="error",
                    title="Insufficient Balance"
                )
            )
            return 0
        return amount

    async def __duel_get_gladiator(
        self, message: Message, user: Member,
        profile: Profiles, notify: bool = True
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
                    )
                )
            return None
        available = []
        for glad in glads['Gladiator']:
            itemid = inv.from_name(name=glad['name'])[0]
            gld = Item.from_id(itemid)
            available.append(gld)
        if len(available) > 1:
            choices_view = SelectView(
                heading="Choose a gladiator:",
                options={
                    gld: gld.description.split(' as')[0]
                    for gld in available
                },
                no_response=True,
                check=lambda x: x.id == message.author.id
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
        await base.delete()
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
            str(players[1].id), glads[1].name, str(winner.user.id),
            amount
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

    async def __duel_start(
        self, message: Message,
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
            thread = await message.channel.start_thread(
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
