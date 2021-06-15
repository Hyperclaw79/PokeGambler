"""
Profile Commands Module
"""

# pylint: disable=unused-argument, too-many-locals

from __future__ import annotations
import random
from datetime import datetime, timedelta
from io import BytesIO
from typing import Dict, List, Optional, TYPE_CHECKING

from PIL import Image

from ..base.items import Chest
from ..base.models import (
    Boosts, Inventory, Loots, Matches,
    Minigame, Profile
)
from ..base.shop import BoostItem

from ..helpers.imageclasses import (
    BadgeGenerator, LeaderBoardGenerator,
    ProfileCardGenerator, WalletGenerator
)
from ..helpers.utils import (
    get_embed, get_formatted_time,
    get_modules, img2file
)
from .basecommand import (
    Commands, alias,
    model, get_profile
)

if TYPE_CHECKING:
    from discord import Message, Member


class ProfileCommands(Commands):
    """
    Commands that deal with the profile system of PokeGambler.
    One of the most feature rich command category.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pcg = ProfileCardGenerator(self.ctx.assets_path)
        self.walletgen = WalletGenerator(self.ctx.assets_path)
        self.lbg = LeaderBoardGenerator(self.ctx.assets_path)
        self.bdgen = BadgeGenerator(self.ctx.assets_path)

    @alias("pr")
    async def cmd_profile(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):
        """The profile command.
        $```scss
        {command_prefix}profile [id/mention]
        ```$

        @Check your or someone's PokeGambler profile.
        To check someone's profile, provide their ID or mention them.@

        ~To check your own profile:
            ```
            {command_prefix}profile
            ```
        To check Alan's profile:
            ```
            {command_prefix}pr @Alan#1234
            ```~
        """
        if args:
            user = message.guild.get_member(int(args[0]))
        elif kwargs["mentions"]:
            user = kwargs["mentions"][0]
        else:
            user = message.author
        profile = await get_profile(self.database, message, user)
        if not profile:
            return
        badges = profile.get_badges()
        profile = profile.get()
        avatar_byio = BytesIO()
        await user.avatar_url_as(size=512).save(avatar_byio)
        avatar = Image.open(avatar_byio)
        name = profile["name"]
        balance = f'{profile["balance"]:,}'
        num_played = str(profile["num_matches"])
        num_won = str(profile["num_wins"])
        profilecard = self.pcg.get(
            name, avatar, balance,
            num_played, num_won, badges,
            blacklisted=self.database.is_blacklisted(
                str(user.id)
            )
        )
        discord_file = img2file(profilecard, "profilecard.jpg")
        await message.channel.send(file=discord_file)

    @alias(["bal", "chips"])
    async def cmd_balance(self, message: Message, **kwargs):
        """Check balance pokechips.
        $```scss
        {command_prefix}balance
        ```$

        @Quickly check how many {pokechip_emoji} you have.@

        ~To check your balance:
            ```
            {command_prefix}bal
            ```~
        """
        user = message.author
        profile = (
            await get_profile(self.database, message,  message.author)
        ).get()
        data = {
            key: (
                f"{val:,}" if key in [
                    "won_chips", "pokebonds", "balance"
                ]
                else str(val)
            )
            for key, val in profile.items()
        }
        wallet = self.walletgen.get(data)
        discord_file = img2file(wallet, "wallet.png", ext="PNG")
        await message.channel.send(
            content=user.mention,
            file=discord_file
        )

    @alias("lb")
    async def cmd_leaderboard(
        self, message: Message,
        args: Optional[List] = None,
        **kwargs
    ):

        # pylint: disable=too-many-locals

        """Check the global leaderboard.
        $```scss
        {command_prefix}leaderboard [balance/minigame]
        ```$

        @Check the global PokeGambler leaderboard.
        By default, ranks are sorted according to number of wins.
        You can also sort it according to balance and any minigame.@

        ~To check the leaderboard:
            ```
            {command_prefix}lb
            ```
        To check the leaderboard in terms of riches:
            ```
            {command_prefix}lb balance
            ```
        To check the leaderboard for QuickFlip:
            ```
            {command_prefix}lb flip
            ```~
        """
        if args and not args[0].lower().startswith("bal"):
            lbrd = self.__get_minigame_lb(
                args[0].lower(),
                message.author
            )
            if lbrd is None:
                await message.channel.send(
                    embed=get_embed(
                        "You can choose a minigame name or 'balance'.",
                        embed_type="error",
                        title="Invalid Input"
                    )
                )
                return
            leaderboard = []
            lbrd = [
                (
                    message.guild.get_member(int(res[0])), *res[1:]
                )
                for res in lbrd
                if message.guild.get_member(int(res[0]))
            ]
            for idx, res in enumerate(lbrd):
                rank = idx + 1
                earned = None
                if len(res) == 4:
                    member, num_matches, num_wins, earned = res
                else:
                    member, num_matches, num_wins = res
                profile = Profile(self.database, member).get()
                balance = earned or profile["balance"]
                name = profile["name"]
                leaderboard.append({
                    "rank": rank,
                    "user_id": member.id,
                    "name": name,
                    "num_matches": num_matches,
                    "num_wins": num_wins,
                    "balance": balance
                })
        else:
            sort_by = "num_wins" if not args else "balance"
            leaderboard = self.database.get_leaderboard(sort_by=sort_by)
        if not leaderboard:
            await message.channel.send(
                embed=get_embed(
                    "No matches were played yet.",
                    embed_type="warning"
                )
            )
            return
        leaderboard = leaderboard[:12]
        for idx, data in enumerate(leaderboard):
            data["rank"] = idx + 1
            data["balance"] = f'{data["balance"]:,}'
        for i in range(0, len(leaderboard), 4):
            batch_4 = leaderboard[i: i + 4]
            img = await self.lbg.get(self.ctx, batch_4)
            await message.channel.send(
                file=img2file(img, f"leaderboard{i}.jpg")
            )

    @alias("#")
    async def cmd_rank(self, message: Message, **kwargs):
        """Check user rank.
        $```scss
        {command_prefix}rank
        ```$

        @Creates your PokeGambler Rank card.
        Rank is decided based on number of wins.@

        ~To check your rank:
            ```
            {command_prefix}rank
            ```~
        """
        profile = await get_profile(self.database, message,  message.author)
        data = profile.get()
        rank = self.database.get_rank(str(message.author.id))
        data["rank"] = rank or 0
        data["balance"] = f'{data["balance"]:,}'
        img = await self.lbg.get_rankcard(self.ctx, data, heading=True)
        discord_file = img2file(img, "rank.png", ext="PNG")
        await message.channel.send(file=discord_file)

    @alias("bdg")
    async def cmd_badges(self, message: Message, **kwargs):
        """Check Badge progress.
        $```scss
        {command_prefix}badges
        ```$

        @Check the list of available badges and what all you have unlocked.@

        ~To check your rank:
            ```
            {command_prefix}badges
            ```~
        """
        profile = await get_profile(self.database, message,  message.author)
        badges = profile.get_badges()
        badgestrip = self.bdgen.get(badges)
        discord_file = img2file(badgestrip, "badges.png", ext="PNG")
        await message.channel.send(file=discord_file)

    async def cmd_stats(self, message: Message, **kwargs):
        """Check match and minigame stats.
        $```scss
        {command_prefix}stats
        ```$

        @Check the number of gamble matches & minigames you've played and won.@

        ~To check your rank:
            ```
            {command_prefix}stats
            ```~
        """
        match_stats = Matches(
            self.database, message.author
        ).get_stats()
        stat_dict = {
            "Gamble Matches": f"Played: {match_stats[0]}\n"
            f"Won: {match_stats[1]}"
        }
        for minigame_cls in Minigame.__subclasses__():
            minigame = minigame_cls(self.database, message.author)
            stat_dict[
                minigame_cls.__name__
            ] = f"Played: {minigame.num_plays}\n" + \
                f"Won: {minigame.num_wins}"
        emb = get_embed(
            "Here's how you've performed till now.",
            title=f"Statistics for **{message.author.name}**"
        )
        for key, val in stat_dict.items():
            emb.add_field(
                name=f"**{key}**",
                value=f"```rb\n{val}\n```",
                inline=False
            )
        await message.channel.send(embed=emb)

    @model([Loots, Profile, Chest, Inventory])
    @alias('lt')
    async def cmd_loot(self, message: Message, **kwargs):
        """Stable source of Pokechips.
        $```scss
        {command_prefix}loot
        ```$

        @Search the void for free {pokechip_emoji}.
        The number of chips is randomly choosen from 5 to 10.
        `Chip Amount Boost incoming soon`
        `BETA boost is current active: x2 chips`
        There is a cooldown of 10 minutes between loots.
        `Cooldown Reduction Boost incoming soon`@
        """
        on_cooldown = self.ctx.loot_cd.get(message.author, None)
        perm_boosts = Boosts(
            self.database, message.author
        ).get()
        loot_mult = 1 + (perm_boosts["lucky_looter"] * 0.05)
        cd_reducer = perm_boosts["loot_lust"]
        tr_mult = 0.1 * perm_boosts["fortune_burst"]
        boosts = self.ctx.boost_dict.get(message.author.id, None)
        if boosts:
            cd_reducer += boosts['boost_lt_cd']['stack']
            loot_mult += 0.05 * boosts['boost_lt']['stack']
            tr_mult += 0.1 * boosts['boost_tr']['stack']
        cd_time = 60 * (10 - cd_reducer)
        loot_cd = self.ctx.loot_cd.get(
            message.author,
            datetime.now() - timedelta(minutes=10)
        )
        elapsed = (
            datetime.now() - loot_cd
        ).total_seconds()
        if on_cooldown and elapsed < cd_time:
            time_remaining = get_formatted_time(
                cd_time - elapsed,
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
        earned = loot_info["earned"]
        tier = loot_info["tier"]
        loot = int(
            random.randint(5, 10) * (
                10 ** (tier - 1)
            ) * loot_mult
        )
        loot *= 2  # BETA x2 Bonus
        tr_mult *= 2  # BETA x2 Bonus
        embed = None
        proc = random.uniform(0, 1.0)
        if proc <= tr_mult:
            chest = Chest.get_chest(tier=tier)
            chest.save(self.database)
            Inventory(self.database, message.author).save(
                int(chest.itemid, 16)
            )
            embed = get_embed(
                f"Woah! You got lucky and found a **{chest}**.\n"
                "It's been added to your inventory.",
                title="**FOUND A TREASURE CHEST**",
                thumbnail=chest.asset_url,
                footer=f"Chest ID: {chest.itemid}"
            )
        profile.credit(loot)
        loot_model.update(earned=earned + loot)
        await message.channel.send(
            f"**You found {loot} <a:blinker:843844481220083783>! "
            "Added to your balance.**",
            embed=embed
        )

    @model([Loots, Profile, Chest, Inventory])
    @alias('dl')
    async def cmd_daily(self, message: Message, **kwargs):
        """Daily source of Pokechips.
        $```scss
        {command_prefix}daily
        ```$

        @Claim free {pokechip_emoji} and a chest everyday.
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
        boost_model = Boosts(self.database, message.author)
        loot_info = loot_model.get()
        boost_info = boost_model.get()
        boost = boost_info["lucky_looter"] + 1
        earned = loot_info["earned"]
        tier = loot_info["tier"]
        daily_streak = loot_info["daily_streak"]
        last_claim = loot_info["daily_claimed_on"]
        if isinstance(last_claim, str):
            last_claim = datetime.strptime(
                last_claim,
                "%Y-%m-%d %H:%M:%S"
            )
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
            loot += 100 * (daily_streak / 5)
        loot *= 2  # BETA x2 Bonus
        chest = Chest.get_chest(tier=tier)
        chest.description += f"\n[Daily for {message.author.id}]"
        chest.save(self.database)
        Inventory(self.database, message.author).save(
            int(chest.itemid, 16)
        )
        embed = get_embed(
            f"Here's your daily **{chest}**.\n"
            f"Claim the chest with `{self.ctx.prefix}open {chest.itemid}`.",
            title="**Daily Chest**",
            thumbnail=chest.asset_url,
            footer=f"Current Streak: {daily_streak}"
        )
        profile.credit(int(loot))
        loot_model.update(
            earned=(earned + loot),
            daily_streak=daily_streak,
            daily_claimed_on=datetime.today().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
        await message.channel.send(
            f"**Daily loot of {int(loot)} <a:blinker:843844481220083783> "
            "added to your balance.**",
            embed=embed
        )

    @model(Boosts)
    async def cmd_boosts(self, message: Message, **kwargs):
        """Check active boosts.
        $```scss
        {command_prefix}boosts
        ```$

        @Check your active purchased boosts.@
        """
        def __get_desc(boost):
            prm_bst = perm_boosts[boost['name'].lower().replace(' ', '_')]
            total = boost['stack'] + prm_bst
            desc_str = f"{boost['description']}\nStack: {total}"
            if prm_bst > 0:
                desc_str += f" ({prm_bst} Permanent)"
            expires_in = (30 * 60) - (
                datetime.now() - boost["added_on"]
            ).total_seconds()
            if expires_in > 0 and boost['stack'] > 0:
                expires_in = get_formatted_time(
                    expires_in, show_hours=False
                ).replace('**', '')
            else:
                expires_in = "Expired / Not Purchased Yet"
            desc_str += f"\nExpires in: {expires_in}"
            return f"```css\n{desc_str}\n```"
        boosts = self.ctx.boost_dict.get(message.author.id, None)
        perm_boosts = Boosts(self.database, message.author).get()
        if not (
            boosts or any(
                bst > 1
                for bst in perm_boosts.values()
            )
        ):
            await message.channel.send(
                embed=get_embed(
                    "You don't have any active boosts.",
                    title="No Boosts"
                )
            )
            return
        emb = get_embed(
            "\u200B",
            title="Active Boosts"
        )
        if not boosts:
            boosts = BoostItem.create_boost_dict()
        for val in boosts.values():
            emb.add_field(
                name=val["name"],
                value=__get_desc(val),
                inline=False
            )
        await message.channel.send(embed=emb)

    def __get_minigame_lb(self, mg_name: str, user: Member) -> List[Dict]:
        def _commands(module):
            return [
                attr.replace("cmd_", "")
                for attr in dir(module)
                if all([
                    attr.startswith("cmd_"),
                    attr not in getattr(module, "alias", [])
                ])
            ]

        def _aliases(module):
            return [
                alias.replace("cmd_", "")
                for alias in getattr(module, "alias", [])
            ]

        def _get_lb(modules, mg_name, user):
            leaderboard = None
            for module in modules:
                if mg_name in _aliases(module) + _commands(module):
                    command = getattr(module, f"cmd_{mg_name}")
                    models = getattr(command, "models", [])
                    if not models:
                        continue
                    for model_ in models:
                        if issubclass(model_, Minigame):
                            leaderboard = model_(
                                self.database, user
                            ).get_lb()
                            return leaderboard
            return leaderboard
        modules = get_modules(self.ctx)
        return _get_lb(modules, mg_name, user)
