"""
The launcher for bot.py which verifies Python version.
Also serves as gateway for system args.
"""

import argparse
import sys

from bot import PokeGambler

if __name__ == "__main__":
    if sys.version_info < (3, 7):
        print(
            f"You are running Python version v{sys.version.split()[0]}.\n"
            "But you require version v3.7 at least.\n"
            "Please retry after updating to the latest version.\n"
        )
    else:
        parser = argparse.ArgumentParser()
        default_dict = {
            "assets_path": "assets",
            "error_log_path": "errors.log"
        }
        for key, val in default_dict.items():
            parser.add_argument(
                f'--{key}',
                default=f'data/{val}'
            )
        parsed = parser.parse_args()
        bot = PokeGambler(**{
            key: getattr(parsed, key)
            for key in default_dict
        })
        bot.run()
