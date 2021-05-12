"""
Profile Commands Module
"""

# pylint: disable=unused-argument

from io import BytesIO

from PIL import Image

from ..helpers.imageclasses import (
    BadgeGenerator, LeaderBoardGenerator,
    ProfileCardGenerator, WalletGenerator
)
from ..helpers.utils import get_embed, get_profile, img2file
from .basecommand import Commands, alias


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
    async def cmd_profile(self, message, args=None, **kwargs):
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
            user = self.ctx.get_user(int(args[0]))
        elif kwargs["mentions"]:
            user = kwargs["mentions"][0].id
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
            num_played, num_won, badges
        )
        discord_file = img2file(profilecard, "profilecard.jpg")
        await message.channel.send(file=discord_file)

    @alias(["bal", "chips"])
    async def cmd_balance(self, message, **kwargs):
        """Check balance pokechips.
        $```scss
        {command_prefix}balance
        ```$

        @Quickly check how many <:pokechip:840469159242760203> you have.@

        ~To check your balance:
            ```
            {command_prefix}bal
            ```~
        """
        user = message.author
        profile = (await get_profile(self.database, message,  message.author)).get()
        data = {
            key: (
                f"{val:,}" if key in [
                    "won_chips", "purchased_chips", "balance"
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
    async def cmd_leaderboard(self, message, args=None, **kwargs):
        """Check the global leaderboard.
        $```scss
        {command_prefix}leaderboard
        ```$

        @Check the global PokeGambler leaderboard.
        By default, ranks are sorted according to number of wins.
        You can also sort it according to balance.@

        ~To check the leaderboard:
            ```
            {command_prefix}lb
            ```
        To check the leaderboard in terms of riches:
            ```
            {command_prefix}lb balance
            ```~
        """
        sort_by = "num_wins"
        if args and args[0].lower().startswith("bal"):
            sort_by = "balance"
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
    async def cmd_rank(self, message, **kwargs):
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
    async def cmd_badges(self, message, **kwargs):
        """Check Badge progress.
        $```scss
        {command_prefix}badge
        ```$

        @Check the list of available badges and what all you have unlocked.@

        ~To check your rank:
            ```
            {command_prefix}badge
            ```~
        """
        profile = await get_profile(self.database, message,  message.author)
        badges = profile.get_badges()
        badgestrip = self.bdgen.get(badges)
        discord_file = img2file(badgestrip, "badges.png", ext="PNG")
        await message.channel.send(file=discord_file)
