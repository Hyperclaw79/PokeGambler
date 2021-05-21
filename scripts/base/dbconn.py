"""
The Database Wrapper Module.
"""

# pylint: disable=too-many-public-methods, too-many-lines

import sqlite3
from typing import Dict, List, Union


def encode_type(val):
    """
    SQLize numbers and strings.
    """
    if str(val).replace('.', '').replace(
        '+', ''
    ).replace('-', '').isdigit():
        return val
    return f'"{val}"'


def resolve_type(val):
    """
    Resolve SQLized strings and numbers.
    """
    ret_val = val
    if any(
        state in val
        for state in ["True", "False"]
    ):
        ret_val = val.strip('"') == 'True'
    elif all([
        val.startswith('"'),
        val.endswith('"')
    ]):
        ret_val = val.strip('"')
    elif all([
        val.count('.') == 1,
        val.replace('.', '').replace(
            '+', ''
        ).replace('-', '').isdigit()
    ]):
        ret_val = float(val)
    elif val.replace(
        '+', ''
    ).replace('-', '').isdigit():
        ret_val = int(val)
    return ret_val


def dict2str(dic: Dict) -> str:
    """
    Dictionary to SQLized string.
    """
    return ", ".join(
        f"{key}: {encode_type(val)}"
        for key, val in dic.items()
    )


def str2dict(sql_str: str) -> Dict:
    """
    SQLized string to Dictionary
    """
    return {
        kw.split(': ')[0]: resolve_type(kw.split(': ')[1])
        for kw in sql_str.decode().split(', ')
    }


sqlite3.register_adapter(bool, str)
sqlite3.register_converter("BOOLEAN", lambda v: v == b'True')
sqlite3.register_adapter(
    list, lambda l: ', '.join(
        str(encode_type(elem))
        for elem in l
    )
)

sqlite3.register_converter(
    "LIST",
    lambda v: [
        resolve_type(elem)
        for elem in v.decode().split(', ')
    ]
)
sqlite3.register_adapter(dict, dict2str)
sqlite3.register_converter("DICT", str2dict)


class DBConnector:
    """The API for transacting with the local Databse.
    The database being used is a simple SQLite DB.

    Attributes
    ----------
    db_path : str
        the path to the local database file.
    """
    def __init__(self, db_path: str = "pokegambler.db"):
        self.conn = sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        # self.conn.set_trace_callback(print)
        self.conn.execute("PRAGMA foreign_keys = 1")
        self.cursor = self.conn.cursor()
        self.conn.create_function("in_list", 2, self.in_list)
        self.conn.create_function("is_winner", 2, self.is_winner)

    @staticmethod
    def in_list(uid, values):
        """
        Custom SQL fn which checks if the uid is in the list of values.
        """
        return uid in values.split(", ")

    @staticmethod
    def is_winner(user_id, winner):
        """
        Custom SQL fn which checks if user_id is the winner.
        """
        return int(user_id == winner)

    @staticmethod
    def format_val(val):
        """
        Internal SQLizing function.
        """
        ret_val = val
        if isinstance(val, (str, bool)):
            ret_val = f'"{val}"'
        elif isinstance(val, (int, float)):
            ret_val = str(val)
        elif val is None:
            ret_val = "null"
        return ret_val

# DDL

