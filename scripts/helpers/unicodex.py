"""
Unicode based utilites
"""

from itertools import cycle
from typing import Tuple, Union


class UnicodeProgressBar:
    """
    A Progress bar generator using Unicode characters.
    """
    def __init__(
        self, total: int = 5,
        style: str = "squares"
    ):
        charmap = {
            "squares": {
                "base": '⬛',
                "seq": cycle([
                    '🟦', '🟩', '🟨',
                    '🟧', '🟥'
                ])
            },
            "circles": {
                "base": '⚫',
                "seq": cycle([
                    '🔵', '🟢', '🟡',
                    '🟠', '🔴'
                ])
            }
        }
        self.total = total
        self.base, self.seq = charmap.get(
            style.lower(), "squares"
        ).values()
        self.empty_bar = ''.join(self.base for _ in range(total))

    def __iter__(self):
        unicode_bar = self.empty_bar
        for idx, char in enumerate(self.seq):
            if idx >= self.total:
                break
            unicode_bar = unicode_bar.replace(self.base, char, 1)
            yield unicode_bar

    def get(self, count: int):
        """
        Return the progress bar at a specific count.
        """
        unicode_bar = self.empty_bar
        for idx, char in enumerate(self.seq):
            if idx > count - 1:
                break
            unicode_bar = unicode_bar.replace(self.base, char, 1)
        return unicode_bar


class Unicodex:
    """
    Unicode based utilites
    """
    @staticmethod
    def num2emojis(number: Union[str, int]) -> str:
        """
        Convert a number into a sequence of dicord emojis.
        """
        uninums = [
            ":zero:", ":one:", ":two:", ":three:", ":four:",
            ":five:", ":six:", ":seven:", ":eight:", ":nine:",
        ]
        return "".join(
            uninums[int(digit)]
            for digit in str(number)
        )

    @classmethod
    def format_streak(
        cls, streak: int,
        mode: str = "daily"
    ) -> Tuple[str, str]:
        """
        Format a streak for display.
        """
        emoji = ''
        count = streak % 5
        if not count and streak:
            emoji = '🎁' if mode == 'vote' else '⬆️'
            count = 5
        unipog = UnicodeProgressBar(total=5)
        return (
            f"**{mode.title()} Streak**: {cls.num2emojis(streak)}\n",
            f"`{unipog.get(count)}` {emoji}"
        )