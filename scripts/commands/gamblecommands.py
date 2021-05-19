"""
Gambling Commands Module
"""

# pylint: disable=too-many-arguments, too-many-locals, unused-argument

import asyncio
import math
import random
from datetime import datetime

import discord
from scripts.base.items import Chest

from ..base.models import Flips, Loots, Matches, Moles, Profile
from ..helpers.checks import user_check, user_rctn
from ..helpers.imageclasses import BoardGenerator
from ..helpers.utils import (
    get_embed, get_enum_embed, get_formatted_time,
    img2file, wait_for
)
from .basecommand import Commands, alias, dealer_only, model


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
        if num_wins in [10, 100]:
            loot_table = Loots(self.database, winner)
            if num_wins == 10:
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

    @dealer_only
    @model([Profile, Matches, Loots])
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
            msg += f"You have won {amount * 2} <:pokechip:840469159242760203>"
            title = "Congratulations!"
            color = 5023308
            profile.update(
                balance=profile.get()["balance"] + amount,
                won_chips=profile.get()["won_chips"] + amount
            )
            won = True
        else:
            msg += f"You have lost {amount} <:pokechip:840469159242760203>"
            title = "You Lost!"
            color = 14155786
            profile.update(
                balance=profile.get()["balance"] - amount,
                won_chips=profile.get()["won_chips"] - amount
            )
            won = False
        Flips(
            self.database, message.author,
            amount, won
        ).save()
        emb = get_embed(msg, title=title, image=img, color=color)
        await opt_msg.edit(embed=emb)

    @model([Moles, Profile])
    @alias(["mole", "whack"])
    async def cmd_whackamole(self, message, args=None, **kwargs):
        """Find the chip minigame.
        $```scss
        {command_prefix}whackamole [--difficulty number]
        ```$

        @Find the hidden chip for a chance to win a jackpot.
        If no amount is specified, 50 chips will be used by default.
        Minimum 50 chips and maximim 9999 chips can be used.
        You can choose difficulty level (default 1) and rewards will scale.
        ```
        ╔═══════╦═══════╦══════╦════════╗
        ║ Level ║ Board ║ Cost ║ Reward ║
        ╠═══════╬═══════╬══════╬════════╣
        ║   1   ║  3x3  ║   50 ║   x3   ║
        ║   2   ║  4x4  ║  100 ║   x4   ║
        ║   3   ║  5x5  ║  150 ║   x6   ║
        ║   4   ║  6x6  ║  150 ║   x10  ║
        ║   5   ║  7x7  ║  150 ║   x20  ║
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
        cost = [50, 100, 150, 150, 150][level]
        multiplier = [3, 4, 6, 10, 20][level]
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
            profile.update(
                balance=profile.get()["balance"] + (cost * multiplier),
                won_chips=profile.get()["won_chips"] + (cost * multiplier)
            )
            won = True
        else:
            content = "**Uhoh! You couldn't guess it right this time.**\n" + \
                f"{cost} <:pokechip:840469159242760203> " + \
                "have been taken from your account."
            color = 14155786
            profile.update(
                balance=profile.get()["balance"] - cost,
                won_chips=profile.get()["won_chips"] - cost
            )
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

    @model([Loots, Profile, Chest])
    @alias('lt')
    async def cmd_loot(self, message, **kwargs):
        """Stable source of Pokechips.
        $```scss
        {command_prefix}loot
        ```$

        @Search the void for free <:pokechip:840469159242760203>.
        The number of chips is randomly choosen from 5 to 10.
        `Chip Amount Boost incoming soon`
        `BETA boost is current active: x2 chips`
        There is a cooldown of 10 minutes between loots.
        `Cooldown Reduction Boost incoming soon`@
        """
        on_cooldown = self.ctx.loot_cd.get(message.author, None)
        cd_time = 600
        if on_cooldown and (
            datetime.now() - self.ctx.loot_cd[message.author]
        ).total_seconds() < cd_time:
            time_remaining = get_formatted_time(
                cd_time - (
                    datetime.now() - self.ctx.loot_cd[message.author]
                ).total_seconds(),
                show_hours=False
            )
            await message.add_reaction("⌛")
            await message.channel.send(
                content=str(message.author.mention),
                embed=get_embed(
                    f"Please wait {time_remaining} before looting again.",
                    embed_type="warning",
                    title="On Cooldown"
                )
            )
            return
        self.ctx.loot_cd[message.author] = datetime.now()
        profile = Profile(self.database, message.author)
        loot_model = Loots(self.database, message.author)
        loot_info = loot_model.get()
        boost = loot_info["loot_boost"]
        earned = loot_info["earned"]
        tier = loot_info["tier"]
        treasure_chance = 0.01 * loot_info["treasure_boost"]
        loot = random.randint(5, 10) * boost * (10 ** (tier - 1))
        loot *= 2  # x2 BETA Bonus
        treasure_chance *= 2 # x2 BETA Bonus
        embed = None
        proc = random.uniform(0, 1.0)
        if proc <= treasure_chance:
            chest = Chest.get_chest(tier=tier)
            chest.save(self.database)
            embed = get_embed(
                f"Woah! You got lucky and found a **{chest}**.\n"
                "It's been added to your inventory.",
                title="**FOUND A TREASURE CHEST**",
                thumbnail=chest.asset_url
            )
        data = profile.get()
        balance = data["balance"] + loot
        won_chips = data["won_chips"] + loot
        profile.update(balance=balance, won_chips=won_chips)
        loot_model.update(earned=earned + loot)
        await message.channel.send(
            f"**You found {loot} <a:blinker:843844481220083783>! "
            "Added to your balance.**",
            embed=embed
        )

    @model([Loots, Profile, Chest])
    @alias('dl')
    async def cmd_daily(self, message, **kwargs):
        """Daily source of Pokechips.
        $```scss
        {command_prefix}daily
        ```$

        @Claim free <:pokechip:840469159242760203> and a chest everyday.
        The chips and the chest both scale with Tier.
        There are 3 tiers:
            1 - Everyone starts here.
            2 - Win 10 gamble matches.
            3 - Win 100 gamble matches.
        You can maintain a daily streak. Get 1K chips for every 5 day streak.
        `BETA boost is current active: x2 chips`@
        """
        profile = Profile(self.database, message.author)
        loot_model = Loots(self.database, message.author)
        loot_info = loot_model.get()
        boost = loot_info["loot_boost"]
        earned = loot_info["earned"]
        tier = loot_info["tier"]
        daily_streak = loot_info["daily_streak"]
        last_claim = loot_info["daily_claimed_on"]
        cd_time = 24 * 60 * 60
        if (
            datetime.now() - last_claim
        ).total_seconds() < cd_time:
            time_remaining = get_formatted_time(
                cd_time - (
                    datetime.now() - last_claim
                ).total_seconds()
            )
            await message.add_reaction("⌛")
            await message.channel.send(
                content=str(message.author.mention),
                embed=get_embed(
                    f"Please wait {time_remaining} before claiming Daily.",
                    embed_type="warning",
                    title="Too early"
                )
            )
            return
        if (
            datetime.now() - last_claim
        ).total_seconds() >= (cd_time * 2):
            # Reset streak on missing by a day
            daily_streak = 0
        else:
            daily_streak += 1
        loot = random.randint(5, 10) * boost * (10 ** tier)
        if daily_streak % 5 == 0 and daily_streak > 0:
            loot += 1000
        loot *= 2  # x2 BETA Bonus
        chest = Chest.get_chest(tier=tier)
        chest.description += f"\n[Daily for {message.author.id}]"
        chest.save(self.database)
        embed = get_embed(
            f"Here's your daily **{chest}**.\n"
            f"Claim the chest with `{self.ctx.prefix}open {chest.itemid}`.\n"
            "(Daily Chests are not stored in the inventory.)",
            title="**Daily Chest**",
            thumbnail=chest.asset_url,
            footer=f"Current Streak: {daily_streak}"
        )
        data = profile.get()
        balance = data["balance"] + loot
        won_chips = data["won_chips"] + loot
        profile.update(balance=balance, won_chips=won_chips)
        loot_model.update(
            earned=(earned + loot),
            daily_streak=daily_streak,
            daily_claimed_on=datetime.today().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
        await message.channel.send(
            f"**Daily loot of {loot} <a:blinker:843844481220083783> "
            "added to your balance.**",
            embed=embed
        )

    @model([Loots, Profile, Chest])
    @alias("chest")
    async def cmd_open(self, message, args=None, **kwargs):
        """Opens a PokeGambler treasure chest.
        $```scss
        {command_prefix}open chest_id
        ```$

        @Opens a treasure chest that you own.
        There are 3 different chests and scale with your tier.
        Here's a drop table:
        ```py
        ╔══════╦═══════════╦═══════════╦══════════════╗
        ║ Tier ║   Chest   ║ Drop Rate ║  Pokechips   ║
        ╠══════╬═══════════╬═══════════╬══════════════╣
        ║   1  ║  Common   ║    66%    ║   34 - 191   ║
        ║   2  ║   Gold    ║    25%    ║  192 - 1110  ║
        ║   3  ║ Legendary ║     9%    ║ 1111 - 10000 ║
        ╚══════╩═══════════╩═══════════╩══════════════╝
        ```@

        ~To open a chest with ID 0000FFFF:
            ```
            {command_prefix}open 0000FFFF
            ```~
        """
        if not args:
            return
        try:
            itemid = int(args[0], 16)
            chest = Chest.from_id(self.database, itemid)
        except (ValueError, ZeroDivisionError):
            chest = None
        if not chest:
            await message.channel.send(
                embed=get_embed(
                    "Make sure you actually own this chest.",
                    embed_type="error",
                    title="Invalid Chest ID"
                )
            )
            return
        if str(message.author.id) not in chest.description:
            print(chest.description)
            await message.channel.send(
                embed=get_embed(
                    "That's not your own chest.",
                    embed_type="error",
                    title="Invalid Chest ID"
                )
            )
            return
        chips = chest.chips
        profile = Profile(self.database, message.author)
        data = profile.get()
        won_chips = data["won_chips"]
        balance = data["balance"]
        profile.update(
            won_chips=(won_chips + chips),
            balance=(balance + chips)
        )
        loot_model = Loots(self.database, message.author)
        earned = loot_model.get()["earned"]
        loot_model.update(
            earned=(earned + chips)
        )
        content = f"You have recieved {chips} <:pokechip:840469159242760203>."
        if chest.name == "Legendary Chest":
            item = chest.get_random_collectible()
            if item:
                content += f"\nAnd woah, you also got a {item}!"
            # Add logic for collectible in inventory.
        chest.delete(self.database)
        await message.channel.send(
            embed=get_embed(
                content,
                title=f"Opened a {chest.name}"
            )
        )
