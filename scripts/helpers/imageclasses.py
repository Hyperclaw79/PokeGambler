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

This module is a compilation of Image Generation Classes.
"""

# pylint: disable=arguments-differ, too-many-arguments

from __future__ import annotations
import os
import random
from abc import ABC, abstractmethod
from io import BytesIO
from typing import (
    Dict, Generator, List,
    Optional, Tuple, TYPE_CHECKING
)

from PIL import (
    Image, ImageDraw,
    ImageEnhance, ImageFont
)
from ..base.items import Gladiator

if TYPE_CHECKING:
    from bot import PokeGambler


class AssetGenerator(ABC):
    """
    The Abstract Base Class for Image Generation tasks.

    :param asset_path: The path to the assets folder.
    :type asset_path: str
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
    def get_font(font, txt: str, bbox: List[int]) -> ImageFont:
        """Shrinks the font size until the text fits in bbox.

        :param font: The font to be used.
        :type font: :class:`PIL.ImageFont.ImageFont`
        :param txt: The text to be written.
        :type txt: str
        :param bbox: The bounding box to be used.
        :type bbox: List[int]
        :return: The font object.
        :rtype: :class:`PIL.ImageFont.ImageFont`
        """
        fontsize = font.size
        while font.getsize(txt)[0] > bbox[0]:
            fontsize -= 1
            font = ImageFont.truetype(font.path, fontsize)
        return font

    def imprint_text(
        self, canvas: ImageDraw.Draw,
        txt: str, start_pos: Tuple,
        bbox: Tuple, fontsize: int = 40
    ):
        """Pastes Center aligned, font corrected text on the canvas.

        :param canvas: The canvas to be used.
        :type canvas: :meth:`PIL.ImageDraw.Draw`
        :param txt: The text to be written.
        :type txt: str
        :param start_pos: The starting position of the text.
        :type start_pos: Tuple[int, int]
        :param bbox: The bounding box to be used.
        :type bbox: Tuple[int, int, int, int]
        :param fontsize: The font size to be used.
        :type fontsize: int
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

    def get(
        self, badges: Optional[List] = None
    ) -> Image.Image:
        """
        Returns a strip having the mentioned badges.

        :param badges: The badges to be used.
        :type badges: List[str]
        :return: The strip having the mentioned badges.
        :rtype: :class:`PIL.Image.Image`
        """
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

    def get(
        self, level: Optional[int] = 0
    ) -> Tuple[str, Image.Image]:
        """Returns a Board image with a random tile \
            replaced with a pokechip.

        :param level: The level of the board., default is 0.
        :type level: Optional[int]
        :return: The board image and the board name.
        :rtype: Tuple[str, :class:`PIL.Image.Image`]
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

    def get_board(
        self, level: Optional[int] = 0
    ) -> Tuple[str, Image.Image]:
        """Returns a Wackamole board of given difficulty level.

        :param level: The level of the board., default is 0.
        :type level: Optional[int]
        :return: The board image and the board name.
        :rtype: Tuple[str, :class:`PIL.Image.Image`]
        """
        return (
            self.board_names[level],
            self.boards[level].copy()
        )

    @staticmethod
    def get_valids(
        level: Optional[int] = 0
    ) -> Tuple[Generator, Generator]:
        """Returns a list of possible tile names for \
            given difficulty level.

        :param level: The level of the board., default is 0.
        :type level: Optional[int]
        :return: The row and column values.
        :rtype: Tuple[Generator, Generator]
        """
        return (
            (
                f"{chr(65+i)}"
                for i in range(level + 3)
            ),
            (
                str(j)
                for j in range(1, level + 4)
            )
        )


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

    def get(
        self, gladiators: List[Gladiator]
    ) -> Tuple[Image.Image, int, int]:
        """Handles a duel match between Gladiators.
        Returns an image and damages dealt by each gladiator per round.

        :param gladiators: The list of gladiators.
        :type gladiators: List[:class:`~scripts.base.items.Gladiator`]
        :return: The image and the damages dealt.
        :rtype: Tuple[:class:`PIL.Image.Image`, int, int]
        """
        canvas = self.__prepare_arena([
            glad.owner.name
            for glad in gladiators
        ])
        old_hp1 = old_hp2 = 300
        for (glad1, hp1), (glad2, hp2) in zip(
            self.__fight(gladiators[0]), self.__fight(gladiators[1])
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

    def __fight(self, gladiator: Gladiator) -> Tuple[Image.Image, int]:
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

    def __get_blood(self, damage: int) -> Image.Image:
        """
        Returns corresponding blood image for the damage done.
        """
        return self.bloods[int(damage // 50)]

    @staticmethod
    def __get_damage():
        """
        Returns a random amount of damage.
        """
        return int(
            min(
                max(random.gauss(50, 100), 25),
                300
            )
        )

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
    async def get(
        self, ctx: PokeGambler,
        data: Dict
    ) -> Image.Image:
        """Returns the leaderboard image.

        :param ctx: The PokeGambler client object.
        :type ctx: :class:`bot.PokeGambler`
        :param data: The data to be used to generate the leaderboard.
        :type data: Dict
        :return: The leaderboard image.
        :rtype: :class:`PIL.Image.Image`
        """
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
        self, ctx: PokeGambler,
        data: Dict, heading: bool = False
    ) -> Image.Image:
        """Generates a Rank Card for a user.

        :param ctx: The PokeGambler client object.
        :type ctx: :class:`bot.PokeGambler`
        :param data: The data to be used to generate the rank card.
        :type data: Dict
        :param heading: Whether or not to include the rank card heading.
        :type heading: bool
        :return: The rank card image.
        :rtype: :class:`PIL.Image.Image`
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
        ).avatar.with_size(512).save(avatar_byio)
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
        self.profileframe = Image.open(
            os.path.join(asset_path, "basecards", "profileframe.png")
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
        self, name: str, avatar: Image.Image,
        balance: str, num_played: str, num_won: str,
        badges: Optional[List[Image.Image]] = None,
        blacklisted: bool = False,
        background: Image.Image = None
    ) -> Image.Image:
        """Returns the profile card for a user.

        :param name: The user\'s name.
        :type name: str
        :param avatar: The user\'s avatar.
        :type avatar: :class:`PIL.Image.Image`
        :param balance: The user\'s current balance.
        :type balance: str
        :param num_played: The number of matches the user has played.
        :type num_played: str
        :param num_won: The number of matches the user has won.
        :type num_won: str
        :param badges: The badges the user has earned.
        :type badges: Optional[List[:class:`PIL.Image.Image`]]
        :param blacklisted: Whether or not the user is blacklisted.
        :type blacklisted: bool
        :param background: The user\'s background image.
        :type background: :class:`PIL.Image.Image`
        :return: The profile card
        :rtype: :class:`PIL.Image.Image`
        """

        # pylint: disable=too-many-locals

        if background:
            profilecard = background.convert('RGBA')
            profilecard.paste(
                self.profileframe,
                (0, 0),
                self.profileframe
            )
            profilecard.convert('RGB')
        else:
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
            profilecard = self.__add_bl_effect(profilecard)
        return profilecard

    def __add_bl_effect(self, profilecard: Image.Image) -> Image.Image:
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
        """Returns the balance card for a user.

        :param data: The user's data.
        :type data: Dict
        :return: The balance card
        :rtype: :class:`PIL.Image.Image`
        """
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