# Creation
    def create_profile_table(self):
        """
        SQL endpoint for Profile table creation.
        """
        self.cursor.execute(
            '''
            CREATE TABLE
            IF NOT EXISTS
            profile(
                user_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                balance INT DEFAULT "100" NOT NULL,
                num_matches INT DEFAULT "0" NOT NULL,
                num_wins INT DEFAULT "0" NOT NULL,
                purchased_chips INT DEFAULT "0" NOT NULL,
                won_chips INT DEFAULT "0" NOT NULL,
                is_dealer BOOLEAN DEFAULT "0" NOT NULL
            );
            '''
        )
        self.conn.commit()

    def create_commands_table(self):
        """
        SQL endpoint for Commands table creation.
        """
        self.cursor.execute(
            '''
            CREATE TABLE
            IF NOT EXISTS
            commands(
                user_id TEXT NOT NULL,
                user_is_admin BOOLEAN DEFAULT "0" NOT NULL,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                channel TEXT NOT NULL,
                guild TEXT NOT NULL,
                command TEXT NOT NULL,
                args LIST,
                kwargs DICT
            );
            '''
        )
        self.conn.commit()

    def create_blacklists_table(self):
        """
        SQL endpoint for Blacklists table creation.
        """
        self.cursor.execute(
            '''
            CREATE TABLE
            IF NOT EXISTS
            blacklists(
                user_id TEXT NOT NULL,
                blacklisted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                blacklisted_by TEXT NOT NULL,
                reason TEXT
            );
            '''
        )
        self.conn.commit()

    def create_matches_table(self):
        """
        SQL endpoint for Match History table creation.
        """
        self.cursor.execute(
            '''
            CREATE TABLE
            IF NOT EXISTS
            matches(
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                started_by TEXT NOT NULL,
                participants LIST NOT NULL,
                winner TEXT,
                deal_cost INT DEFAULT "50" NOT NULL,
                lower_wins BOOLEAN DEFAULT FALSE NOT NULL,
                by_joker BOOLEAN DEFAULT FALSE NOT NULL,
                FOREIGN KEY (winner)
                    REFERENCES profile (user_id)
                    ON DELETE SET NULL
            );
            '''
        )
        self.conn.commit()

    def create_flips_table(self):
        """
        SQL endpoint for QuickFlip table creation.
        """
        self.cursor.execute(
            '''
            CREATE TABLE
            IF NOT EXISTS
            flips(
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                played_by TEXT,
                cost INT NOT NULL,
                won BOOLEAN NOT NULL,
                FOREIGN KEY (played_by)
                    REFERENCES profile (user_id)
                    ON DELETE SET NULL
            );
            '''
        )
        self.conn.commit()

    def create_moles_table(self):
        """
        SQL endpoint for Whackamole table creation.
        """
        self.cursor.execute(
            '''
            CREATE TABLE
            IF NOT EXISTS
            moles(
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                played_by TEXT,
                cost INT NOT NULL,
                level INT NOT NULL,
                won BOOLEAN NOT NULL,
                FOREIGN KEY (played_by)
                    REFERENCES profile (user_id)
                    ON DELETE SET NULL
            );
            '''
        )
        self.conn.commit()

    def create_loots_table(self):
        """
        SQL endpoint for Loots table creation.
        """
        self.cursor.execute(
            '''
            CREATE TABLE
            IF NOT EXISTS
            loots(
                user_id TEXT,
                tier INT DEFAULT "1" NOT NULL,
                loot_boost INT DEFAULT "1" NOT NULL,
                treasure_boost INT DEFAULT "1" NOT NULL,
                earned INT DEFAULT "0" NOT NULL,
                daily_claimed_on TIMESTAMP NOT NULL,
                daily_streak INT DEFAULT "0" NOT NULL,
                FOREIGN KEY (user_id)
                    REFERENCES profile (user_id)
                    ON DELETE SET NULL
            );
            '''
        )
        self.conn.commit()

    def create_items_table(self):
        """
        SQL endpoint for Loots table creation.
        """
        self.cursor.execute(
            '''
            CREATE TABLE
            IF NOT EXISTS
            items(
                itemid INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                asset_url TEXT NOT NULL,
                emoji TEXT NOT NULL,
                buyable BOOLEAN DEFAULT 'True' NOT NULL,
                sellable BOOLEAN DEFAULT 'True' NOT NULL,
                price INT NULL
            );
            '''
        )
        self.conn.commit()

    def create_iventory_table(self):
        """
        SQL endpoint for Loots table creation.
        """
        self.cursor.execute(
            '''
            CREATE TABLE
            IF NOT EXISTS
            inventory(
                user_id TEXT NOT NULL,
                itemid INT NOT NULL,
                obtained_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id)
                    REFERENCES profile (user_id)
                    ON DELETE SET NULL,
                FOREIGN KEY (itemid)
                    REFERENCES items (itemid)
                    ON DELETE SET NULL
            );
            '''
        )
        self.conn.commit()

    def create_tables(self):
        """
        SQL endpoint for triggering multiple table creations.
        """
        for attr in dir(self):
            if all([
                attr.endswith("_table"),
                attr.startswith("create_")
            ]):
                getattr(self, attr)()

