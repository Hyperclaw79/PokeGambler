"""
The Database Wrapper Module.
"""

import sqlite3


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


def dict2str(dic: dict) -> str:
    """
    Dictionary to SQLized string.
    """
    return ", ".join(
        f"{key}: {encode_type(val)}"
        for key, val in dic.items()
    )


def str2dict(sql_str: str) -> dict:
    """
    SQLized string to Dictionary
    """
    return {
        kw.split(': ')[0]: resolve_type(kw.split(': ')[1])
        for kw in sql_str.decode().split(', ')
    }


sqlite3.register_adapter(bool, str)
sqlite3.register_converter("BOOLEAN", lambda v: v == 'True')
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
        self.cursor = self.conn.cursor()

    @staticmethod
    def format_val(val):
        """
        Internal SQLizing function.
        """
        ret_val = val
        if isinstance(val, str):
            ret_val = f'"{val}"'
        elif isinstance(val, (int, float)):
            ret_val = str(val)
        elif isinstance(val, bool):
            val_num = 1 if val else 0
            ret_val = str(val_num)
        return ret_val

# DDL

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

    def purge_tables(self):
        """
        SQL endpoint for triggering multiple table purges.
        """
        for attr in dir(self):
            if attr.startswith("purge_"):
                getattr(self, attr)()

# DML

    def save_model(self, model, **kwargs):
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

    def get_command_history(self, limit: int = 5, **kwargs) -> list:
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

    def get_profile(self, user_id: str) -> dict:
        """
        SQL endpoint for Profile Retrieval.
        """
        self.cursor.execute(
            '''
            SELECT * FROM profile
            WHERE user_id IS ?
            ''',
            (user_id,)
        )
        res = self.cursor.fetchone()
        if res:
            return {
                col: res[idx]
                for idx, col in enumerate([
                    "user_id", "name", "balance",
                    "num_matches", "num_wins",
                    "purchased_chips", "won_chips",
                    "is_dealer"
                ])
            }
        return None

    def update_profile(self, user_id: str, **kwargs):
        """
        SQL endpoint for Profile Updation.
        """
        items = ", ".join(
            f"{key} = {self.format_val(val)}"
            for key, val in kwargs.items()
        )

        self.cursor.execute(
            f'''
            UPDATE profile
            SET {items}
            WHERE user_id = ?;
            ''',
            (user_id, )
        )
        self.conn.commit()

    def get_leaderboard(self, sort_by: str = "num_wins") -> list:
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
            WHERE balance > 0
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
            WHERE purchased_chips > 0
            ORDER BY purchased_chips DESC
            LIMIT 1;
            '''
        )
        res = self.cursor.fetchone()
        if res:
            return res[0] == user_id
        return False

if __name__ == "__main__":
    dbconn = DBConnector(db_path='data/pokegambler.db')
