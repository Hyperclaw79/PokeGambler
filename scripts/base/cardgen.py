"""
The Base Card Generation Module
"""
import os
import random

from PIL import Image


class CardGambler:
    """
    The Pokecard Generator class.
    """
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

    def get_card(self, suit: str, card: str):
        """
        Gets the image of a specific card.
        """
        if ".jpg" not in card:
            card = f"{card.upper()}.jpg"
        return Image.open(
            os.path.join(self.pokecards_path, suit, card)
        )

    def get_random_cards(self, num_cards=4, joker_chance=0.05):
        """
        Gets a list of random cards.
        """
        cards = []
        joker_drawn = False
        for _ in range(num_cards):
            card = random.choice(self.cards)
            card_num = card.split(".jpg")[0]
            suit = random.choice(self.suits)
            if all([
                (random.randint(1, 100) / 100) <= joker_chance,
                not joker_drawn
            ]):
                suit = "joker"
                card_num = "Joker"
                card_img = self.joker_card.copy()
                joker_drawn = True
            else:
                card_img = Image.open(
                    os.path.join(self.pokecards_path, suit, card)
                )
            cards.append({
                "card_num": card_num,
                "suit": suit,
                "card_img": card_img
            })
        random.shuffle(cards)
        return cards

    def get_random_card(self):
        """
        Alias for get_random_cards(num_cards=1).
        """
        return self.get_random_cards(num_cards=1)[0]

    @staticmethod
    def get_deck(cards: list, sep="auto", reverse=False):
        """
        Gets a deck generated from list of cards.
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

    def get_random_deck(self, sep="auto", num_cards=12):
        """
        Gets a deck generated from a list of random cards.
        """
        cards = [self.get_random_card()[1] for i in range(num_cards)]
        return self.get_deck(cards, sep=sep)

    def get_closed_deck(self, sep=5, num_cards=12):
        """
        Gets a deck of closed cards.
        """
        cards = [self.closed_card for i in range(num_cards)]
        return self.get_deck(cards, sep=sep, reverse=True)
