"""
Gambling Commands Module
"""

# pylint: disable=too-many-arguments, too-many-locals, too-many-lines
# pylint: disable=too-many-instance-attributes, unused-argument

from __future__ import annotations
import asyncio
import math
import random
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

import discord

from ..base.items import Gladiator, Item
from ..base.models import (
    Flips, Inventory, Loots,
    Matches, Moles, Profile,
    Duels
)
from ..helpers.checks import user_check, user_rctn
from ..helpers.imageclasses import (
    BoardGenerator, GladitorMatchHandler
)
from ..helpers.utils import (
    dedent, get_embed, get_enum_embed,
    img2file, wait_for, dm_send
)
from .basecommand import (
    Commands, alias, dealer_only,
    model, no_thumb
)

if TYPE_CHECKING:
    from discord import Message, Member


class GambleCommands(Commands):
    """
    Gamble Commands are the core commands for PokeGambler.
    Currently, the only available command is the Gamble command itself.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.registered = []
        self.conv_table = {
            f"{i}": i
            for i in range(2, 11)
        }
        self.conv_table.update({
            "0": 0,
            "A": 1,
            "J": 11,
            "Q": 12,
            "K": 13,
            "Joker": 100
        })
        self.suits = [
            "joker", "spade", "heart", "club", "diamond"
        ]
        self.catog_channel = None
        self.match_status = 0  # 1 - open for regs, 2 - in progress
        self.rules = {
            "lower_wins": "Lower number card wins"
        }
        self.boardgen = BoardGenerator(self.ctx.assets_path)

    def __charge_player(self, dealed_deck, fee):
        profiles = {}
        for player, _ in dealed_deck.items():
            profiles[str(player.id)] = profile = Profile(self.database, player)
            data = profile.get()
            bal = data["balance"]
            num_matches = data["num_matches"]
            won_chips = data["won_chips"]
            bal -= fee
            won_chips -= fee
            num_matches += 1
            profile.update(
                balance=bal,
                num_matches=num_matches,
                won_chips=won_chips
            )
            self.registered.remove(player)
        return profiles

    async def __create_gamble_channel(self, message):
        if not self.catog_channel:
            self.catog_channel = [
                chan
                for chan in message.guild.categories
                if chan.name.lower() in (
                    "pokegambler", "text channels",
                    "pokégambler", "gamble"
                )
            ][0]
        gamblers = [
            role
            for role in message.guild.roles
            if role.name.lower() == "gamblers"
        ][0]
        dealers = [
            role
            for role in message.guild.roles
            if role.name.lower() == "dealers"
        ][0]
        overwrites = {
            gamblers: discord.PermissionOverwrite(send_messages=False),
            message.guild.me: discord.PermissionOverwrite(send_messages=True),
            dealers: discord.PermissionOverwrite(send_messages=True)
        }
        gamble_channel = await message.guild.create_text_channel(
            name="gamble-here",
            overwrites=overwrites,
            category=self.catog_channel
        )
        return gamble_channel, gamblers

    async def __cleanup(self, gamble_channel, delay=30.0):
        await asyncio.sleep(delay)
        if gamble_channel:
            await gamble_channel.delete()
        self.registered = []
        self.match_status = 0

    def __get_decks(self, num_cards, joker_chance):
        dealed_deck = {
            self.registered[i]: card
            for i, card in enumerate(
                self.ctx.dealer.get_random_cards(
                    num_cards=num_cards,
                    joker_chance=joker_chance
                )
            )
        }
        closed_decks = [
            self.ctx.dealer.get_closed_deck(num_cards=i)
            for i in range(num_cards, 0, -1)
        ]
        return dealed_deck, closed_decks

    async def __handle_low_bal(self, usr, gamble_channel):
        low_bal_embed = get_embed(
            "Every user gets 100 chips as a starting bonus.\n"
            "You can buy more or exchange for Poketwo credits.",
            embed_type="error",
            title="Not enough Pokechips!",
            footer="Contact an admin for details."
        )
        try:
            await usr.send(embed=low_bal_embed)
        except discord.Forbidden:
            await gamble_channel.send(
                content=usr.mention,
                embed=low_bal_embed
            )

    async def __handle_registration(self, message, **kwargs):
        fee = kwargs["fee"]
        max_players = max(2, int(kwargs.pop("max_players", 12)))
        gamble_channel, gamblers = await self.__create_gamble_channel(message)
        rules = ', '.join(
            self.rules[key]
            for key in kwargs
            if key in self.rules.keys()
        ) or 'None'
        desc = (
            f"**Entry Fee**: {fee} <:pokechip:840469159242760203> "
            "(Non-refundable unless match fails)\n"
            f"**Custom Rules**: {rules}\n"
            "**Transaction Rate**: `<tr>%` "
            "(will increase by 5% per 3 players if more than 12)\n"
        )
        admins = [
            role
            for role in message.guild.roles
            if role.name.lower() == "admins"
        ][0]
        hot_time = False
        if admins in message.author.roles:
            hot_time = True
            desc += "**:fire: Hot Time is active! " + \
                "The chance to get Joker is increased to `20%`!**\n"
        else:
            desc += "Chance to get Joker: 5%"
        register_embed = get_embed(
            desc,
            title="A new match is about to start!",
            footer="React with ➕ (within 30 secs) "
            "to be included in the match."
        )
        first_embed = register_embed.copy()
        first_embed.description = first_embed.description.replace("<tr>", "10")
        register_msg = await gamble_channel.send(
            content=f"Hey {gamblers.mention}",
            embed=first_embed,
        )
        await register_msg.add_reaction("➕")
        now = datetime.now()
        while all([
            (datetime.now() - now).total_seconds() < 30,
            len(self.registered) < max_players
        ]):
            try:
                _, usr = await self.ctx.wait_for(
                    "reaction_add",
                    check=lambda rctn, usr: all([
                        rctn.message.id == register_msg.id,
                        rctn.emoji == "➕",
                        usr.id != self.ctx.user.id,
                        usr not in self.registered,
                        not usr.bot
                    ]),
                    timeout=(30 - (datetime.now() - now).total_seconds())
                )
                bal = Profile(self.database, usr).get()["balance"]
                if bal < fee:
                    await self.__handle_low_bal(usr, gamble_channel)
                    continue
                self.registered.append(usr)
                players = ', '.join(player.name for player in self.registered)
                embed = self.__prep_reg_embed(
                    register_embed, players,
                    fee, now, max_players
                )
                await register_msg.edit(embed=embed)
            except asyncio.TimeoutError:
                continue
        return gamble_channel, hot_time

    async def __handle_roll(
        self, message, deck, player,
        card, gamble_channel, dealed_deck
    ):
        closed_fl = img2file(deck, "closed.png")
        card_fl = img2file(
            card["card_img"],
            f"{card['card_num']}{card['suit']}.jpeg"
        )
        closed_msg = await gamble_channel.send(
            content=f"{player.mention}, react with 👀 within 10 seconds.",
            file=closed_fl
        )
        await closed_msg.add_reaction("👀")
        try:
            await self.ctx.wait_for(
                "reaction_add",
                check=lambda rctn, usr: user_rctn(
                    message, player, rctn, usr,
                    chan=gamble_channel, emoji="👀"
                ),
                timeout=10
            )
        except asyncio.TimeoutError:
            await gamble_channel.send(
                embed=get_embed(
                    f"{player.mention}, you didn't react in time."
                )
            )
            await closed_msg.delete()
            dealed_deck[player].update({
                "card_num": "0",
                "card_img": self.ctx.dealer.closed_card.copy()
            })
            return
        await closed_msg.delete()
        await gamble_channel.send(
            content=f"{player.mention}, here's your card:",
            file=card_fl
        )
        if card["card_num"] == "Joker":
            return "Joker"

    async def __announce_winner(
        self, gamble_channel, dealed_deck,
        winner, fee, profiles
    ):
        profile = profiles[str(winner.id)]
        data = profile.get()
        bal = data["balance"]
        num_wins = data["num_wins"]
        won_chips = data["won_chips"]
        transaction_rate = 0.1 + 0.05 * math.floor(
            max(
                0,
                len(self.registered) - 12
            ) / 3
        )
        incr = int(
            (fee * len(dealed_deck.items())) * (1 - transaction_rate)
        )
        bal += incr
        num_wins += 1
        if num_wins in [25, 100]:
            loot_table = Loots(self.database, winner)
            if num_wins == 25:
                loot_table.update(tier=2)
            else:
                loot_table.update(tier=3)
        won_chips += incr
        profile.update(
            balance=bal,
            num_wins=num_wins,
            won_chips=won_chips
        )
        title = f"The winner is {winner}!"
        is_joker = [
            player
            for player, card in dealed_deck.items()
            if card["card_num"] == "Joker"
        ]
        if is_joker:
            title += " (by rolling a Joker)"
        winner_embed = get_embed(
            f"{incr} pokechips have been added to their balance.",
            title=title,
            footer="10% pokechips from the pot deducted as transaction fee."
        )
        await gamble_channel.send(embed=winner_embed)
        return bool(is_joker)

    async def __handle_winner(
        self, dealed_deck,
        gamble_channel, profiles,
        lower_wins, fee
    ):
        embed = get_enum_embed(
            [
                f"{player} rolled a 『{card['card_num']} {card['suit']}』."
                for player, card in dealed_deck.items()
            ],
            title="Roll Table"
        )
        players = sorted(
            dealed_deck.items(),
            key=lambda x: (
                self.conv_table[
                    x[1]["card_num"]
                ],
                -self.suits.index(
                    x[1]["suit"]
                )
            ),
            reverse=True
        )
        if lower_wins:
            players = players[::-1]
            if self.conv_table[players[0][1]['card_num']] == 0:
                players.append(players.pop(0))
        winner = players[0][0]
        rolled = [
            dealed_deck[player]["card_img"]
            for player in [
                pl[0]
                for pl in players
            ]
        ]
        rolled_deck = self.ctx.dealer.get_deck(rolled, reverse=True)
        rolled_fl = img2file(rolled_deck, "rolled.jpg")
        embed.set_image(url="attachment://rolled.jpg")
        await gamble_channel.send(embed=embed, file=rolled_fl)
        # Return is_joker for saving into DB
        return (
            winner,
            await self.__announce_winner(
                gamble_channel, dealed_deck,
                winner, fee, profiles
            )
        )

    def __prep_reg_embed(
        self, register_embed, players,
        fee, now, max_players
    ):
        embed = register_embed.copy()
        embed.description = register_embed.description.replace(
            "<tr>",
            str(
                10 + 5 * math.floor(
                    max(0, len(self.registered) - 12) / 3
                )
            )
        )
        rem_secs = int(30 - (datetime.now() - now).total_seconds())
        embed.set_footer(
            text=f"React with ➕ (within {rem_secs} secs)"
            " to be included in the match."
        )
        embed.add_field(
            name=f"Current Participants "
            f"『{len(self.registered)}/{max_players}』",
            value=players,
            inline=False
        )
        embed.add_field(
            name="Pokechips in the pot",
            value=f"{fee * len(self.registered)} "
            "<:pokechip:840469159242760203>",
            inline=False
        )
        return embed

    async def __input_handler(
        self, message, args, profile,
        default, min_chips, max_chips
    ):
        amount = default
        if args:
            try:
                amount = int(args[0])
            except (ZeroDivisionError, ValueError):
                await message.channel.send(
                    embed=get_embed(
                        f"Amount will be defaulted to {default} chips.",
                        embed_type="warning",
                        title="Invalid Input"
                    )
                )
        if any([
            amount < min_chips,
            amount > max_chips
        ]):
            await message.channel.send(
                embed=get_embed(
                    f"Amount should be more than {min_chips} and less than {max_chips} chips.",
                    embed_type="error",
                    title="Invalid Input"
                )
            )
            return None
        if profile.get()["balance"] < amount:
            await self.__handle_low_bal(message.author, message.channel)
            await message.add_reaction("❌")
            return None
        return amount

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
                        "Amount of chips not specified, will be set to **50**.",
                        embed_type="warning",
                        title="No Pokechips count"
                    )
                )
        if user_profile.get()['balance'] < amount:
            await dm_send(
                message, message.author,
                embed=get_embed(
                    "You do not have enough <:pokechip:840469159242760203>\n"
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
                f"Successfully chosen 『**{gladiator}**』as Gladiator for this match.",
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
                f"Bet Amount: **{amount}** <:pokechip:840469159242760203>",
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
            action = f"""
            * {glads[0].name} deals『{dmg1}』damage to {glads[1].name}.
            * {glads[1].name} deals『{dmg2}』damage to {glads[0].name}.
            """
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

    @dealer_only
    @model([Profile, Matches, Loots])
    @alias(["deal", "roll"])
    async def cmd_gamble(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """The core command of the bot - Gamble.
        $```scss
        {command_prefix}gamble [50 < fee] [--lower_wins]
        ```$

        @`🎲 Dealer Command`
        Roll random pokemon themed cards for a fee and winner takes it all.
        If a fee is not specified, defaults to 50 <:pokechip:840469159242760203>.
        To make the lower card win, use the kwarg `lower_wins`.
        *A small transaction fees will be levyed before crediting the winner.
        This fee scales with number of players, if above 15.*@

        ~To gamble with default settings:
            ```
            {command_prefix}gamble
            ```
        To gamble for 1000 <:pokechip:840469159242760203>:
            ```
            {command_prefix}gamble 1000
            ```
        To gamble in lower_wins mode:
            ```
            {command_prefix}gamble --lower_wins
            ```~
        """
        if self.match_status != 0:
            await message.channel.send(
                embed=get_embed(
                    "A match/registration/cleanup is in progress, "
                    "please wait and try again later.",
                    embed_type="warning",
                    title="Unable to start match"
                )
            )
            return
        self.match_status = 1
        kwargs.pop("mentions", [])
        try:
            fee = max(int(args[0]), 50) if args else 50
        except (ZeroDivisionError, ValueError):
            fee = 50
        kwargs["fee"] = fee
        gamble_channel, hot_time = await self.__handle_registration(
            message, **kwargs
        )
        if len(self.registered) <= 1:
            await message.channel.send(
                embed=get_embed(
                    "This match has been cancelled due to lack of players.",
                    embed_type="warning",
                    title="Not enough players!"
                )
            )
            await self.__cleanup(gamble_channel, delay=10.0)
            return
        self.match_status = 2
        lower_wins = kwargs.get("lower_wins", False)
        joker_chance = 0.05
        if hot_time:
            joker_chance = 0.2
        num_cards = len(self.registered)
        dealed_deck, closed_decks = self.__get_decks(num_cards, joker_chance)
        profiles = self.__charge_player(dealed_deck, fee)
        for deck, (player, card) in zip(closed_decks, dealed_deck.items()):
            joker_found = await self.__handle_roll(
                message, deck, player, card,
                gamble_channel, dealed_deck
            )
            if joker_found:
                break
        winner, is_joker = await self.__handle_winner(
            dealed_deck, gamble_channel,
            profiles, lower_wins, fee
        )
        Matches(
            self.database, message.author,
            started_by=str(message.author.id),
            participants=list(profiles),
            winner=str(winner.id),
            lower_wins=lower_wins,
            deal_cost=fee,
            by_joker=is_joker
        ).save()
        await self.__cleanup(gamble_channel, delay=30.0)

    @model([Flips, Profile])
    @alias(["flip", "chipflip"])
    async def cmd_quickflip(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """Head/Tails flip for Pokechips.
        $```scss
        {command_prefix}quickflip [50 < amount < 9999]
        ```$

        @A quick way to double your pokechips ||(or halve it)|| using a chip flip.
        If no amount is specified, 50 chips will be used by default.
        Minimum 50 chips and maximim 9999 chips can be used.@

        ~To flip for 50 <:pokechip:840469159242760203>:
            ```
            {command_prefix}flip
            ```
        To flip for 1000 <:pokechip:840469159242760203>:
            ```
            {command_prefix}flip 1000
            ```~
        """
        profile = Profile(self.database, message.author)
        amount = await self.__input_handler(
            message, args, profile, default=50,
            min_chips=50, max_chips=9999
        )
        if amount is None:
            return
        opt_msg = await message.channel.send(
            embed=get_embed(
                "```md\n# Options\n1. Heads\n2. Tails\n```",
                title=f"**Place your bet for {amount}** <:pokechip:840469159242760203>",
                footer=f"⚠️ You'll either get {amount * 2} or "
                f"lose {amount} pokechips",
                image="https://cdn.discordapp.com/attachments/840469669332516904"
                "/843077878816178186/blinker.gif"
            )
        )
        idx = random.randint(0, 1)
        img = [
            "https://cdn.discordapp.com/attachments/840469669332516904/" + \
                "843079658274422814/logochip.png",
            "https://cdn.discordapp.com/attachments/840469669332516904/" + \
                "843079660375638046/pokechip.png"
        ][idx]
        reply = await wait_for(
            message.channel, self.ctx, init_msg=opt_msg,
            check=lambda msg: user_check(msg, message),
            timeout="inf"
        )
        if not reply:
            return
        reply = reply.content.lower()
        valids = ['1', '2', 'heads', 'tails']
        valid_str = ', '.join(valids)
        if reply not in valids:
            await message.channel.send(
                embed=get_embed(
                    f"You need to choose from: ({valid_str})",
                    embed_type="error",
                    title="Invalid Input"
                )
            )
            return
        choice = int(reply) - 1 if reply in valids[:2] else valids[2:].index(reply)
        msg = f"PokeGambler choose {valids[2:][idx].title()}.\n"
        if choice == idx:
            amt_mult = 1
            boosts = self.ctx.boost_dict.get(message.author.id, None)
            if boosts:
                amt_mult += boosts['boost_flip']['stack'] * 0.1
            msg += f"You have won {amount + int(amount * amt_mult)} <:pokechip:840469159242760203>"
            title = "Congratulations!"
            color = 5023308
            profile.credit(int(amount * amt_mult))
            won = True
        else:
            msg += f"You have lost {amount} <:pokechip:840469159242760203>"
            title = "You Lost!"
            color = 14155786
            profile.debit(amount)
            won = False
        Flips(
            self.database, message.author,
            amount, won
        ).save()
        emb = get_embed(msg, title=title, image=img, color=color)
        await opt_msg.edit(embed=emb)

    @model([Moles, Profile])
    @alias(["mole", "whack"])
    @no_thumb
    async def cmd_whackamole(self, message: Message, **kwargs):
        """Find the chip minigame.
        $```scss
        {command_prefix}whackamole [--difficulty number]
        ```$

        @Find the hidden chip for a chance to win a jackpot.
        If no amount is specified, 50 chips will be used by default.
        Minimum 50 chips and maximim 9999 chips can be used.
        You can choose difficulty level (default 1) and rewards will scale.
        ```py
        ╔═══════╦═══════╦══════╦════════╗
        ║ Level ║ Board ║ Cost ║ Reward ║
        ╠═══════╬═══════╬══════╬════════╣
        ║   1   ║  3x3  ║   50 ║   x3   ║
        ║   2   ║  4x4  ║  100 ║   x4   ║
        ║   3   ║  5x5  ║  150 ║   x10  ║
        ║   4   ║  6x6  ║  200 ║   x50  ║
        ║   5   ║  7x7  ║  250 ║   x100 ║
        ╚═══════╩═══════╩══════╩════════╝
        ```@

        ~To play with the default difficulty (level 1):
            ```
            {command_prefix}mole
            ```
        To play the extreme mode (level 5):
            ```
            {command_prefix}mole --difficulty 5
            ```~
        """
        level = kwargs.get("difficulty", kwargs.get("level", 1))
        if any([
            not str(level).isdigit(),
            str(level).isdigit() and int(level) not in range(1, 6)
        ]):
            await message.channel.send(
                embed=get_embed(
                    "You need to choose a number between 1 and 5.",
                    embed_type="error",
                    title="Invalid Input"
                )
            )
            return
        level = int(level) - 1
        valids = self.boardgen.get_valids(level)
        cost = [50, 100, 150, 200, 250][level]
        multiplier = [3, 4, 10, 50, 100][level]
        profile = Profile(self.database, message.author)
        if profile.get()["balance"] < cost:
            await self.__handle_low_bal(message.author, message.channel)
            await message.add_reaction("❌")
            return
        board, board_img = self.boardgen.get_board(level)
        opt_msg = await message.channel.send(
            content=f"**Difficulty: {level + 1} ({board})**\n"
            f"**Cost: {cost} <:pokechip:840469159242760203>** \n"
            "> Choose a tile:",
            file=img2file(board_img, f"{board}.jpg")
        )
        reply = await wait_for(
            message.channel, self.ctx, init_msg=opt_msg,
            check=lambda msg: user_check(msg, message),
            timeout="inf"
        )
        if reply.content.title() not in valids:
            await message.channel.send(
                embed=get_embed(
                    "You can only choose one of the displayed tiles.",
                    embed_type="error",
                    title="Invalid Input"
                )
            )
            return
        choice = reply.content.title()
        rolled, board_img = self.boardgen.get(level)
        await opt_msg.delete()
        if choice == rolled:
            content = "**Congratulations! You guessed it correctly.**\n" + \
                f"{cost * multiplier} <:pokechip:840469159242760203> " + \
                "have been added in your account."
            color = 5023308
            profile.credit(cost * multiplier)
            won = True
        else:
            content = "**Uhoh! You couldn't guess it right this time.**\n" + \
                f"{cost} <:pokechip:840469159242760203> " + \
                "have been taken from your account."
            color = 14155786
            profile.debit(cost)
            won = False
        Moles(
            self.database, message.author,
            cost, level, won
        ).save()
        await message.channel.send(
            embed=get_embed(
                content=content,
                color=color,
                image=f"attachment://{rolled}.jpg"
            ),
            file=img2file(board_img, f"{rolled}.jpg")
        )

    async def cmd_matches(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """List latest gamble matches.
        $```scss
        {command_prefix}matches [quantity] [--verbose]
        ```$

        @Lists out the results of latest gamble matches.
        If no quantity is given, defaults to 10.
        If --verbose is used, lists the mode and if joker spawned.@

        ~To list latest matches:
            ```
            {command_prefix}matches
            ```
        To latest 5 matches:
            ```
            {command_prefix}matches 5
            ```
        To see if Joker spawned in last 5 matches:
            ```
            {command_prefix}matches 5 --verbose
            ```~
        """
        limit = int(args[0]) if args else 10
        matches = self.database.get_matches(limit=limit)
        embeds = []
        for match in matches:
            started_by = message.guild.get_member(
                int(match["started_by"])
            )
            played_at = match["played_at"]
            pot = match["deal_cost"] * len(match['participants'])
            parts = "\n".join(
                str(message.guild.get_member(plyr))
                for plyr in match["participants"]
            )
            parts = f"```py\n{parts}\n```"
            winner = message.guild.get_member(int(match["winner"]))
            emb = get_embed(
                f"Match started by: **{started_by}**\n"
                f"Played on: **{played_at}**\n"
                f"Amount in pot: **{pot}** <:pokechip:840469159242760203>",
                title="Recent Matches"
            )
            emb.add_field(
                name="Participants",
                value=parts,
                inline=True
            )
            emb.add_field(
                name="Winner",
                value=f"**```{winner}```**",
                inline=True
            )
            emb.add_field(
                name="\u200B",
                value="\u200B",
                inline=True
            )
            if kwargs.get("verbose", False):
                emb.add_field(
                    name="Mode",
                    value=f"```py\n{match['lower_wins']}\n```",
                    inline=True
                )
                emb.add_field(
                    name="Joker Spawned",
                    value=f"```py\n{match['by_joker']}\n```",
                    inline=True
                )
                emb.add_field(
                    name="\u200B",
                    value="\u200B",
                    inline=True
                )
            emb.set_image(url=winner.avatar_url_as(size=256))
            embeds.append(emb)
        await self.paginate(message, embeds)

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
        Cost defaults to 50 <:pokechip:840469159242760203> (minimum) if not provided.
        Both the players must own at least one Gladiator and have enough balance.
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
        # TODO: rework damage actions
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
        confirmed = await self.__duel_confirmation(message, user2, amount)
        if not confirmed:
            return
        other_profile = Profile(self.database, user2)
        gladiator2 = await self.__duel_get_gladiator(
            message, user2, notify=False
        )
        if not gladiator2:
            return
        proceed = await self.__duel_proceed(
            message, user2, other_profile,
            gladiator2, amount
        )
        if not proceed:
            return
        glads = [gladiator1, gladiator2]
        profiles = [user_profile, other_profile]
        await self.__duel_play(
            message, glads,
            profiles, amount
        )
