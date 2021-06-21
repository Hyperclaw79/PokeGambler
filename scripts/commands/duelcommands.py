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
    DuelActionsModel, Inventory, Profile, Duels
)

from ..helpers.checks import user_check
from ..helpers.imageclasses import GladitorMatchHandler
from ..helpers.utils import (
    dedent, get_embed, get_enum_embed,
    img2file, wait_for, dm_send
)
from .basecommand import (
    Commands, alias, check_completion,
    cooldown, model, no_thumb
)

if TYPE_CHECKING:
    from bot import PokeGambler
    from discord import Message, Member
    from ..base.dbconn import DBConnector


class DuelActions:
    """
    Holder class for different types of duel attacks.
    """
    def __init__(
        self, ctx: PokeGambler,
        database: DBConnector
    ) -> None:
        self.ctx = ctx
        self.database = database
        actions = database.get_actions()
        if not actions:
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
                        self.database, owner,
                        action, key
                    ).save()
        else:
            self.normal = []
            self.crit = []
            for action in actions:
                if action["level"] == "Normal":
                    self.normal.append(action["action"])
                else:
                    self.crit.append(action["action"])

    def refresh(self):
        """
        Populates DuelActions class with all actions in DB.
        """
        self.normal = []
        self.crit = []
        actions = self.database.get_actions()
        for action in actions:
            if action["level"] == "Normal":
                self.normal.append(action["action"])
            else:
                self.crit.append(action["action"])

    def get(self, damage: int) -> str:
        """
        Returns a random attack based on damage.
        """
        if damage >= 300:
            return "<g1> uses 🅳🅸🆅🅸🅽🅴 🆆🆁🅰🆃🅷 and finishes off <g2>."
        if damage > 150:
            return random.choice(self.crit)
        return random.choice(self.normal)


