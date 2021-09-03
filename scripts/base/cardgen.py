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

The Base Card Generation Module
"""
import os
import random
from typing import List, Optional

from PIL import Image


class CardGambler:
    """
    The Pokecard Generator class.

    :param assets_path: The path to the asset folder.
    :type assets_path: str
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, assets_path: str = "assets"):
        self.asset_path = assets_path
        self.pokecards_path = os.path.join(self.asset_path, "pokecards")
        self.basecards_path = os.path.join(self.asset_path, "basecards")
        self.suits = os.listdir(self.pokecards_path)
        self.cards = os.listdir(
            os.path.join(self.pokecards_path, self.suits[0])
        )
        self.closed_card = Image.open(
            os.path.join(self.basecards_path, "pokecards-back.jpg")
        )
        self.joker_card = Image.open(
            os.path.join(self.basecards_path, "pokecards-joker.jpg")
        )
        self.watermark = Image.open(
            os.path.join(self.basecards_path, "pokecards-watermark.png")
        )

    def get_card(self, suit: str, card: str) -> Image.Image:
        """Gets the image of a specific card.

        :param suit: The suit of the card.
        :type suit: str
        :param card: The card number.
        :type card: str
        :return: The image of the card.
        :rtype: :class:`PIL.Image.Image`
        """
        if ".jpg" not in card:
            card = f"{card.upper()}.jpg"
        facecard = Image.open(
            os.path.join(self.pokecards_path, suit, card)
        ).convert('RGBA')
        return Image.alpha_composite(facecard, self.watermark).convert('RGB')

    @staticmethod
    def get_deck(
        cards: List[Image.Image],
        sep: Optional[str] = "auto",
        reverse: Optional[bool] = False
    ) -> Image.Image:
        """Gets a deck generated from a list of cards.

        :param cards: The list of cards to generate the deck from.
        :type cards: List[:class:`PIL.Image.Image`]
        :param sep: The seperation width, defaults to "auto"
        :type sep: Optional[str]
        :param reverse: Stack the cards in reverse?, defaults to False
        :type reverse: Optional[bool]
        :return: The deck image.
        :rtype: :class:`PIL.Image.Image`
        """
        width, height = cards[0].size
        if sep == "auto":
            sep = width // 2
        deck_size = (width + sep * (len(cards) - 1), height)
        deck = Image.new("RGB", deck_size, (0, 0, 0))
        if reverse:
            for i, card in enumerate(cards[::-1]):
                deck.paste(
                    card,
                    (deck_size[0] - ((i * sep) + width), 0)
                )
        else:
            for i, card in enumerate(cards):
                deck.paste(
                    card,
                    ((i * sep), 0)
                )
        return deck

    def get_closed_deck(
        self, sep: Optional[int] = 5,
        num_cards: Optional[int] = 12
    ) -> Image.Image:
        """Gets a deck of closed cards.

        :param sep: The seperation width, defaults to 5
        :type sep: Optional[int]
        :param num_cards: Number of cards, defaults to 12
        :type num_cards: Optional[int]
        :return: The closed deck image.
        :rtype: :class:`PIL.Image.Image`
        """
        cards = [self.closed_card for i in range(num_cards)]
        return self.get_deck(cards, sep=sep, reverse=True)

    def get_random_card(self) -> Image.Image:
        """Alias for :func:`get_random_cards` with ``num_cards = 1``.

        :return: Random card.
        :rtype: :class:`PIL.Image.Image`
        """
        return self.get_random_cards(num_cards=1)[0]

    def get_random_cards(
        self, num_cards: Optional[int] = 4,
        joker_chance: Optional[float] = 0.05
    ) -> List[Image.Image]:
        """Gets a list of random cards.

        :param num_cards: Number of cards, defaults to 4
        :type num_cards: Optional[int]
        :param joker_chance: Chance of including a Joker, defaults to 0.05
        :type joker_chance: Optional[float]
        :return: A list of random cards.
        :rtype: List[:class:`PIL.Image.Image`]
        """
        cards = []
        joker_drawn = False
        for _ in range(num_cards):
            card = random.choice(self.cards)
            card_num = card.split(".jpg")[0]
            suit = random.choice(self.suits)
            while (card_num, suit) in (
                (card_["card_num"], card_["suit"])
                for card_ in cards
            ):
                card = random.choice(self.cards)
                card_num = card.split(".jpg")[0]
            if all([
                (random.randint(1, 100) / 100) <= joker_chance,
                not joker_drawn
            ]):
                suit = "joker"
                card_num = "Joker"
                card_img = self.joker_card.copy()
                joker_drawn = True
            else:
                card_img = self.get_card(suit, card)
            cards.append({
                "card_num": card_num,
                "suit": suit,
                "card_img": card_img
            })
        random.shuffle(cards)
        return cards

    def get_random_deck(
        self, num_cards: Optional[int] = 12,
        **kwargs
    ) -> Image.Image:
        """Gets a deck generated from a list of random cards.

        :param num_cards: Number of cards, defaults to 12
        :type num_cards: Optional[int]
        :return: The deck image consisting of random cards.
        :rtype: :class:`PIL.Image.Image`
        """
        cards = [
            self.get_random_card()[1]
            for _ in range(num_cards)
        ]
        return self.get_deck(cards, **kwargs)
