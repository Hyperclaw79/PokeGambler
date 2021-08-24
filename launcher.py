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