class DuelCommands(Commands):
    """
    Gamble Commands are the core commands for PokeGambler.
    Currently, the only available command is the Gamble command itself.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.duelactions = DuelActions(self.ctx, self.database)

    @cooldown(300)
    @model([Duels, Profile, Inventory, Item])
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
        user_profile = Profile(self.database, message.author)
        amount = await self.__duel_get_cost(message, user_profile, args)
        if not amount:
            return
        gladiator1 = await self.__duel_get_gladiator(message, message.author)
        if not gladiator1:
            return
        user2 = mentions[0]
        na_checks = [
            user2.bot,
            self.database.is_blacklisted(user2.id)
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
        confirmed = await self.__duel_confirmation(message, user2, amount)
        if not confirmed:
            return
        other_profile = Profile(self.database, user2)
        gladiator2 = await self.__duel_get_gladiator(
            message, user2, notify=False
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

    @alias("action+")
    @model([DuelActionsModel, Profile])
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
        dmg_info = ["(dmg < 150)", "(dmg >= 150)"]
        cost_info = [
            "(200 Pokechips)",
            "(200 Pokebonds)"
        ]
        charges = ["won_chips", "pokebonds"]
        lvl_msg = await message.channel.send(
            embed=get_enum_embed(
                [
                    f"{lvl} {dmg} {cost}"
                    for lvl, dmg, cost in zip(
                        levels, dmg_info, cost_info
                    )
                ],
                title="Choose the action level"
            )
        )
        reply = await wait_for(
            message.channel, self.ctx, init_msg=lvl_msg,
            check=lambda msg: user_check(msg, message),
            timeout="inf"
        )
        if (
            reply.content.isdigit()
            and 0 < int(reply.content) <= len(levels)
        ):
            choice = levels[int(reply.content) - 1]
        elif reply.content.title() in levels:
            choice = reply.content.title()
        else:
            await message.channel.send(
                embed=get_embed(
                    "Please reuse the command.",
                    embed_type="error",
                    title="Invalid Choice"
                )
            )
            return
        profile = Profile(self.database, message.author)
        if profile.get(
            charges[levels.index(choice)]
        ) < 200:
            await message.channel.send(
                embed=get_embed(
                    "You cannot afford to create that action.",
                    embed_type="error",
                    title="Insufficient Balance"
                )
            )
            return
        action_inp_msg = await message.channel.send(
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
                title="Enter the action message"
            )
        )
        reply = await wait_for(
            message.channel, self.ctx, init_msg=action_inp_msg,
            check=lambda msg: user_check(msg, message),
            timeout="inf"
        )
        if "<g1>" not in reply.content:
            await message.channel.send(
                embed=get_embed(
                    "You need to include at least <g1> in the action.\n"
                    "Please reuse the command.",
                    embed_type="error",
                    title="No Gladiator 1 Placeholder"
                )
            )
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
            self.database, message.author,
            action[:100], choice
        ).save()
        await message.channel.send(
            embed=get_embed(
                "Successfully saved your duel action.\n"
                "Let's hope it shows up soon.",
                title="Duel Action saved"
            )
        )
        profile.debit(200, bonds=levels.index(choice))
        self.duelactions.refresh()

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
        inv = Inventory(self.database, message.author)
        tickets = inv.from_name("Gladiator Nickname Change")
        if not tickets:
            await message.channel.send(
                embed=get_embed(
                    "You do not have any renaming tickets.\n"
                    "You can buy one from the Consumables Shop.",
                    embed_type="error",
                    title="Insufficient Tickets"
                )
            )
            return
        glad = await self.__duel_get_gladiator(message, message.author)
        if not glad:
            return
        inp_msg = await dm_send(
            message,
            message.author,
            embed=get_embed(
                "Use a sensible name (Max 10 chars) for your gladiator.",
                title="Enter New Nickname"
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
        new_name = re.sub(r"[^\x00-\x7F]+", "", reply.content[:10].title()).strip()
        if not new_name:
            await dm_send(
                message,
                message.author,
                embed=get_embed(
                    "That name is not allowed, keep it simple.\n"
                    "Please reuse the command later.",
                    embed_type="error",
                    title="Invalid Nickname"
                )
            )
            return
        glad.rename(self.database, new_name)
        inv.delete([tickets[0]], quantity=1)
        await dm_send(
            message,
            message.author,
            embed=get_embed(
                f"Successfully renamed your Gladiator to {new_name}.",
                title="Rename Complete"
            )
        )

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
        user_profile: Profile,
        args: Optional[List] = None
    ) -> int:
        if args and args[0].isdigit() and int(args[0]) > 50:
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
        notify: bool = True
    ) -> Gladiator:
        inv = Inventory(self.database, user)
        glads, _ = inv.get(True, category='Gladiator')
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
            itemid = int(inv.get_ids(name=glad['name'])[0], 16)
            gld = Item.from_id(self.database, itemid)
            available.append(gld)
        if len(available) > 1:
            emb = get_enum_embed(
                map(str, available),
                title="Choose which gladiator you want to use:"
            )
            choice_msg = await dm_send(
                message, user,
                embed=emb
            )
            reply = await wait_for(
                choice_msg.channel, self.ctx,
                init_msg=choice_msg,
                check=lambda msg: all([
                    msg.author.id == user.id,
                    msg.channel.id == choice_msg.channel.id
                ]),
                timeout="inf"
            )
            if reply.content.lower() not in [
                str(idx + 1) for idx in range(len(available))
            ] + [str(glad).lower() for glad in available]:
                await dm_send(
                    message, user,
                    embed=get_embed(
                        "That's an invalid choice.\n"
                        "Using the first available one.",
                        embed_type="warning",
                        title="Invalid Input"
                    )
                )
                gladiator = available[0]
            elif reply.content.isdigit():
                gladiator = available[int(reply.content) - 1]
            else:
                gladiator = [
                    gld
                    for gld in available
                    if str(gld).lower() == reply.content.lower()
                ][0]
        else:
            gladiator = available[0]
        await dm_send(
            message, user,
            embed=get_embed(
                f"Successfully chosen 『**{gladiator}**』"
                "for this command/match.",
                title="Gladiator Confirmed"
            )
        )
        gladiator.image = await gladiator.get_image(self.ctx.sess)
        gladiator.owner = user
        return gladiator

    async def __duel_confirmation(
        self, message: Message,
        user: Member, amount: int
    ) -> bool:
        inv_msg = await message.channel.send(
            content=f"Hey {user.mention}, you have been invited "
            f"to a Gladiator match by **{message.author.name}**",
            embed=get_embed(
                "React to this message with ☑️ to accept the duel.\n"
                f"Bet Amount: **{amount}** {self.chip_emoji}",
                title="Do you accept?"
            )
        )
        await inv_msg.add_reaction("☑️")
        await inv_msg.add_reaction("❌")
        reply = await wait_for(
            message.channel, self.ctx,
            "reaction_add", init_msg=inv_msg,
            check=lambda rctn, usr: all([
                rctn.emoji in ["☑️", "❌"],
                rctn.message.id == inv_msg.id,
                usr.id == user.id
            ]),
            timeout=60.0
        )
        if reply:
            rctn, _ = reply
        await inv_msg.delete()
        if not reply or rctn.emoji == "❌":
            await message.channel.send(
                embed=get_embed(
                    f"Gladiator Match has been declined by **{user.name}**.",
                    embed_type="warning",
                    title="Duel cancelled."
                )
            )
            return False
        return True

    @staticmethod
    async def __duel_proceed(
        message: Message, user: Member,
        profile: Profile, gladiator: Gladiator,
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
        start_fl = img2file(
            next(gladhandler.get(glads))[0],
            "start.jpg"
        )
        fresh_emb.set_image(
            url="attachment://start.jpg"
        )
        base = await message.channel.send(
            embed=fresh_emb, file=start_fl
        )
        return base

    async def __duel_play(
        self, message: Message,
        glads: List[Gladiator],
        profiles: List[Profile],
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
        base = await self.__duel_start(message, gladhandler, glads)
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
            await base.delete()
            base = await message.channel.send(
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
        await message.channel.send(
            embed=get_embed(
                f"**{winner.name}**'s『{winner_glad}』"
                f"destroyed **{other.name}**'s『{other_glad}』",
                title=f"💀 Match won by **{winner.name}**!",
                no_icon=True
            )
        )
        winner.credit(amount)
        other.debit(amount)
        Duels(
            self.database, players[0], glads[0].name,
            str(players[1].id), glads[1].name, str(winner.user.id),
            amount
        ).save()
