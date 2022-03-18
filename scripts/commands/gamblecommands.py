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

# pylint: disable=too-many-arguments, too-many-locals
# pylint: disable=too-many-instance-attributes, unused-argument

from __future__ import annotations
import asyncio
import math
import random
from typing import Optional, TYPE_CHECKING

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
    dealer_only, model
)

if TYPE_CHECKING:
    from discord import Message


class GambleCommands(Commands):
    """
    | Gamble Commands are the core commands for PokeGambler.
    | Currently, the only available command is the Gamble command itself.
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
        fee: Optional[int] = 50,
        lower_wins: Optional[bool] = False,
        max_players: Optional[int] = None,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param fee: The fee to be charged for the gamble.
        :type fee: Optional[int]
        :default fee: 50
        :min_value fee: 50
        :param lower_wins: Whether or not the lower number card wins.
        :type lower_wins: Optional[bool]
        :default lower_wins: False
        :param max_players: The maximum number of players allowed.
        :type max_players: Optional[int]

        .. meta::
            :description: The core command of the bot - Gamble.
            :alises: [deal, roll]

        .. rubric:: Syntax
        .. code:: coffee

            /gamble [fee:chips] [lower_wins:True/False] [max_players:number]

        .. rubric:: Description

        ``🎲 Dealer Command``
        Roll random pokemon themed cards for a fee and winner takes it all.
        If a fee is not specified, defaults to 50 {pokechip_emoji}.
        To make the lower card win, use the option lower_wins.

        .. note::
            A small transaction fees will be levyed before
            crediting the winner.
            This fee scales with number of players, if above 15.

        .. rubric:: Examples

        * To gamble with default settings

        .. code:: coffee
            :force:

            /gamble

        * To gamble for 1000 {pokechip_emoji}

        .. code:: coffee
            :force:

            /gamble fee:1000

        * To gamble in lower_wins mode

        .. code:: coffee
            :force:

            /gamble lower_wins:True
        """
        kwargs.pop("mentions", [])
        kwargs.update({
            "fee": fee,
            "lower_wins": lower_wins,
            "max_players": max_players
        })
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
                started_by=message.author,
                participants=profiles,
                winner=winner,
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
        amount: Optional[int] = 50,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param amount: The amount to use for the flip.
        :type amount: Optional[int]
        :default amount: 50
        :min_value amount: 50
        :max_value amount: 9999

        .. meta::
            :description: Head/Tails coinflip for PokeGambler.

        .. rubric:: Syntax
        .. code:: coffee

            /quickflip [amount:chips]

        .. rubric:: Description

        .. role:: spoiler
            :class: spoiler

        A quick way to x2 your pokechips :spoiler:`(or halve it)`.
        If no amount is specified, 50 chips will be used by default.
        Minimum 50 chips and maximum 9999 chips can be used.

        .. rubric:: Examples

        * To flip for 50 {pokechip_emoji}

        .. code:: coffee
            :force:

            /flip

        * To flip for 1000 {pokechip_emoji}

        .. code:: coffee
            :force:

            /flip amount:1000
        """
        profile = Profiles(message.author)
        amount = await self.__flip_input_handler(
            message, amount, profile,
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
        quantity: Optional[int] = 10,
        verbose: Optional[bool] = False,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param quantity: The number of matches to show.
        :type quantity: Optional[int]
        :default quantity: 10
        :min_value quantity: 1
        :max_value quantity: 50
        :param verbose: Whether to show the full match details.
        :type verbose: Optional[bool]
        :default verbose: False

        .. meta::
            :description: Lists latest gamble matches.

        .. rubric:: Syntax
        .. code:: coffee

            /matches [quantity:number] [verbose:True/False]

        .. rubric:: Description

        Lists out the results of latest gamble matches.
        If no quantity is given, defaults to 10.
        If verbose option is used, lists the mode and if joker spawned.

        .. rubric:: Examples

        * To list latest matches

        .. code:: coffee
            :force:

            /matches

        * To list latest 5 matches

        .. code:: coffee
            :force:

            /matches quantity:5

        * To see if Joker spawned in last 5 matches

        .. code:: coffee
            :force:

            /matches quantity:5 verbose:True
        """
        matches = Matches.get_matches(limit=quantity)
        embeds = []
        for match in matches:
            started_by = match["started_by"]["name"]
            played_at = match["played_at"]
            pot = match["deal_cost"] * len(match['participants'])
            parts = "\n".join(
                plyr["name"] or "Unknown"
                for plyr in match["participants"]
            )
            parts = f"```py\n{parts}\n```"
            winner = match["winner"]
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
            winner_name = winner['name'] if winner else 'Not in Server'
            emb.add_field(
                name="Winner",
                value=f"**```{winner_name}```**",
                inline=True
            )
            emb.add_field(
                name="\u200B",
                value="\u200B",
                inline=True
            )
            if verbose:
                emb.add_field(
                    name="Lower Wins",
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
            winner = self.ctx.get_user(winner['id'])
            if winner:
                emb.set_image(
                    url=winner.display_avatar.with_size(256)
                )
            embeds.append(emb)
        await self.paginate(message, embeds)

    @model([Moles, Profiles])
    @alias(["mole", "whack", "moles"])
    @check_completion
    async def cmd_whackamole(
        self, message: Message,
        difficulty: Optional[int] = None,
        **kwargs
    ):
        """
        :param message: The message which triggered this command.
        :type message: :class:`discord.Message`
        :param difficulty: The level at which you wanna play.
        :type difficulty: Optional[int]
        :default difficulty: None
        :min_value difficulty: 1
        :max_value difficulty: 5

        .. meta::
            :description: A minigame where you guess chip location.
            :aliases: mole, whack, moles

        .. rubric:: Syntax
        .. code:: coffee

            /mole [difficulty:level]

        .. rubric:: Description
        .. code:: py

            Find the hidden chip for a chance to win a jackpot.
            If no amount is specified, 50 chips will be used by default.
            Minimum 50 chips and maximum 9999 chips can be used.
            You can choose difficulty level (default 1) and rewards will scale.

            ╔═══════╦═══════╦══════╦════════╗
            ║ Level ║ Board ║ Cost ║ Reward ║
            ╠═══════╬═══════╬══════╬════════╣
            ║   1   ║  3x3  ║   50 ║   x3   ║
            ║   2   ║  4x4  ║  100 ║   x4   ║
            ║   3   ║  5x5  ║  150 ║   x10  ║
            ║   4   ║  6x6  ║  200 ║   x50  ║
            ║   5   ║  7x7  ║  250 ║   x100 ║
            ╚═══════╩═══════╩══════╩════════╝

        .. rubric:: Examples

        * To play with the default difficulty (level 1)

        .. code:: coffee
            :force:

            /mole

        * To play the extreme mode (level 5)

        .. code:: coffee
            :force:

            /mole difficulty:5
        """
        boards = [
            f"{i + 3}x{i + 3}"
            for i in range(5)
        ]
        costs = [50, 100, 150, 200, 250]
        multipliers = [3, 4, 10, 50, 100]
        if not difficulty:
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
            level = choice_view.result
        else:
            level = difficulty
        level -= 1
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
            file=img2file(board_img, f"{rolled}.jpg"),
            view=multi_select_view
        )

    @staticmethod
    async def handle_low_bal(usr, gamble_channel):
        """Handle low balance.

        :meta private:
        """
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
        self, message, amount,
        profile, min_chips, max_chips
    ):
        if amount:
            proceed = await MinMaxValidator(
                min_chips, max_chips,
                message=message,
                dm_user=True
            ).validate(amount)
            if not proceed:
                return None
            amount = int(amount)
        else:
            amount = min_chips
        if profile.get("balance") < amount:
            await self.handle_low_bal(message.author, message.channel)
            await message.add_reaction("❌")
            return None
        return amount

    def __gamble_charge_player(self, dealed_deck, fee):
        profiles = {}
        for player, _ in dealed_deck.items():
            profiles[player] = profile = Profiles(player)
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
        try:  # Interaction Messages can't be used for creating threads.
            gamble_thread = await message.channel.create_thread(
                name="gamble-here",
                message=message
            )
        except discord.HTTPException:
            msg = await message.channel.send("Starting Gamble....")
            gamble_thread = await message.channel.create_thread(
                name="gamble-here",
                message=msg
            )
        rules = ', '.join(
            self.rules[key]
            for key in kwargs
            if key in self.rules
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
        profile = profiles[winner]
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
        if num_wins == 25:
            loot_table = Loots(winner)
            loot_table.update(tier=2)
        elif num_wins == 100:
            loot_table = Loots(winner)
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
            idx = 0
            # Push all non-reactors to the bottom.
            while self.conv_table[players[0][1]['card_num']] == 0:
                players.append(players.pop(0))
                idx += 1
                # Rare case where no one reacts
                if idx == len(players):
                    break
        winner = next(
            (
                player[0]
                for player in players
                if player[1]["card_num"] == "Joker"
            ), None
        )

        if winner is None:
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
