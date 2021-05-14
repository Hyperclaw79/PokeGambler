"""
This module is a compilation of Image Generation Classes.
"""

# pylint: disable=arguments-differ, too-many-arguments

import os
from abc import ABC, abstractmethod
from io import BytesIO
import random

from PIL import (
    Image, ImageDraw,
    ImageFont, ImageEnhance
)


class AssetGenerator(ABC):
    """
    The Abstract Base Class for Image Generation tasks.
    """
    def __init__(self, asset_path: str = "assets"):
        self.asset_path = asset_path
        self.pokechip = Image.open(
            os.path.join(asset_path, "pokechip.png")
        )

    @abstractmethod
    def get(self, **kwargs):
        """
        Every Image Generation class should have a get method.
        """

    @staticmethod
    def get_font(font, txt, bbox):
        """
        Shrinks the font size until the text fits in bbox.
        """
        fontsize = font.size
        while font.getsize(txt)[0] > bbox[0]:
            fontsize -= 1
            font = ImageFont.truetype(font.path, fontsize)
        return font

    def imprint_text(
        self, canvas,
        txt: str, start_pos: tuple,
        bbox: tuple, fontsize=40
    ):
        """
        Pastes Center aligned, font corrected text on the canvas.
        """
        font = ImageFont.truetype(
            os.path.join(self.asset_path, "Exo-ExtraBold.ttf"),
            fontsize
        )
        font = self.get_font(font, txt, bbox)
        width, height = font.getsize(txt)
        pos = (
            (bbox[0] - width) / 2 + start_pos[0],
            (bbox[1] - height) / 2 + start_pos[1]
        )
        canvas.text(pos, txt, fill=(255, 255, 255), font=font)


class ProfileCardGenerator(AssetGenerator):
    """
    ProfileCard Image Generation Class
    """
    def __init__(self, asset_path: str="assets"):
        super().__init__(asset_path)
        self.font = ImageFont.truetype(
            os.path.join(asset_path, "Exo-ExtraBold.ttf"),
            36
        )
        self.profilecard = Image.open(
            os.path.join(asset_path, "basecards", "profilecard.jpg")
        )
        self.badges = {
            badge: Image.open(
                os.path.join(
                    asset_path, "basecards",
                    "badges", "100x100", f"{badge}.png"
                )
            )
            for badge in ["champion", "emperor", "funder", "dealer"]
        }

    def get(
        self, name: str, avatar: Image,
        balance: str, num_played: str, num_won: str,
        badges: None, blacklisted: bool = False
    ) -> Image:

        # pylint: disable=too-many-locals

        profilecard = self.profilecard.copy()
        profilecard.paste(
            avatar.resize((280, 280)).convert('RGB'),
            (603, 128)
        )
        canvas = ImageDraw.Draw(profilecard)
        params = [
            {
                "txt": name,
                "start_pos": (220, 112),
                "bbox": (280, 56)
            },
            {
                "txt": num_played,
                "start_pos": (220, 292),
                "bbox": (280, 56)
            },
            {
                "txt": num_won,
                "start_pos": (220, 340),
                "bbox": (280, 56)
            },
            {
                "txt": balance,
                "start_pos": (220, 177),
                "bbox": (210, 56)
            }
        ]
        for param in params:
            canvas.text(
                param["start_pos"],
                param["txt"],
                fill=(0, 0, 0),
                font=self.get_font(
                    self.font, param["txt"], param["bbox"]
                )
            )
        profilecard = profilecard.convert('RGBA')
        if all([
            badges, not blacklisted
        ]):
            for idx, badge in enumerate(badges):
                profilecard.paste(
                    self.badges[badge],
                    (25 + (120 * idx), 400),
                    self.badges[badge]
                )
        chip_pos = (220 + self.font.getsize(balance)[0] + 20, 159)
        chip = self.pokechip.resize((80, 80), Image.ANTIALIAS)
        profilecard.paste(chip, chip_pos, chip)
        profilecard = profilecard.convert('RGB')
        if blacklisted:
            profilecard = self.add_bl_effect(profilecard)
        return profilecard

    def add_bl_effect(self, profilecard):
        """
        Adds a Blacklisted label on profilecard.
        Also desaturates and darkens the image.
        """
        for task in ["Brightness", "Color"]:
            enhancer = getattr(ImageEnhance, task)(profilecard)
            profilecard = enhancer.enhance(0.25)
        text_layer = Image.new('RGBA', profilecard.size, (0, 0, 0, 0))
        canvas = ImageDraw.Draw(text_layer)
        canvas.text(
            (50, 205),
            "BLACKLISTED",
            fill=(255, 255, 255, 255),
            font=ImageFont.truetype(self.font.path, 130)
        )
        profilecard.paste(
            text_layer.rotate(-20),
            (0, 0),
            text_layer.rotate(-20)
        )
        return profilecard


