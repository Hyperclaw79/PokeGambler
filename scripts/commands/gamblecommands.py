"""
Gambling Commands Module
"""

# pylint: disable=too-many-arguments, too-many-locals
# pylint: disable=too-many-instance-attributes, unused-argument

from __future__ import annotations
import asyncio
import math
import random
from typing import List, Optional, TYPE_CHECKING

import discord

from ..base.models import (
    Boosts, Flips, Loots, Matches,
    Moles, Profiles
)
from ..base.shop import BoostItem
from ..base.views import GambleCounter, MultiSelectView, SelectView
from ..helpers.checks import user_rctn
from ..helpers.imageclasses import BoardGenerator
from ..helpers.utils import (
    get_embed, get_enum_embed,
    img2file
)
from ..helpers.validators import MinMaxValidator
from .basecommand import (
    Commands, alias, check_completion,
    dealer_only, model, no_thumb
)

if TYPE_CHECKING:
    from discord import Message


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
        self.rules = {
            "lower_wins": "Lower number card wins"
        }
        self.boardgen = BoardGenerator(self.ctx.assets_path)

    @check_completion
    @dealer_only
    @model([Profiles, Matches, Loots])
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
        If a fee is not specified, defaults to 50 {pokechip_emoji}.
        To make the lower card win, use the kwarg `lower_wins`.
        *A small transaction fees will be levyed before crediting the winner.
        This fee scales with number of players, if above 15.*@

        ~To gamble with default settings:
            ```
            {command_prefix}gamble
            ```
        To gamble for 1000 {pokechip_emoji}:
            ```
            {command_prefix}gamble 1000
            ```
        To gamble in lower_wins mode:
            ```
            {command_prefix}gamble --lower_wins
            ```~
        """
        kwargs.pop("mentions", [])
        try:
            fee = max(int(args[0]), 50) if args else 50
        except (ZeroDivisionError, ValueError):
            fee = 50
        kwargs["fee"] = fee
        gamble_channel, hot_time = await self.__gamble_register(
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
            await self.__gamble_cleanup(gamble_channel, delay=10.0)
            return
        try:
            lower_wins = kwargs.get("lower_wins", False)
            joker_chance = 0.2 if hot_time else 0.05
            num_cards = len(self.registered)
            dealed_deck, closed_decks = self.__gamble_get_decks(
                num_cards, joker_chance
            )
            profiles = self.__gamble_charge_player(dealed_deck, fee)
            for deck, (player, card) in zip(closed_decks, dealed_deck.items()):
                joker_found = await self.__gamble_handle_roll(
                    message, deck, player, card,
                    gamble_channel, dealed_deck
                )
                if joker_found:
                    break
            winner, is_joker = await self.__gamble_handle_winner(
                dealed_deck, gamble_channel,
                profiles, lower_wins, fee
            )
            Matches(
                message.author,
                started_by=str(message.author.id),
                participants=list(profiles),
                winner=str(winner.id),
                lower_wins=lower_wins,
                deal_cost=fee,
                by_joker=is_joker
            ).save()
        finally:
            await self.__gamble_cleanup(
                gamble_channel,
                delay=30.0,
                completed=True
            )

    @model([Flips, Profiles])
    @alias(["flip", "chipflip", "flips"])
    @check_completion
    async def cmd_quickflip(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """Head/Tails flip for Pokechips.
        $```scss
        {command_prefix}quickflip [50 < amount < 9999]
        ```$

        @A quick way to x2 your pokechips ||(or halve it)|| using a chip flip.
        If no amount is specified, 50 chips will be used by default.
        Minimum 50 chips and maximum 9999 chips can be used.@

        ~To flip for 50 {pokechip_emoji}:
            ```
            {command_prefix}flip
            ```
        To flip for 1000 {pokechip_emoji}:
            ```
            {command_prefix}flip 1000
            ```~
        """
        profile = Profiles(message.author)
        amount = await self.__flip_input_handler(
            message, args, profile,
            min_chips=50, max_chips=9999
        )
        if amount is None:
            return
        valids = ["Heads", "Tails"]
        choices_view = SelectView(
            heading="Choose an option",
            options={
                opt: ""
                for opt in valids
            },
            no_response=True,
            check=lambda x: x.user.id == message.author.id
        )
        opt_msg = await message.reply(
            embed=get_embed(
                title=f"**Place your bet for {amount}** {self.chip_emoji}",
                footer=f"⚠️ You'll either get {amount * 2} or "
                f"lose {amount} pokechips",
                image="https://cdn.discordapp.com/attachments/"
                "840469669332516904/843077878816178186/blinker.gif",
                color=profile.get("embed_color")
            ),
            view=choices_view
        )
        await choices_view.dispatch(self)
        if choices_view.result is None:
            return
        choice = valids.index(choices_view.result)
        idx = random.randint(0, 1)
        img = [
            "https://cdn.discordapp.com/attachments/874623706339618827/"
            "874627863960252466/logochip.png",
            "https://cdn.discordapp.com/attachments/874623706339618827/"
            "874627865520504842/pokechip.png"
        ][idx]
        msg = f"PokeGambler choose {valids[idx]}.\n"
        if choice == idx:
            amt_mult = 1 + (
                0.1 * Boosts(
                    message.author
                ).get("flipster")
            )
            boosts = BoostItem.get_boosts(str(message.author.id))
            amt_mult += boosts['boost_flip']['stack'] * 0.1
            tot_amt = amount + int(amount * amt_mult)
            msg += f"You have won {tot_amt} {self.chip_emoji}"
            title = "Congratulations!"
            color = 5023308
            profile.credit(int(amount * amt_mult))
            won = True
        else:
            msg += f"You have lost {amount} {self.chip_emoji}"
            title = "You Lost!"
            color = 14155786
            profile.debit(amount)
            won = False
        Flips(
            message.author,
            amount, won
        ).save()
        emb = get_embed(msg, title=title, image=img, color=color)
        await opt_msg.edit(embed=emb, view=None)

    @model(Matches)
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
        matches = Matches.get_matches(limit=limit)
        embeds = []
        for match in matches:
            started_by = message.guild.get_member(
                int(match["started_by"])
            )
            played_at = match["played_at"]
            pot = match["deal_cost"] * len(match['participants'])
            parts = "\n".join(
                str(message.guild.get_member(int(plyr)))
                for plyr in match["participants"]
            )
            parts = f"```py\n{parts}\n```"
            winner = message.guild.get_member(int(match["winner"]))
            emb = get_embed(
                f"Match started by: **{started_by}**\n"
                f"Played on: **{played_at}**\n"
                f"Amount in pot: **{pot}** {self.chip_emoji}",
                title="Recent Matches"
            )
            emb.add_field(
                name="Participants",
                value=parts,
                inline=True
            )
            emb.add_field(
                name="Winner",
                value=f"**```{winner if winner else 'Not in Server'}```**",
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
            if winner:
                emb.set_image(url=winner.avatar.with_size(256))
            embeds.append(emb)
        await self.paginate(message, embeds)

    @model([Moles, Profiles])
    @alias(["mole", "whack", "moles"])
    @no_thumb
    @check_completion
    async def cmd_whackamole(self, message: Message, **kwargs):
        """Find the chip minigame.
        $```scss
        {command_prefix}whackamole [--difficulty number]
        ```$

        @Find the hidden chip for a chance to win a jackpot.
        If no amount is specified, 50 chips will be used by default.
        Minimum 50 chips and maximum 9999 chips can be used.
        You can choose difficulty level (default 1) and rewards will scale.
        ```py
        ╔═══════╦═══════╦══════╦════════╗
        ║ Level ║ Board ║ Cost ║ Reward ║
        ╠═══════╬═══════╬══════╬════════╣
        ║   1   ║  3x3  ║   50 ║   x3   ║
        ║   2   ║  4x4  ║  100 ║   x4   ║
        ║   3   ║  5x5  ║  150 ║   x10  ║
        ║   4   ║  6x6  ║  200 ║   x50  ║
        ║   5   ║  7x7  ║  250 ║   x100 ║
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
        boards = [
            f"{i + 3}x{i + 3}"
            for i in range(5)
        ]
        costs = [50, 100, 150, 200, 250]
        multipliers = [3, 4, 10, 50, 100]
        level = kwargs.get("difficulty", kwargs.get("level", 1))
        choice_view = SelectView(
            heading="Select the Level",
            options={
                (i + 1): f"Board: {boards[i]}\t"
                f"Cost: {costs[i]}\t"
                f"Reward Multiplier: x{multipliers[i]}"
                for i in range(5)
            },
            no_response=True,
            check=lambda x: x.user.id == message.author.id
        )
        level_inp = await message.reply(
            "Which difficulty do you wanna play in?",
            view=choice_view
        )
        await choice_view.dispatch(self)
        if not choice_view.result:
            return
        await level_inp.delete()
        level = choice_view.result - 1
        letters, numbers = self.boardgen.get_valids(level)
        cost = costs[level]
        multiplier = multipliers[level]
        profile = Profiles(message.author)
        if profile.get("balance") < cost:
            await self.handle_low_bal(message.author, message.channel)
            await message.add_reaction("❌")
            return
        board, board_img = self.boardgen.get_board(level)
        multi_select_view = MultiSelectView(
            kwarg_list=[
                {
                    "heading": "Select the Column",
                    "options": {
                        letter: ""
                        for letter in letters
                    }
                },
                {
                    "heading": "Select the Row",
                    "options": {
                        number: ""
                        for number in numbers
                    }
                }
            ],
            check=lambda x: x.user.id == message.author.id
        )
        emb = get_embed(
            title=f"**Difficulty: {level + 1} ({board})**",
            content="```\nChoose a tile.\n```",
            image=f"attachment://{board}.jpg"
        )
        emb.add_field(
            name="Cost",
            value=f"**{cost} {self.chip_emoji}**"
        )
        opt_msg = await message.reply(
            embed=emb,
            file=img2file(board_img, f"{board}.jpg"),
            view=multi_select_view
        )
        await multi_select_view.dispatch(self)
        if not multi_select_view.results:
            return
        choice = "".join(
            sorted(
                multi_select_view.results,
                reverse=True
            )
        )
        rolled, board_img = self.boardgen.get(level)
        await opt_msg.delete()
        if choice == rolled:
            content = "**Congratulations! You guessed it correctly.**\n" + \
                f"{cost * multiplier} {self.chip_emoji} " + \
                "have been added in your account."
            color = 5023308
            profile.credit(cost * multiplier)
            won = True
        else:
            content = "**Uhoh! You couldn't guess it right this time.**\n" + \
                f"{cost} {self.chip_emoji} " + \
                "have been taken from your account."
            color = 14155786
            profile.debit(cost)
            won = False
        Moles(
            message.author,
            cost, level, won
        ).save()
        await message.reply(
            embed=get_embed(
                content=content,
                color=color,
                image=f"attachment://{rolled}.jpg"
            ),
            file=img2file(board_img, f"{rolled}.jpg")
        )

    async def handle_low_bal(self, usr, gamble_channel):
        """Handle low balance."""
        low_bal_embed = get_embed(
            "Every user gets 100 chips as a starting bonus.\n"
            "You can buy more or exchange for other bot credits.",
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

    async def __flip_input_handler(
        self, message, args,
        profile, min_chips, max_chips
    ):
        amount = min_chips
        if args:
            proceed = await MinMaxValidator(
                min_chips, max_chips,
                message=message,
                dm_user=True
            ).validate(args[0])
            if not proceed:
                return None
            amount = int(args[0])
        if profile.get("balance") < amount:
            await self.handle_low_bal(message.author, message.channel)
            await message.add_reaction("❌")
            return None
        return amount

    def __gamble_charge_player(self, dealed_deck, fee):
        profiles = {}
        for player, _ in dealed_deck.items():
            profiles[str(player.id)] = profile = Profiles(player)
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

    async def __gamble_cleanup(
        self, gamble_thread,
        delay=30.0, completed=False
    ):
        await asyncio.sleep(delay)
        if gamble_thread:
            if completed:
                await gamble_thread.edit(
                    archived=True,
                    locked=True
                )
            else:
                await gamble_thread.delete()
            gamblers = self.__get_gambler_role(gamble_thread)
            await gamble_thread.parent.set_permissions(
                gamblers, send_messages=True
            )
        self.registered = []

    def __gamble_get_decks(self, num_cards, joker_chance):
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

    async def __gamble_register(self, message: Message, **kwargs):
        fee = kwargs["fee"]
        max_players = max(2, int(kwargs.pop("max_players", 12)))
        gamblers = self.__get_gambler_role(message.channel)
        await message.channel.set_permissions(
            gamblers, send_messages=False
        )
        gamble_thread = await message.channel.create_thread(
            name="gamble-here",
            message=message
        )
        rules = ', '.join(
            self.rules[key]
            for key in kwargs
            if key in self.rules.keys()
        ) or 'None'
        desc = (
            f"**Entry Fee**: {fee} {self.chip_emoji} "
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
        gamble_view = GambleCounter(
            self, gamble_thread,
            register_embed, fee,
            max_players
        )
        first_embed = register_embed.copy()
        first_embed.description = first_embed.description.replace("<tr>", "10")
        # Isolate the ping since it gets silenced on edit.
        cnt_msg = await message.channel.send(
            content=f"Hey {gamblers.mention}"
        )
        emb_msg = await message.channel.send(
            embed=first_embed,
            view=gamble_view
        )
        await gamble_view.dispatch(self)
        self.registered = gamble_view.registration_list
        await cnt_msg.delete()
        await emb_msg.delete()
        return gamble_thread, hot_time

    async def __gamble_handle_roll(
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

    async def __gamble_announce_winner(
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
            loot_table = Loots(winner)
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

    async def __gamble_handle_winner(
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
            await self.__gamble_announce_winner(
                gamble_channel, dealed_deck,
                winner, fee, profiles
            )
        )

    @staticmethod
    def __get_gambler_role(channel):
        return [
            role
            for role in channel.guild.roles
            if role.name.lower() == "gamblers"
        ][0]