# Purges

    def purge_commands(self):
        """
        SQL endpoint for purging Commands table.
        """
        self.cursor.execute(
            '''
            DELETE FROM commands;
            '''
        )
        self.conn.commit()

    def purge_profile(self):
        """
        SQL endpoint for purging Profile table.
        """
        self.cursor.execute(
            '''
            DELETE FROM profile;
            '''
        )
        self.conn.commit()

    def purge_blacklists(self):
        """
        SQL endpoint for purging Blacklists table.
        """
        self.cursor.execute(
            '''
            DELETE FROM blacklists;
            '''
        )
        self.conn.commit()

    def purge_matches(self):
        """
        SQL endpoint for purging Matches table.
        """
        self.cursor.execute(
            '''
            DELETE FROM matches;
            '''
        )
        self.conn.commit()

    def purge_flips(self):
        """
        SQL endpoint for purging Flips table.
        """
        self.cursor.execute(
            '''
            DELETE FROM flips;
            '''
        )
        self.conn.commit()

    def purge_moles(self):
        """
        SQL endpoint for purging Moles table.
        """
        self.cursor.execute(
            '''
            DELETE FROM moles;
            '''
        )
        self.conn.commit()

    def purge_loots(self):
        """
        SQL endpoint for purging Loots table.
        """
        self.cursor.execute(
            '''
            DELETE FROM loots;
            '''
        )
        self.conn.commit()

    def purge_items(self):
        """
        SQL endpoint for purging Items table.
        """
        self.cursor.execute(
            '''
            DELETE FROM items;
            '''
        )
        self.conn.commit()

    def purge_inventory(self):
        """
        SQL endpoint for purging Inventory table.
        """
        self.cursor.execute(
            '''
            DELETE FROM inventory;
            '''
        )
        self.conn.commit()

    def purge_tables(self):
        """
        SQL endpoint for triggering multiple table purges.
        """
        for attr in dir(self):
            if all([
                attr.startswith("purge_"),
                not attr.endswith("tables")
            ]):
                getattr(self, attr)()

