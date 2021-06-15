"""
This module is a compilation of Image Generation Classes.
"""

# pylint: disable=arguments-differ, too-many-arguments

import os
import random
from abc import ABC, abstractmethod
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import (
    Image, ImageDraw,
    ImageEnhance, ImageFont
)
from ..base.items import Gladiator


class AssetGenerator(ABC):
    """
    The Abstract Base Class for Image Generation tasks.
    """
    def __init__(self, asset_path: str = "assets"):
        self.asset_path = asset_path
        self.pokechip = Image.open(
            os.path.join(asset_path, "pokechip.png")
        )
        self.pokebond = Image.open(
            os.path.join(asset_path, "pokebond.png")
        )

    @abstractmethod
    def get(self, **kwargs):
        """
        Every Image Generation class should have a get method.
        """

    @staticmethod
    def get_font(font, txt: str, bbox: List) -> ImageFont:
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
        txt: str, start_pos: Tuple,
        bbox: Tuple, fontsize: int = 40
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
    def __init__(self, asset_path: str = "assets"):
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
        badges: Optional[List[Image.Image]] = None,
        blacklisted: bool = False
    ) -> Image.Image:

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

    def add_bl_effect(self, profilecard: Image.Image) -> Image.Image:
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
    def __init__(self, asset_path: str = "assets"):
        super().__init__(asset_path)
        self.asset_path = asset_path
        self.font = ImageFont.truetype(
            os.path.join(asset_path, "Exo-ExtraBold.ttf"),
            32
        )
        self.wallet = Image.open(
            os.path.join(asset_path, "basecards", "wallet.png")
        )

    def get(self, data: Dict) -> Image.Image:
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
                "txt": data["pokebonds"],
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
    async def get(self, ctx, data: Dict) -> Image.Image:
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

    async def get_rankcard(
        self, ctx,
        data: Dict, heading: bool = False
    ) -> Image.Image:
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
        base = (
            self.rankcard.copy()
            if heading else self.rankcard_no_head.copy()
        )
        canvas = ImageDraw.Draw(base)
        for key, pos in pos_dict.items():
            txt = str(data[key])
            self.imprint_text(
                canvas, txt,
                pos["start_pos"],
                pos["bbox"], 60
            )
        avatar_byio = BytesIO()
        await ctx.get_user(
            int(data["user_id"])
        ).avatar_url_as(size=512).save(avatar_byio)
        avatar = Image.open(avatar_byio).resize(
            (402, 402)
        ).convert('RGBA')
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
            ).resize(
                (1280, 437), Image.ANTIALIAS
            ).convert("RGB")
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

    def get(self, badges: List = None) -> Image.Image:
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


class BoardGenerator(AssetGenerator):
    """
    The Board Generator for Wackamole minigame.
    """
    def __init__(self, asset_path: str):
        super().__init__(asset_path=asset_path)
        self.mole = Image.new('RGB', (250, 250), (0, 0, 0))
        self.mole.paste(
            self.pokechip.resize((250, 250)).convert('RGB')
        )
        self.boards = []
        self.board_names = []
        for board in sorted(os.listdir(
            os.path.join(asset_path, "basecards", "boards")
        )):
            self.board_names.append(
                board.split(".jpg")[0].title()
            )
            self.boards.append(
                Image.open(
                    os.path.join(
                        asset_path, "basecards", "boards", board
                    )
                )
            )

    @staticmethod
    def get_valids(level: int = 0) -> List:
        """
        Returns a list of possible tile names for given difficulty level.
        """
        return [
            f"{chr(65+i)}{j}"
            for i in range(level + 3)
            for j in range(1, level + 4)
        ]

    def get_board(self, level: int = 0) -> Tuple[str, Image.Image]:
        """
        Returns a Wackamole board (name, Image) of given difficulty level.
        """
        return (
            self.board_names[level],
            self.boards[level].copy()
        )

    def get(self, level: int = 0) -> Tuple[str, Image.Image]:
        """
        Returns a Board image with a random time replaced with a pokechip.
        """
        pos = (
            random.randint(0, level + 2),
            random.randint(0, level + 2)
        )
        tile_w, tile_h = (250, 250)
        board_img = self.boards[level].copy()
        board_img.paste(
            self.mole,
            (pos[0] * tile_w, pos[1] * tile_h)
        )
        letter = ('A', 'B', 'C', 'D', 'E', 'F', 'G')[pos[0]]
        num = pos[1] + 1
        rolled = f"{letter}{num}"
        return (rolled, board_img)


