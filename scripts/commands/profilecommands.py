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

Profile Commands Module
"""

# pylint: disable=unused-argument, too-many-locals

from __future__ import annotations
import random
from datetime import datetime, timedelta
from io import BytesIO
from typing import Dict, List, Optional, TYPE_CHECKING

from PIL import Image
import discord

from ..base.items import Chest
from ..base.models import (
    Blacklist, Boosts, CommandData, Inventory, Loots,
    Matches, Minigame, Profiles, Votes
)
from ..base.shop import BoostItem
from ..base.views import LinkView

from ..helpers.checks import user_check
from ..helpers.imageclasses import (
    BadgeGenerator, LeaderBoardGenerator,
    ProfileCardGenerator, WalletGenerator
)
from ..helpers.unicodex import Unicodex
from ..helpers.utils import (
    LineTimer, dm_send, get_embed, get_formatted_time,
    get_modules, img2file, wait_for
)
from ..helpers.validators import HexValidator, ImageUrlValidator

from .basecommand import (
    Commands, alias, check_completion, cache_images, get_user,
    model, get_profile, needs_ticket
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

    @needs_ticket("Background Change")
    @check_completion
    @model([Profiles, Inventory])
    @alias('bg')
    async def cmd_background(self, message: Message, **kwargs):
        """Change Profile Background.
        $```scss
        {command_prefix}background
        ```$

        @Change the background in your Profile card.
        The Background Change ticket can be purchased
        from the Consumables Shop.@
        """
        profile = Profiles(message.author)
        inp_msg = await dm_send(
            message, message.author,
            embed=get_embed(
                "The image size should be greater than **960x540**.\n"
                "Make sure it uses the *same aspect ratio* as well.\n"
                "Supported Extension: `PNG` and `JPEG`\n"
                "> Will rollback to default background "
                "if link is not accessible any time.\n"
                "⚠️Using inappropriate images will get you blacklisted.",
                title="Enter the image url or upload it.",
                color=profile.get('embed_color')
            )
        )
        reply = await wait_for(
            inp_msg.channel, self.ctx,
            init_msg=inp_msg,
            check=lambda msg: user_check(msg, message, inp_msg.channel),
            timeout="inf"
        )
        url = await self.__background_get_url(message, reply)
        if not url:
            return
        profile.update(
            background=url
        )
        inv = Inventory(message.author)
        tickets = kwargs["tickets"]
        inv.delete(tickets[0], quantity=1)
        await dm_send(
            message, message.author,
            embed=get_embed(
                "You can check your profile now.",
                title="Succesfully updated Profile Background.",
                color=profile.get('embed_color')
            )
        )

    @alias("bdg")
    @model(Profiles)
    @cache_images
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
        profile = await get_profile(message,  message.author)
        badges = profile.get_badges()
        badgestrip = self.bdgen.get(badges)
        discord_file = img2file(badgestrip, "badges.png", ext="PNG")
        msg = await message.reply(file=discord_file)
        self.cmd_badges.__dict__["image_cache"][message.author.id].register(
            msg.attachments[0].proxy_url
        )

    @alias(["bal", "chips"])
    @model(Profiles)
    @cache_images
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
        profile = (
            await get_profile(message,  message.author)
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
        msg = await message.reply(
            file=discord_file
        )
        self.cmd_balance.__dict__["image_cache"][message.author.id].register(
            msg.attachments[0].proxy_url
        )

    @model([Boosts, BoostItem, Profiles])
    async def cmd_boosts(self, message: Message, **kwargs):
        """Check active boosts.
        $```scss
        {command_prefix}boosts
        ```$

        @Check your active purchased boosts.@
        """
        def get_desc(boost):
            prm_bst = perm_boosts[boost['name'].lower().replace(' ', '_')]
            total = boost['stack'] + prm_bst
            desc_str = f"{boost['description']}\nStack: {total}"
            if prm_bst > 0:
                desc_str += f" ({prm_bst} Permanent)"
            expires_in = (30 * 60) - (
                datetime.utcnow() - boost["added_on"]
            ).total_seconds()
            if expires_in > 0 and boost['stack'] > 0:
                expires_in = get_formatted_time(
                    expires_in, show_hours=False
                ).replace('**', '')
            else:
                expires_in = "Expired / Not Purchased Yet"
            desc_str += f"\nExpires in: {expires_in}"
            return f"```css\n{desc_str}\n```"
        boosts = BoostItem.get_boosts(str(message.author.id))
        profile = Profiles(message.author)
        perm_boosts = Boosts(message.author).get()
        perm_boosts.pop('user_id')
        if not (
            boosts or any(
                bst > 1
                for bst in perm_boosts.values()
            )
        ):
            await message.reply(
                embed=get_embed(
                    "You don't have any active boosts.",
                    title="No Boosts",
                    color=profile.get('embed_color')
                )
            )
            return
        emb = get_embed(
            "\u200B",
            title="Active Boosts",
            color=profile.get('embed_color')
        )
        if not boosts:
            boosts = BoostItem.default_boosts()
        for val in boosts.values():
            emb.add_field(
                name=val["name"],
                value=get_desc(val),
                inline=False
            )
        await message.reply(embed=emb)

    @model([Loots, Profiles, Chest, Inventory])
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
        You can maintain a daily streak.
        Get more (scalable) chips for every 5 day streak.@
        """
        profile = Profiles(message.author)
        loot_model = Loots(message.author)
        boost_model = Boosts(message.author)
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
            await message.reply(
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
        chest = Chest.get_chest(tier=tier)
        chest.save()
        Inventory(message.author).save(chest.itemid)
        embed = get_embed(
            f"Here's your daily **{chest}**.\n"
            f"Claim the chest with `{self.ctx.prefix}open {chest.itemid}`.",
            title="**Daily Chest**",
            thumbnail=chest.asset_url,
            footer="You get bonus pokechips for every 5 streak.",
            color=profile.get('embed_color')
        )
        profile.credit(int(loot))
        loot_model.update(
            earned=(earned + loot),
            daily_streak=daily_streak,
            daily_claimed_on=datetime.today()
        )
        stk_name, stk_val = Unicodex.format_streak(daily_streak)
        embed.add_field(
            name=stk_name,
            value=stk_val
        )
        await message.reply(
            f"**Daily loot of {int(loot)} {self.chip_emoji} "
            "added to your balance.**",
            embed=embed
        )

    @needs_ticket("Embed Color Change")
    @check_completion
    @model([Profiles, Inventory])
    @alias(['embed', 'ec', 'color'])
    async def cmd_embed_color(self, message: Message, **kwargs):
        """Change Embed Color.
        $```scss
        {command_prefix}embed_color
        ```$

        @Change the color of the embeds you get from PokeGambler.
        The Embed Color Change ticket can be purchased
        from the Consumables Shop.@
        """
        profile = Profiles(message.author)
        inp_msg = await dm_send(
            message, message.author,
            embed=get_embed(
                "Enter the hexadecimal code for the color you want.\n"
                "Should follow the pattern: #abcdef\n"
                "> Eg: #000FFF",
                title="Enter the color code",
                color=profile.get('embed_color')
            )
        )
        reply = await wait_for(
            inp_msg.channel, self.ctx,
            init_msg=inp_msg,
            check=lambda msg: user_check(msg, message, inp_msg.channel),
            timeout="inf"
        )
        proceed = await HexValidator(
            message=message,
            on_error={
                "title": "Invalid Hexadecimal Color Code",
                "description": "You need to enter a valid hex code."
            },
            dm_user=True
        ).validate(reply.content)
        if not proceed:
            return
        hexcode = reply.content.lstrip('#')
        profile.update(
            embed_color=int(hexcode, 16)
        )
        inv = Inventory(message.author)
        tickets = kwargs["tickets"]
        inv.delete(tickets[0], quantity=1)
        await dm_send(
            message, message.author,
            embed=get_embed(
                title="Succesfully updated your Embed Color.",
                color=profile.get('embed_color')
            )
        )

    @model(Profiles)
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
        with LineTimer(self.logger, "Get Leaderboards"):
            if args and not args[0].lower().startswith("bal"):
                lbrd = self.__lb_get_minigame_lb(
                    args[0].lower(),
                    message.author
                )
                if lbrd is None:
                    await message.reply(
                        embed=get_embed(
                            "You can choose a minigame name or 'balance'.",
                            embed_type="error",
                            title="Invalid Input"
                        )
                    )
                    return
                leaderboard = []
                lbrd = [
                    {
                        "member": (
                            message.guild.get_member(int(res["_id"]))
                            or self.ctx.get_guild(
                                self.ctx.official_server
                            ).get_member(int(res["_id"]))
                        ),
                        **res,
                        "rank": idx + 1
                    }
                    for idx, res in enumerate(lbrd)
                    if (
                        message.guild.get_member(int(res["_id"]))
                        or self.ctx.get_guild(
                            self.ctx.official_server
                        ).get_member(int(res["_id"]))
                    )
                ]
                for res in lbrd:
                    profile = Profiles(res["member"]).get()
                    balance = res.get("earned", 0) or profile["balance"]
                    name = profile["name"]
                    leaderboard.append({
                        "rank": res["rank"],
                        "user_id": res["_id"],
                        "name": name,
                        "num_matches": res["num_matches"],
                        "num_wins": res["num_wins"],
                        "balance": balance
                    })
            else:
                sort_by = [
                    "num_wins", "num_matches"
                ] if not args else ["balance"]
                leaderboard = Profiles.get_leaderboard(
                    sort_by=sort_by
                )
            if not leaderboard:
                await message.reply(
                    embed=get_embed(
                        "No matches were played yet.",
                        embed_type="warning"
                    )
                )
                return
            lbd = []
            idx = 0
            for data in leaderboard:
                if not self.ctx.get_user(int(data["user_id"])):
                    continue
                data["rank"] = idx + 1
                data["balance"] = f'{data["balance"]:,}'
                lbd.append(data)
                idx += 1
        embeds = []
        files = []
        with LineTimer(self.logger, "Create Leaderboard Images"):
            for i in range(0, len(lbd), 4):
                batch_4 = lbd[i: i + 4]
                img = await self.lbg.get(self.ctx, batch_4)
                lb_fl = img2file(img, f"leaderboard{i}.jpg")
                emb = discord.Embed(
                    title="",
                    description="",
                    color=discord.Colour.dark_theme()
                )
                embeds.append(emb)
                files.append(lb_fl)
        if not embeds:
            await message.reply(
                embed=get_embed(
                    "No matches were played yet.",
                    embed_type="warning"
                )
            )
            return
        with LineTimer(self.logger, "Leaderboard Pagination"):
            await self.paginate(message, embeds, files)

    @model([Loots, Profiles, Chest, Inventory])
    @alias('lt')
    async def cmd_loot(self, message: Message, **kwargs):
        """Stable source of Pokechips.
        $```scss
        {command_prefix}loot
        ```$

        @Search the void for free {pokechip_emoji}.
        The number of chips is randomly choosen from 5 to 10.
        `Loot Increase Boost can be purchased from Boosts shop.`
        There is a cooldown of 10 minutes between loots.
        `Cooldown Reduction Boost can be purchased from Boosts shop.`@
        """
        on_cooldown = self.ctx.loot_cd.get(message.author, None)
        perm_boosts = Boosts(
            message.author
        ).get()
        loot_mult = 1 + (perm_boosts["lucky_looter"] * 0.05)
        cd_reducer = perm_boosts["loot_lust"]
        tr_mult = 0.1 * (perm_boosts["fortune_burst"] + 1)
        boosts = BoostItem.get_boosts(str(message.author.id))
        cd_reducer += boosts['boost_lt_cd']['stack']
        loot_mult += 0.05 * boosts['boost_lt']['stack']
        tr_mult += 0.1 * boosts['boost_tr']['stack']
        cd_time = 60 * (10 - cd_reducer)
        on_cd = await self.__loot_handle_cd(message, on_cooldown, cd_time)
        if on_cd:
            return
        profile = Profiles(message.author)
        loot_model = Loots(message.author)
        loot_info = loot_model.get()
        earned = loot_info["earned"]
        tier = loot_info["tier"]
        loot = int(
            random.randint(5, 10) * (
                10 ** (tier - 1)
            ) * loot_mult
        )
        embed = None
        if random.uniform(0, 1.0) <= tr_mult:
            embed = self.__loot_handle_treasure(message, profile, tier)
        profile.credit(loot)
        loot_model.update(earned=earned + loot)
        await message.reply(
            f"**You found {loot} {self.chip_emoji}! "
            "Added to your balance.**",
            embed=embed
        )

    @model([Profiles, Blacklist])
    @alias("pr")
    @get_user
    @cache_images
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
        user = kwargs["selected_user"]
        profile = await get_profile(message, user)
        if not profile:
            return
        badges = profile.get_badges()
        profile = profile.get()
        avatar_byio = BytesIO()
        await user.avatar.with_size(512).save(avatar_byio)
        avatar = Image.open(avatar_byio)
        name = profile["name"]
        balance = f'{profile["balance"]:,}'
        num_played = str(profile["num_matches"])
        num_won = str(profile["num_wins"])
        background = None
        if profile.get("background", None):
            background = await self.__profile_get_bg(profile)
        profilecard = self.pcg.get(
            name, avatar, balance,
            num_played, num_won, badges,
            blacklisted=Blacklist.is_blacklisted(
                str(user.id)
            ), background=background
        )
        discord_file = img2file(profilecard, "profilecard.jpg")
        msg = await message.reply(file=discord_file)
        self.cmd_profile.__dict__["image_cache"][user.id].register(
            msg.attachments[0].proxy_url
        )

    @model(Profiles)
    @alias("#")
    @cache_images
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
        with LineTimer(self.logger, "Get Profile"):
            profile = await get_profile(
                message,
                message.author
            )
            rank = profile.get_rank()
            data = profile.get()
            data["rank"] = rank or 0
            data["balance"] = f'{data["balance"]:,}'
        with LineTimer(self.logger, "Create Rank Image"):
            img = await self.lbg.get_rankcard(self.ctx, data, heading=True)
            discord_file = img2file(
                img,
                f"rank_{message.author}.png",
                ext="PNG"
            )
        with LineTimer(self.logger, "Send Rank Image"):
            msg = await message.reply(file=discord_file)
            self.cmd_rank.__dict__["image_cache"][message.author.id].register(
                msg.attachments[0].proxy_url
            )

    @model([Minigame, Loots, CommandData])
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
            message.author
        ).get_stats()
        stat_dict = {
            "Gambles": f"Played: {match_stats[0]}\n"
            f"Won: {match_stats[1]}"
        }
        for minigame_cls in Minigame.__subclasses__():
            minigame = minigame_cls(message.author)
            stat_dict[
                minigame_cls.__name__
            ] = f"Played: {minigame.num_plays}\n" + \
                f"Won: {minigame.num_wins}"
        loots_earned = Loots(message.author).earned
        num_cmds = CommandData.num_user_cmds(str(message.author.id))
        stat_dict["Misc."] = f"Looted: {loots_earned}\n" + \
            f"Commands: {num_cmds}"
        emb = get_embed(
            "Here's how you've performed till now.",
            title=f"Statistics for **{message.author.name}**",
            color=Profiles(message.author).get('embed_color')
        )
        for idx, (key, val) in enumerate(stat_dict.items()):
            if idx and (idx % 2 == 0):
                emb.add_field(name="\u200B", value="\u200B")
            emb.add_field(
                name=f"**{key}**",
                value=f"```rb\n{val}\n```"
            )
        await message.reply(embed=emb)

    @model([Profiles, Votes, Loots, Inventory])
    @alias("v")
    async def cmd_vote(self, message: Message, **kwargs):
        """Vote for the bot.
        $```scss
        {command_prefix}vote
        ```$

        @Vote for the bot on Top.gg.
        Get 100 chips for every vote.
        Bonus Rewards on every 5 streak.@
        """
        votes = Votes(message.author)
        streak = votes.vote_streak
        profile = Profiles(message.author)
        emb, elapsed = self.__vote_prep_embed(votes, streak, profile)
        if not votes.reward_claimed:
            profile.credit(100)
            content = "Thanks for voting, you've been given " + \
                f"100 {self.chip_emoji}."
            if streak % 5 == 0 and votes.vote_streak > 0:
                tier = Loots(message.author).tier
                chest = Chest.get_chest(tier=tier)
                chest.save()
                Inventory(message.author).save(chest.itemid)
                content += "\nYou've been given a bonus Chest!\n" + \
                    f"『{chest.emoji}』**{chest}** - **{chest.itemid}**"
                cleared_cds = ["Loot"]
                for cmd in self.ctx.cooldown_cmds:
                    cleared = self.ctx.cooldown_cmds[cmd].pop(
                        message.author, None
                    )
                    if cleared:
                        cleared_cds.append(
                            cmd.__name__.replace("cmd_", "").title()
                        )
                self.ctx.loot_cd.pop(message.author, None)
                cd_cmd_str = "\n".join(
                    f"{idx + 1}. {cmd}"
                    for idx, cmd in enumerate(cleared_cds)
                )
                content += "\nCooldowns cleared for following commands:" + \
                    f"\n```md\n{cd_cmd_str}\n```"
            votes.update(reward_claimed=True)
            emb.add_field(
                name="Rewards Added",
                value=content,
                inline=False
            )
        else:
            emb.add_field(
                name="Streak Rewards",
                value="```md\n1. Tier scaled Chest\n"
                "2. Clears all cooldowns (except daily)\n```",
                inline=False
            )
        vote_button = LinkView(
            url=f"https://top.gg/bot/{self.ctx.user.id}/vote",
            label="Vote Now!"
        )
        to_send = {
            "embed": emb
        }
        if elapsed >= 12:
            to_send["view"] = vote_button
        await message.reply(**to_send)

    async def __background_get_url(self, message, reply):
        if len(reply.attachments) > 0:
            if reply.attachments[0].content_type not in (
                "image/png", "image/jpeg"
            ):
                await dm_send(
                    message, message.author,
                    embed=get_embed(
                        "Please make sure it's a png or a jpeg image.",
                        embed_type="error",
                        title="Invalid Image"
                    )
                )
                return None
            return reply.attachments[0].proxy_url
        proceed = await ImageUrlValidator(
            message=message,
            on_error={
                "title": "Invalid Image",
                "description": "Please make sure it's a png or a jpeg image."
            },
            dm_user=True
        ).validate(reply.content)
        if not proceed:
            return None
        return reply.content

    def __lb_get_minigame_lb(self, mg_name: str, user: Member) -> List[Dict]:
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
                possibilities = _aliases(module) + _commands(module)
                if mg_name in possibilities:
                    command = getattr(module, f"cmd_{mg_name}")
                    models = getattr(command, "models", [])
                    if not models:
                        continue
                    for model_ in models:
                        if issubclass(model_, Minigame):
                            leaderboard = model_(
                                user
                            ).get_lb()
                            if leaderboard:
                                return leaderboard
            return leaderboard
        modules = get_modules(self.ctx)
        return _get_lb(modules, mg_name, user)

    async def __loot_handle_cd(self, message, on_cooldown, cd_time):
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
            await message.reply(
                embed=get_embed(
                    f"Please wait {time_remaining} before looting again.",
                    embed_type="warning",
                    title="On Cooldown"
                )
            )
            return True
        self.ctx.loot_cd[message.author] = datetime.now()
        return False

    @staticmethod
    def __loot_handle_treasure(message, profile, tier):
        chest = Chest.get_chest(tier=tier)
        chest.save()
        Inventory(message.author).save(chest.itemid)
        return get_embed(
            f"Woah! You got lucky and found a **{chest}**.\n"
            "It's been added to your inventory.",
            title="**FOUND A TREASURE CHEST**",
            thumbnail=chest.asset_url,
            footer=f"Chest ID: {chest.itemid}",
            color=profile.get('embed_color')
        )

    async def __profile_get_bg(self, profile):
        bg_byio = BytesIO()
        try:
            async with self.ctx.sess.get(profile["background"]) as resp:
                data = await resp.read()
            bg_byio.write(data)
            bg_byio.seek(0)
            background = Image.open(bg_byio).resize((960, 540))
        except Exception:  # pylint: disable=broad-except
            background = None
        return background

    def __vote_prep_embed(self, votes, streak, profile):
        emb = get_embed(
            title="Vote",
            content="Vote for the bot on **Top.gg** to get rewards.\n"
            f"You'll get **100** {self.chip_emoji} on every vote.\n"
            "Bonus rewards for every **5** streak.",
            color=profile.get('embed_color'),
            footer="Re-use this command after voting "
            "to autoclaim rewards."
        )
        stk_name, stk_val = Unicodex.format_streak(
            streak,
            mode="vote"
        )
        if votes.reward_claimed:
            stk_val = stk_val.replace("🎁", "")
        emb.add_field(
            name=stk_name,
            value=stk_val
        )
        last_voted = votes.last_voted
        now = datetime.now()
        elapsed = (now - last_voted).total_seconds() // 3600
        if elapsed >= 12:
            cd_msg = "You can vote **now**!"
        else:
            ends_on = last_voted + timedelta(hours=12)
            tot_secs = (ends_on - now).total_seconds()
            cd_msg = f"You can vote again in {get_formatted_time(tot_secs)}."
        emb.add_field(
            name="Vote Cooldown",
            value=cd_msg,
            inline=False
        )
        return emb, elapsed