# UnlockedModel

    def get_existing(self, model: str, user_id: str) -> Dict:
        """
        SQL endpoint for getting existing results from UnlockedModel type table.
        """
        self.cursor.execute(
            f'''
            SELECT * FROM {model}
            WHERE user_id IS ?
            ''',
            (user_id,)
        )
        res = self.cursor.fetchone()
        if res:
            names = (col[0] for col in self.cursor.description)
            return dict(zip(names, res))
        return None

    def save_model(self, model: str, **kwargs) -> int:
        """
        Saves the model in the database and returns the primary key to it.
        """
        keys, vals = zip(*kwargs.items())
        self.cursor.execute(
            f'''
            INSERT OR IGNORE INTO {model}
            ({', '.join(keys)})
            VALUES
            ({', '.join(['?'] * len(vals))});
            ''',
            tuple(vals)
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def update_model(self, model: str, user_id: str, **kwargs):
        """
        SQL endpoint for UnlockedModel type table Updation.
        """
        items = ", ".join(
            f"{key} = {self.format_val(val)}"
            for key, val in kwargs.items()
        )

        self.cursor.execute(
            f'''
            UPDATE {model}
            SET {items}
            WHERE user_id = ?;
            ''',
            (user_id, )
        )
        self.conn.commit()

# Commands

    def get_command_history(self, limit: int = 5, **kwargs) -> List:
        """
        Retrieves the list of commands used.
        """
        keys = [
            "user_id", "user_is_admin", "used_at", "channel",
            "guild", "command", "args", "kwargs"
        ]
        where_clause = ""
        if kwargs:
            if "user_is_admin" in kwargs.keys():
                kwargs["user_is_admin"] = "1" if kwargs["user_is_admin"] else "0"
            kwarg_str = ' AND '.join(f'{key} IS "{val}"' for key, val in kwargs.items())
            where_clause = f"WHERE {kwarg_str}"
        self.cursor.execute(
            f'''
            SELECT * FROM commands
            {where_clause}
            ORDER BY used_at DESC
            LIMIT ?
            ''',
            (limit, )
        )
        results = self.cursor.fetchall()
        if results:
            cmds = []
            for res in results:
                cmd = {
                    col: res[idx]
                    for idx, col in enumerate(keys)
                }
                cmds.append(cmd)
            return cmds
        return None

# Profile

    def get_full_profile(self, user_id: str) -> Dict:
        """
        Returns info about the user obtained from joining
        Profile and Loots tables.
        """
        self.cursor.execute(
            """
            SELECT * FROM profile
            JOIN loots
            USING (user_id)
            WHERE user_id IS ?;
            """,
            (user_id, )
        )
        res = self.cursor.fetchone()
        if res:
            names = (col[0] for col in self.cursor.description)
            return dict(zip(names, res))
        return None

    def get_leaderboard(self, sort_by: str = "num_wins") -> List:
        """
        SQL endpoint for fetching the Leaderbaord.
        Sorts according to num_wins by default. Can accept Balance as well.
        """
        if sort_by == "num_wins":
            sort_by = "win_rate DESC, num_wins DESC, balance"
        self.cursor.execute(
            f'''
            SELECT
                user_id, name, balance,
                num_wins, num_matches,
                (
                    CAST(num_wins AS FLOAT) / CAST(num_matches AS FLOAT)
                ) AS win_rate
            FROM profile
            WHERE num_matches > 0
            ORDER BY {sort_by} DESC
            LIMIT 10;
            '''
        )
        results = self.cursor.fetchall()
        if results:
            profiles = []
            for res in results:
                profile = {
                    col: res[idx]
                    for idx, col in enumerate([
                        "user_id", "name", "balance",
                        "num_wins", "num_matches", "win_rate"
                    ])
                }
                profiles.append(profile)
            return profiles
        return None

    def get_rank(self, user_id: str) -> int:
        """
        SQL endpoint for fetching User Rank.
        """
        self.cursor.execute(
            '''
            SELECT RowNum FROM (
                SELECT user_id, ROW_NUMBER () OVER (
                        ORDER BY CAST(
                            num_wins AS FLOAT
                        ) / CAST(
                            num_matches AS FLOAT
                        ) DESC, num_wins DESC
                    ) RowNum
                FROM profile
                WHERE num_matches > 0
            )
            WHERE user_id IS ?;
            ''',
            (user_id, )
        )
        res = self.cursor.fetchone()
        if res:
            return res[0]
        return None

    def is_emperor(self, user_id: str) -> bool:
        """
        SQL endpoint for checking if user is the richest.
        """
        self.cursor.execute(
            '''
            SELECT user_id FROM profile
            WHERE balance > 100
            ORDER BY balance DESC
            LIMIT 1;
            '''
        )
        res = self.cursor.fetchone()
        if res:
            return res[0] == user_id
        return False

    def is_champion(self, user_id: str) -> bool:
        """
        SQL endpoint for checking if user is the ultimate victor.
        """
        self.cursor.execute(
            '''
            SELECT user_id FROM profile
            WHERE num_wins > 0
            ORDER BY num_wins DESC, num_matches DESC
            LIMIT 1;
            '''
        )
        res = self.cursor.fetchone()
        if res:
            return res[0] == user_id
        return False

    def is_top_funder(self, user_id: str) -> bool:
        """
        SQL endpoint for checking if user is the best patron.
        """
        self.cursor.execute(
            '''
            SELECT user_id FROM profile
            WHERE purchased_chips > 100
            ORDER BY purchased_chips DESC
            LIMIT 1;
            '''
        )
        res = self.cursor.fetchone()
        if res:
            return res[0] == user_id
        return False

# Blacklists

    def get_blacklists(self, limit: int = 10) -> List:
        """
        Retrieves all blacklisted users.
        """
        keys = [
            "user_id", "blacklisted_at", "reason"
        ]
        self.cursor.execute(
            '''
            SELECT * FROM blacklists
            ORDER BY blacklisted_at DESC
            LIMIT ?
            ''',
            (limit, )
        )
        results = self.cursor.fetchall()
        if results:
            blks = []
            for res in results:
                blk = {
                    col: res[idx]
                    for idx, col in enumerate(keys)
                }
                blks.append(blk)
            return blks
        return None

    def is_blacklisted(self, user_id: str) -> bool:
        """
        SQL endpoint for checking if user is blacklisted.
        """
        self.cursor.execute(
            '''
            SELECT * FROM blacklists
            WHERE user_id = ?
            ''',
            (user_id, )
        )
        res = self.cursor.fetchone()
        return bool(res)

    def pardon_user(self, user_id: str) -> None:
        """
        SQL endpoint for pardoning a blacklisted user.
        """
        self.cursor.execute(
            '''
            DELETE FROM blacklists
            WHERE user_id = ?
            ''',
            (user_id, )
        )
        self.conn.commit()

# Matches

    def get_match_stats(self, user_id:str) -> List:
        """
        Gets the Wins and Losses for every participated match.
        """
        self.cursor.execute(
            f"""
            SELECT is_winner("{user_id}", winner) FROM matches
            WHERE in_list("{user_id}", participants)
            """
        )
        return [
            res[0]
            for res in self.cursor.fetchall()
        ]

# Flips

    def get_flips(self, user_id: str, wins: bool = False) -> List:
        """
        Gets the QuickFlip data of a particular player.
        """
        query = f'''
        SELECT * FROM flips
        WHERE played_by IS "{user_id}"
        '''
        if wins:
            query += '\nAND won = "True"'
        self.cursor.execute(query)
        res = self.cursor.fetchall()
        if res:
            return res
        return None

    def get_flips_lb(self) -> List[Union[str, int]]:
        """
        Returns player_id, total_played, total_wins for QuickFlip.
        Sorted according to total wins.
        """
        self.cursor.execute(
            """
            WITH winners AS (
                SELECT
                    COUNT(inner_fp.played_by) AS tw,
                    SUM(inner_fp.cost) AS te
                FROM flips inner_fp
                WHERE inner_fp.played_by = fp.played_by
                AND won = 'True'
            )
            SELECT
                fp.played_by,
                COUNT(*) AS total_played,
                (SELECT tw FROM winners) AS total_wins,
                (SELECT te FROM winners) AS total_earned
            FROM flips fp
            GROUP BY played_by
            ORDER BY total_earned DESC;
            """
        )
        res = self.cursor.fetchall()
        if not res:
            return []
        return res

# Moles

    def get_moles(self, user_id: str, wins: bool = False) -> List:
        """
        Gets the WhackaMole data of a particular player.
        """
        query = f'''
        SELECT * FROM moles
        WHERE played_by IS "{user_id}"
        '''
        if wins:
            query += '\nAND won = "True"'
        self.cursor.execute(query)
        res = self.cursor.fetchone()
        if res:
            return {
                col: res[idx]
                for idx, col in enumerate([
                    "played_at", "cost", "level",
                    "won", "played_by"
                ])
            }
        return None

    def get_moles_lb(self) -> List[Union[str, int]]:
        """
        Returns player_id, total_played, total_wins for WhackaMole.
        Sorted according to total wins.
        """
        self.cursor.execute(
            """
            WITH winners AS (
                SELECT
                    COUNT(inner_ml.played_by)
                FROM moles inner_ml
                WHERE inner_ml.played_by = ml.played_by
                AND won = 'True'
            )
            SELECT
                ml.played_by,
                COUNT(*) AS total_played,
                (SELECT * FROM winners) AS total_wins
            FROM moles ml
            GROUP BY played_by
            ORDER BY COUNT(won) DESC, level DESC;
            """
        )
        res = self.cursor.fetchall()
        if not res:
            return []
        return res

# Items

    def save_item(self, **kwargs) -> int:
        """
        Saves the model in the database and returns the primary key to it.
        """
        keys, vals = zip(*kwargs.items())
        self.cursor.execute(
            f'''
            INSERT OR IGNORE INTO items
            ({', '.join(keys)})
            VALUES
            ({', '.join(['?'] * len(vals))});
            ''',
            tuple(vals)
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def get_item(self, itemid: int) -> Dict:
        """
        SQL endpoint for getting an Item with id.
        """
        self.cursor.execute(
            '''
            SELECT * FROM items
            WHERE itemid IS ?
            ''',
            (itemid,)
        )
        res = self.cursor.fetchone()
        if res:
            names = (col[0] for col in self.cursor.description)
            return dict(zip(names, res))
        return None

    def delete_item(self, itemid: int) -> None:
        """
        SQL endpoint for deleting an Item with id.
        """
        self.cursor.execute(
            '''
            DELETE FROM items
            WHERE itemid IS ?
            ''',
            (itemid,)
        )
        self.conn.commit()

    def get_tradables(self, limit: int = 10) -> List:
        """
        SQL endpoint for getting a list of Tradables.
        Useful for displaying them in a shop.
        A limit can be provided, defaults to 10.
        """
        self.cursor.execute(
            '''
            SELECT * FROM items
            WHERE category IS "Tradable"
            LIMIT ?;
            ''',
            (limit,)
        )
        results = self.cursor.fetchall()
        if results:
            names = [
                col[0]
                for col in self.cursor.description
            ]
            return [
                dict(zip(names, res))
                for res in results
            ]
        return None

    def get_collectibles(self, limit: int = 10) -> List:
        """
        SQL endpoint for getting a list of Collectibles.
        Useful for trading with other players.
        A limit can be provided, defaults to 10.
        """
        self.cursor.execute(
            '''
            SELECT * FROM items
            WHERE category IS "Collectible"
            LIMIT ?;
            ''',
            (limit,)
        )
        results = self.cursor.fetchall()
        if results:
            names = [
                col[0]
                for col in self.cursor.description
            ]
            return [
                dict(zip(names, res))
                for res in results
            ]
        return None

    def get_treasures(self, limit: int = 10) -> List:
        """
        SQL endpoint for getting a list of Treasures.
        Useful for flexing in the inventory.
        A limit can be provided, defaults to 10.
        """
        self.cursor.execute(
            '''
            SELECT * FROM items
            WHERE category IS "Treasure"
            ORDER BY itemid DESC
            LIMIT ?;
            ''',
            (limit,)
        )
        results = self.cursor.fetchall()
        if results:
            names = [
                col[0]
                for col in self.cursor.description
            ]
            return [
                dict(zip(names, res))
                for res in results
            ]
        return None

# Inventory

    def get_inventory_items(self, user_id: str, display_mode=False) -> List:
        """
        SQL endpoint for getting a list of items in a user's Inventory.
        If counts_only is True, it will return a list of item names and their counts.
        """
        if display_mode:
            statement = '''SELECT
                items.name,
                Count(items.name) AS count,
                items.category,
                items.emoji,
                Coalesce(Sum(items.price), 0) AS 'Net Worth'
            FROM inventory
            JOIN items
            USING(itemid)
            WHERE user_id IS ?
            GROUP BY items.name
            ORDER BY
                CASE category
                    WHEN 'Teasure' THEN 1
                    WHEN 'Chest' THEN 2
                    WHEN 'Tradable' THEN 3
                    WHEN 'Collectible' THEN 4
                END, (count * items.price) DESC;
            '''
        else:
            statement = '''
            SELECT items.*
            FROM inventory
            JOIN items
            USING(itemid)
            WHERE user_id IS ?
            ORDER BY
                CASE category
                    WHEN 'Teasure' THEN 1
                    WHEN 'Chest' THEN 2
                    WHEN 'Tradable' THEN 3
                    WHEN 'Collectible' THEN 4
                END, (count * items.price) DESC;
            '''
        self.cursor.execute(statement, (user_id, ))
        results = self.cursor.fetchall()
        if results:
            names = [
                col[0]
                for col in self.cursor.description
            ]
            return [
                dict(zip(names, res))
                for res in results
            ]
        return None

    def get_inv_ids(self, user_id: str, name: str) -> List:
        """
        SQL endpoint for listing IDs of an Item in user's inventory.
        """
        self.cursor.execute(
            '''
            SELECT items.itemid
            FROM inventory
            JOIN items
            USING(itemid)
            WHERE
                user_id IS ?
                AND items.name is ?
            ''',
            (user_id, name)
        )
        results = self.cursor.fetchall()
        if results:
            return [
                res[0]
                for res in results
            ]
        return None

if __name__ == "__main__":
    dbconn = DBConnector(db_path='data/pokegambler.db')