class WalletGenerator(AssetGenerator):
    """
    BalanceCard Image Generation Class
    """
    def __init__(self, asset_path: str="assets"):
        super().__init__(asset_path)
        self.asset_path = asset_path
        self.font = ImageFont.truetype(
            os.path.join(asset_path, "Exo-ExtraBold.ttf"),
            32
        )
        self.wallet = Image.open(
            os.path.join(asset_path, "basecards", "wallet.png")
        )

    def get(self, data: dict)->Image:
        wallet = self.wallet.copy()
        canvas = ImageDraw.Draw(wallet)
        params = [
            {
                "txt": data["won_chips"],
                "start_pos": (620, 100),
                "bbox": (255, 70),
                "fontsize": 54
            },
            {
                "txt": data["purchased_chips"],
                "start_pos": (620, 235),
                "bbox": (255, 70),
                "fontsize": 54
            },
            {
                "txt": data["balance"],
                "start_pos": (620, 390),
                "bbox": (255, 70),
                "fontsize": 54
            }
        ]
        for param in params:
            self.imprint_text(canvas, **param)
        return wallet


class LeaderBoardGenerator(AssetGenerator):
    """
    Leaderboard Image Generation Class
    """
    def __init__(self, asset_path: str = "assets"):
        super().__init__(asset_path)
        self.leaderboard = Image.open(
            os.path.join(
                asset_path, "basecards",
                "leaderboard", "lb.jpg"
            )
        )
        self.rankcard = Image.open(
            os.path.join(
                asset_path, "basecards",
                "leaderboard", "rankcard.png"
            )
        )
        self.rankcard_no_head = Image.open(
            os.path.join(
                asset_path, "basecards",
                "leaderboard", "rankcard_no_heading.png"
            )
        )

    # pylint: disable=invalid-overridden-method
    async def get(self, ctx, data)->Image:
        poslist = [
            (41, 435), (1371, 435),
            (41, 950), (1371, 950)
        ]
        leaderboard = self.leaderboard.copy()
        for idx, user_data in enumerate(data):
            rankcard = await self.get_rankcard(ctx, data=user_data)
            leaderboard.paste(rankcard, poslist[idx])
        leaderboard = leaderboard.resize(
            (int(leaderboard.size[0] / 2), int(leaderboard.size[1] / 2))
        )
        return leaderboard

    async def get_rankcard(self, ctx, data: dict, heading=False) -> Image:
        """
        Generates a Rank Card for a user.
        """
        pos_dict = {
            "name": {
                "start_pos": (799, 310),
                "bbox": (397, 144)
            },
            "rank": {
                "start_pos": (643, 310),
                "bbox": (112, 114)
            },
            "num_wins": {
                "start_pos": (1240, 242),
                "bbox": (276, 122)
            },
            "num_matches": {
                "start_pos": (1240, 398),
                "bbox": (276, 122)
            },
            "balance": {
                "start_pos": (1559, 310),
                "bbox": (320, 144)
            }
        }
        base = self.rankcard.copy() if heading else self.rankcard_no_head.copy()
        canvas = ImageDraw.Draw(base)
        for key, pos in pos_dict.items():
            txt = str(data[key])
            self.imprint_text(canvas, txt, pos["start_pos"], pos["bbox"], 60)
        avatar_byio = BytesIO()
        await ctx.get_user(int(data["user_id"])).avatar_url_as(size=512).save(avatar_byio)
        avatar = Image.open(avatar_byio).resize((402, 402)).convert('RGBA')
        base.paste(avatar, (131, 196), avatar)
        if any([
            int(data["rank"]) >= 4,
            int(data["rank"]) == 0
        ]):
            hexagon = "black"
        else:
            hexagon = ["gold", "silver", "bronze"][int(data["rank"]) - 1]
        hexagon = Image.open(
            os.path.join(
                self.asset_path, "basecards",
                "leaderboard", "hexagons", f"{hexagon}.png"
            )
        )
        rankcard = Image.alpha_composite(base, hexagon)
        if not heading:
            rankcard = rankcard.crop(
                (0, 70, 1920, 725)
            ).resize((1280, 437), Image.ANTIALIAS).convert("RGB")
        else:
            rankcard = rankcard.resize((1280, 530), Image.ANTIALIAS)
        return rankcard


class BadgeGenerator(AssetGenerator):
    """
    Badgestrip Image Generation Class
    """
    def __init__(self, asset_path: str = "assets"):
        super().__init__(asset_path)
        self.badges = {
            badge: Image.open(
                os.path.join(
                    asset_path, "basecards",
                    "badges", f"{badge}.png"
                )
            )
            for badge in ["champion", "emperor", "funder", "dealer"]
        }
        self.badgestrip = Image.open(
            os.path.join(
                asset_path, "basecards",
                "badges", "badgestrip.png"
            )
        )

    def get(self, badges: list = None)->Image:
        badgestrip = self.badgestrip.copy()
        if not badges:
            return badgestrip
        badge_dict = {
            "funder": (40, 200),
            "champion": (370, 200),
            "emperor": (687, 200),
            "dealer": (1020, 200)
        }
        for badge in badges:
            badgestrip.paste(
                self.badges[badge],
                badge_dict[badge],
                self.badges[badge]
            )
        return badgestrip


class ChipFlipper(AssetGenerator):
    """
    Simple chip generator which returns pokechip or logochip.
    """
    def __init__(self, asset_path: str):
        super().__init__(asset_path=asset_path)
        self.pokechip = self.pokechip.resize((270, 270), Image.ANTIALIAS)
        self.logochip = Image.open(
            os.path.join(asset_path, "logochip.png")
        ).resize((270, 270), Image.ANTIALIAS)

    def get(self):
        """
        Randomly returns a 270 x 270 Pokechip or Logochip.
        """
        choices = ["logochip", "pokechip"]
        choice = random.choice(choices)
        return (choices.index(choice), getattr(self, choice).copy())
