"""
Gambling Commands Module
"""

# pylint: disable=too-many-arguments, too-many-locals, unused-argument

import asyncio
import math
import os
from datetime import datetime

import discord

from ..base.models import Profile
from ..helpers.checks import user_rctn, user_check
from ..helpers.imageclasses import ChipFlipper
from ..helpers.utils import (
    get_embed, get_enum_embed,
    img2file, wait_for
)
from .basecommand import Commands, alias, dealer_only


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
        self.chipflipper = ChipFlipper(self.ctx.assets_path)

    def __charge_player(self, dealed_deck, fee):
        profiles = {}
        for player, _ in dealed_deck.items():
            profiles[str(player.id)] = profile = Profile(self.database, player)
            data = profile.get()
            bal = data["balance"]
            num_matches = data["num_matches"]
            bal -= fee
            num_matches += 1
            profile.update(
                balance=bal,
                num_matches=num_matches
            )
            self.registered.remove(player)
        return profiles

    async def __create_gamble_channel(self, message):
        if not self.catog_channel:
            self.catog_channel = [
                chan
                for chan in message.guild.categories
                if chan.name.lower() == "text channels"
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
                        usr not in self.registered
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
            dealed_deck[player] = {
                "card_num": 0,
                "suit": "Disqualified",
                "card_img": self.ctx.dealer.closed_card.copy()
            }
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
        profile.update(
            balance=bal,
            num_wins=num_wins
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

    async def __handle_winner(
        self, dealed_deck,
        gamble_channel, profiles,
        lower_wins, fee
    ):
        embed = get_enum_embed(
            [
                f"{player} rolled a [{card['card_num']} {card['suit']}]."
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
                self.suits.index(
                    x[1]["suit"]
                )
            ),
            reverse=True
        )
        if lower_wins:
            players = players[::-1]
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
        await self.__announce_winner(
            gamble_channel, dealed_deck,
            winner, fee, profiles
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
            f"[{len(self.registered)}/{max_players}]",
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

    @dealer_only
    @alias(["deal", "roll"])
    async def cmd_gamble(self, message, args=None, **kwargs):
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
            fee = min(int(args[0]), 50) if args else 50
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
        await self.__handle_winner(
            dealed_deck, gamble_channel,
            profiles, lower_wins, fee
        )
        await self.__cleanup(gamble_channel, delay=30.0)

    @alias(["flip", "chipflip"])
    async def cmd_quickflip(self, message, args=None, **kwargs):
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
        amount = int(args[0]) if args else 50
        if profile.get()["balance"] < amount:
            await self.__handle_low_bal(message.author, message.channel)
            await message.add_reaction("❌")
            return
        opt_msg = await message.channel.send(
            embed=get_embed(
                "```md\n# Options\n1. Heads\n2. Tails\n```",
                title=f"**Place your bet for {amount}** <:pokechip:840469159242760203>",
                footer=f"⚠️ You'll either get {amount * 2} or "
                f"lose {amount} pokechips"
            ),
            file=discord.File(
                os.path.join(self.ctx.assets_path, 'blinker.gif')
            )
        )
        idx, img = self.chipflipper.get()
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
        chip = img2file(img, "chip.png", ext="PNG")
        msg = f"PokeGambler choose {valids[2:][idx].title()}.\n"
        if choice == idx:
            msg += f"You have won {amount * 2} <:pokechip:840469159242760203>"
            title = "Congratulations!"
            color = 5023308
            profile.update(
                balance=profile.get()["balance"] + (amount * 2),
                won_chips=profile.get()["won_chips"] + (amount * 2)
            )
        else:
            msg += f"You have lost {amount} <:pokechip:840469159242760203>"
            title = "You Lost!"
            color = 14155786
            profile.update(
                balance=profile.get()["balance"] - amount,
                won_chips=profile.get()["won_chips"] - amount
            )
        emb = get_embed(msg, title=title)
        emb.color = color
        await opt_msg.delete()
        await message.channel.send(embed=emb, file=chip)
