"""
PRofile Commands Module
"""

# pylint: disable=unused-argument

from io import BytesIO

import discord
from PIL import Image

from ..helpers.utils import (
    get_embed, img2file
)
from ..helpers.imageclasses import (
    ProfileCardGenerator, WalletGenerator,
    LeaderBoardGenerator, BadgeGenerator
)
from .basecommand import (
    admin_only, owner_only, alias, Commands
)


class Profile:
    """
    Wrapper for Profile based DB actions.
    """
    def __init__(self, database, user):
        self.database = database
        self.user = user
        profile = self.database.get_profile(str(user.id))
        if not profile:
            self.create()
        else:
            self.profile = profile

    def __default(self):
        self.profile = {
            "user_id": str(self.user.id),
            "name": self.user.name,
            "balance": 100,
            "num_matches": 0,
            "num_wins": 0,
            "purchased_chips": 0,
            "won_chips": 0,
            "is_dealer": "dealers" in [
                role.name.lower()
                for role in self.user.roles
            ]
        }

    def create(self):
        """
        Creates a new profile for the user.
        """
        self.__default()
        self.database.create_profile(**self.profile)

    def update(self, **kwargs):
        """
        Updates an existing user profile.
        """
        if kwargs:
            self.profile.update(kwargs)
            self.database.update_profile(str(self.user.id), **kwargs)

    def reset(self):
        """
        Resets a user's profile to the default values.
        """
        self.__default()
        profile = {**self.profile}
        profile.pop("user_id")
        self.database.update_profile(str(self.user.id), **profile)

    def get(self):
        """
        Converts and returns the user profile as a dictionary.
        """
        return {**self.profile}

    def get_badges(self):
        """
        Computes the Badges unlocked by the user.
        """
        badges = []
        if self.database.is_champion(str(self.user.id)):
            badges.append("champion")
        if self.database.is_emperor(str(self.user.id)):
            badges.append("emperor")
        if self.database.is_top_funder(str(self.user.id)):
            badges.append("funder")
        if self.profile["is_dealer"]:
            badges.append("dealer")
        return badges


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

    async def __get_profile(self, message, user_id):
        try:
            user = message.guild.get_member(user_id)
            if not user:
                await message.channel.send(
                    embed=get_embed(
                        "Could not retrieve the user.",
                        embed_type="error",
                        title="User not found"
                    )
                )
                return None
            return Profile(self.database, user)
        except discord.HTTPException:
            await message.channel.send(
                embed=get_embed(
                    "Could not retrieve the user.",
                    embed_type="error",
                    title="User not found"
                )
            )
            return None

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
        user = message.author
        if any([args, kwargs["mentions"]]):
            if kwargs["mentions"]:
                user = kwargs["mentions"][0]
                profile = Profile(self.database, user)
            else:
                user = self.ctx.get_user(int(args[0]))
                profile = await self.__get_profile(message, int(args[0]))
                if not profile:
                    return
        else:
            profile = Profile(self.database, message.author)
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
        profile = Profile(self.database, message.author).get()
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
        profile = Profile(self.database, message.author)
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
        profile = Profile(self.database, message.author)
        badges = profile.get_badges()
        badgestrip = self.bdgen.get(badges)
        discord_file = img2file(badgestrip, "badges.png", ext="PNG")
        await message.channel.send(file=discord_file)

    @admin_only
    async def cmd_update_balance(self, message, args=None, **kwargs):
        """Updates user's balance.
        $```scss
        {command_prefix}update_balance user_id balance
        ```$

        @`🛡️ Admin Command`
        Overwrite a user's account balance.@

        ~To overwrite balance of user with ID 12345:
            ```
            {command_prefix}update_balance 12345 100
            ```~
        """
        if not args:
            await message.channel.send(
                embed=get_embed(
                    "You need to provide a user ID.",
                    embed_type="error",
                    title="No User ID"
                )
            )
            return
        if len(args) < 2:
            await message.channel.send(
                embed=get_embed(
                    "You need to provide a user ID and balance.",
                    embed_type="error",
                    title="Not enough args"
                )
            )
            return
        user_id = int(args[0])
        try:
            balance = int(args[1])
        except ZeroDivisionError:
            await message.channel.send(
                embed=get_embed(
                    "Good try but bad luck.",
                    embed_type="error",
                    title="Invalid input"
                )
            )
            return
        profile = await self.__get_profile(message, user_id)
        if not profile:
            return
        profile.update(balance=balance)
        await message.add_reaction("👍")

    @admin_only
    async def cmd_add_chips(self, message, args=None, **kwargs):
        """Adds chips to user's balance.
        $```scss
        {command_prefix}add_chips user_id amount [--purchased]
        ```$

        @`🛡️ Admin Command`
        Adds <:pokechip:840469159242760203> to a user's account.
        Use the `--purchased` kwarg if the chips were bought.@

        ~To give 50 <:pokechip:840469159242760203> to user with ID 12345:
            ```
            {command_prefix}add_chips 12345 50
            ```
        To add 500 bought/exchanged <:pokechip:840469159242760203> to user 67890:
            ```
            {command_prefix}add_chips 67890 500 --purchased
            ```~
        """
        if not args:
            await message.channel.send(
                embed=get_embed(
                    "You need to provide a user ID.",
                    embed_type="error",
                    title="No User ID"
                )
            )
            return
        if len(args) < 2:
            await message.channel.send(
                embed=get_embed(
                    "You need to provide a user ID and pokechips.",
                    embed_type="error",
                    title="Not enough args"
                )
            )
            return
        user_id = int(args[0])
        try:
            increment = int(args[1])
        except ZeroDivisionError:
            await message.channel.send(
                embed=get_embed(
                    "Good try but bad luck.",
                    embed_type="error",
                    title="Invalid input"
                )
            )
            return
        profile = await self.__get_profile(message, user_id)
        if not profile:
            return
        data = profile.get()
        balance = data["balance"]
        purchased_chips = data["purchased_chips"]
        balance += increment
        if kwargs.get("purchased", False):
            purchased_chips += increment
        profile.update(
            balance=balance,
            purchased_chips=purchased_chips
        )
        await message.add_reaction("👍")

    @admin_only
    async def cmd_reset_user(self, message, args=None, **kwargs):
        """Completely resets a user's profile.
        $```scss
        {command_prefix}reset_user user_id
        ```$

        @`🛡️ Admin Command`
        Completely resets a user's profile to the starting stage.@

        ~To reset user with ID 12345:
            ```
            {command_prefix}reset_user 12345
            ```~
        """
        if not args:
            await message.channel.send(
                embed=get_embed(
                    "You need to provide a user ID.",
                    embed_type="error",
                    title="No User ID"
                )
            )
            return
        user_id = int(args[0])
        profile = await self.__get_profile(message, user_id)
        profile.reset()
        await message.add_reaction("👍")

    @owner_only
    async def cmd_update_user(self, message, args=None, **kwargs):
        """Updates a user's profile.
        $```scss
        {command_prefix}update_user user_id --param value
        ```$

        @`👑 Owner Command`
        Updates a user's profile based on the kwargs.@

        ~To update num_wins of user with ID 12345:
            ```
            {command_prefix}update_user 12345 --num_wins 10
            ```~
        """
        if not args:
            await message.channel.send(
                embed=get_embed(
                    "You need to provide a user ID.",
                    embed_type="error",
                    title="No User ID"
                )
            )
            return
        user_id = int(args[0])
        kwargs.pop("mentions", [])
        profile = await self.__get_profile(message, user_id)
        if not profile:
            return
        try:
            profile.update(**kwargs)
        except Exception as excp: # pylint: disable=broad-except
            await message.channel.send(
                embed=get_embed(
                    "Good try but bad luck.",
                    embed_type="error",
                    title="Invalid input"
                )
            )
            self.logger.pprint(
                f"{message.author} triggered cmd_update_user with {kwargs}.\n"
                f"Error: {excp}",
                color="red",
                timestamp=True
            )
            return
        await message.add_reaction("👍")