class GladitorMatchHandler(AssetGenerator):
    """
    Gladiator Match handler class
    """
    def __init__(self, asset_path: str = "assets"):
        super().__init__(asset_path)
        self.font = ImageFont.truetype(
            os.path.join(asset_path, "Exo-ExtraBold.ttf"),
            140
        )
        self.arena = Image.open(
            os.path.join(asset_path, "duel", "arena.jpg")
        )
        self.bloods = [
            Image.open(
                os.path.join(asset_path, 'duel', 'bloods', fname)
            ).convert('RGBA')
            for fname in os.listdir(
                os.path.join(asset_path, 'duel', 'bloods')
            )
        ]
        self.glad_x_offset = 270
        self.hp_bar = Image.open(
            os.path.join(asset_path, "duel", "hp_bar.png")
        )
        self.color_bars = [
            Image.new(
                'RGBA',
                (134, 728),
                color=(254, 0, 0, 255)   # RED_BAR
            ),
            Image.new(
                'RGBA',
                (134, 728),
                color=(254, 240, 0, 255)   # YELLOW_BAR
            ),
            Image.new(
                'RGBA',
                (134, 728),
                color=(60, 254, 0, 255)   # GREEN_BAR
            )
        ]

    @staticmethod
    def __get_damage():
        """
        Returns a random amount of damage.
        """
        return int(
            np.clip(
                random.gauss(50, 100), 25, 300
            )
        )

    def __get_blood(self, damage: int) -> Image.Image:
        """
        Returns corresponding blood image for the damage done.
        """
        return self.bloods[int(damage / 50)]

    def __add_blood(
        self, gladiator_sprite: Image.Image,
        damage: int
    ):
        """
        Applies bleeding effect to Gladiator sprite.
        """
        blood = self.__get_blood(damage=damage)
        bld_w, bld_h = blood.size
        bbox = gladiator_sprite.getbbox()
        glad_w = bbox[2] - bbox[0]
        glad_h = bbox[3] - bbox[1]
        pos = (
                random.randint(self.glad_x_offset, glad_w - bld_w),
                random.randint(0, glad_h - bld_h)
            )
        gladiator_sprite.paste(blood, pos, blood)

    def __update_hitpoints(self, gladiator: Image.Image, hitpoints: int):
        """
        Update the HP Bar of the gladiator sprite.
        """
        bar_ht = int((728 / 300) * hitpoints)
        final_glad = gladiator
        if bar_ht > 0:
            clrbar = self.color_bars[int((hitpoints / 300) * 3)].resize(
                    (134, bar_ht)
                )
            final_glad = gladiator.copy()
            final_glad.paste(clrbar, (833, 187 + (728 - bar_ht)), clrbar)
        return final_glad

    def __prepare_arena(self, players: List[str]) -> Image.Image:
        """
        Sets up the initial arena.
        """
        canvas = self.arena.copy()
        board = ImageDraw.Draw(canvas)
        gn_pad1, gn_pad2 = [
            int((1000 - self.font.getsize(plyr)[0]) / 2)
            for plyr in players
        ]
        board.text(
            (500 + gn_pad1, 463),
            players[0],
            font=self.font,
            fill=(255, 255, 255)
        )
        board.text(
            (2340 + gn_pad2, 463),
            players[1],
            font=self.font,
            fill=(255, 255, 255)
        )
        return canvas

    def fight(self, gladiator: Gladiator) -> Tuple[Image.Image, int]:
        """
        Makes the provider gladiator take damage and returns
        a tuple of damaged gladiator image and remaining hitpoint.
        """
        fresh = True
        if fresh:
            fresh = False
            glad = gladiator.image
            glad.paste(self.hp_bar, (0, 0), self.hp_bar)
            hitpoints = 300
            fresh_glad = glad.copy()
            green_bar = self.color_bars[-1]
            fresh_glad.paste(green_bar, (833, 187), green_bar)
            yield fresh_glad, 300
        while hitpoints >= 0:
            dmg = self.__get_damage()
            hitpoints -= dmg
            self.__add_blood(glad, dmg)
            final_glad = self.__update_hitpoints(glad, hitpoints)
            yield final_glad, hitpoints

    def get(
        self, gladiators: List[Gladiator]
    ) -> Tuple[Image.Image, int, int]:
        """
        Handles a duel match between Gladiators.
        Returns an image and damages dealt by each gladiator per round.
        """
        canvas = self.__prepare_arena([
            glad.owner.name
            for glad in gladiators
        ])
        old_hp1 = old_hp2 = 300
        for (glad1, hp1), (glad2, hp2) in zip(
            self.fight(gladiators[0]), self.fight(gladiators[1])
        ):
            canvas.paste(glad1, (500, 675), glad1)
            canvas.paste(glad2, (2340, 675), glad2)
            dmg1 = old_hp2 - hp2
            dmg2 = old_hp1 - hp1
            old_hp1 = hp1
            old_hp2 = hp2
            yield canvas.copy(), dmg1, dmg2
            if max(0, hp1) * max(0, hp2) == 0:
                break
