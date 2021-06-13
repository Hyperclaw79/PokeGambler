"""
Gambling Commands Module
"""

# pylint: disable=too-few-public-methods, too-many-locals, unused-argument

from __future__ import annotations
import asyncio
import random
from typing import List, Optional, TYPE_CHECKING

import discord

from ..base.items import Gladiator, Item
from ..base.models import (
    Inventory, Profile, Duels
)
from ..helpers.imageclasses import GladitorMatchHandler

from ..helpers.utils import (
    dedent, get_embed, get_enum_embed,
    img2file, wait_for, dm_send
)
from .basecommand import Commands

if TYPE_CHECKING:
    from discord import Message, Member


class DuelActions:
    """
    Holder class for different types of duel attacks.
    """
    normal = [
        "<g1> kicks <g2> to the ground.",
        "<g1> pokes <g2> in the eye.",
        "<g1> punches <g2> in the face.",
        "<g1> cuts <g2> with a kitchen knife.",
        "<g1> stikes <g2> from above.",
        "<g1> trips <g2> with finesse.",
        "<g1> bashes <g2> with force."
    ]
    crit = [
        "<g1> releases a charged 🅴🅽🅴🆁🅶🆈 🆁🅰🆈.",
        "<g1> infuses weapon with mana and unleashes "
        "🅴🅻🅴🅼🅴🅽🆃🅰🅻 🆂🆃🆁🅸🅺🅴.",
        "<g1> carries out a 🅵🅻🆄🆁🆁🆈 of 🆂🆃🆁🅸🅺🅴🆂.",
        "<g1> cracks <g2>'s armor with "
        "🅰🆁🅼🅾🆁 🅿🅴🅽🅴🆃🆁🅰🆃🅸🅾🅽.",
        "<g1> aims for vitals and makes <g2> 🅱🅻🅴🅴🅳."
    ]

    @classmethod
    def get(cls: DuelActions, damage: int) -> str:
        """
        Returns a random attack based on damage.
        """
        if damage >= 300:
            return "<g1> uses 🅳🅸🆅🅸🅽🅴 🆆🆁🅰🆃🅷 and finishes off <g2>."
        if damage > 150:
            return random.choice(cls.crit)
        return random.choice(cls.normal)


class DuelCommands(Commands):
    """
    Gamble Commands are the core commands for PokeGambler.
    Currently, the only available command is the Gamble command itself.
    """

    @staticmethod
    def __duel_get_action(
        glads: List[Gladiator],
        damages: List[int]
    ) -> str:
        return "\n".join(
            DuelActions.get(damages[idx]).replace(
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
            if user_profile.get()['balance'] >= 50:
                await message.channel.send(
                    embed=get_embed(
                        "Amount of chips not specified, "
                        "will be set to **50**.",
                        embed_type="warning",
                        title="No Pokechips count"
                    )
                )
        if user_profile.get()['balance'] < amount:
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
                "as Gladiator for this match.",
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
        if profile.get()["balance"] < cost:
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

    async def duel(
        self, message: Message,
        args: Optional[List] = None,
        mentions: List[Member] = None,
        **kwargs
    ):
        """ Carries out Duel between two players. """
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
