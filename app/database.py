from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3



def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.isolation_level = None
        self.conn.execute("PRAGMA foreign_keys = ON")

    @contextmanager
    def transaction(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        else:
            self.conn.execute("COMMIT")

    def execute(self, query: str, params: tuple = ()):
        return self.conn.execute(query, params)

    def fetchone(self, query: str, params: tuple = ()):
        return self.conn.execute(query, params).fetchone()

    def fetchall(self, query: str, params: tuple = ()):
        return self.conn.execute(query, params).fetchall()

    def initialize(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                display_name TEXT NOT NULL,
                wallet_balance REAL NOT NULL DEFAULT 1000,
                bank_balance REAL NOT NULL DEFAULT 0,
                deposit_balance REAL NOT NULL DEFAULT 0,
                deposit_updated_at TEXT NOT NULL,
                premium_level INTEGER NOT NULL DEFAULT 0,
                is_verified INTEGER NOT NULL DEFAULT 0,
                total_wagered REAL NOT NULL DEFAULT 0,
                total_won REAL NOT NULL DEFAULT 0,
                daily_streak INTEGER NOT NULL DEFAULT 0,
                last_daily_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS portfolios (
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, symbol),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS market (
                symbol TEXT PRIMARY KEY,
                price REAL NOT NULL,
                circulating_supply REAL NOT NULL,
                buy_pressure REAL NOT NULL DEFAULT 0,
                sell_pressure REAL NOT NULL DEFAULT 0,
                volatility REAL NOT NULL,
                floor_price REAL NOT NULL,
                ceiling_price REAL NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                counterparty_id INTEGER,
                kind TEXT NOT NULL,
                asset TEXT,
                amount REAL NOT NULL,
                fee REAL NOT NULL DEFAULT 0,
                note TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS achievements (
                user_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                unlocked_at TEXT NOT NULL,
                PRIMARY KEY (user_id, code),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS blackjack_sessions (
                user_id INTEGER PRIMARY KEY,
                bet REAL NOT NULL,
                player_hand TEXT NOT NULL,
                dealer_hand TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
            """
        )
        self.seed_market()

    def seed_market(self) -> None:
        if self.fetchone("SELECT symbol FROM market LIMIT 1"):
            return

        current_time = now_iso()
        with self.transaction():
            self.execute(
                """
                INSERT INTO market (
                    symbol, price, circulating_supply, buy_pressure, sell_pressure,
                    volatility, floor_price, ceiling_price, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("BTC", 28000.0, 40.0, 0.0, 0.0, 0.015, 8000.0, 90000.0, current_time),
            )
            self.execute(
                """
                INSERT INTO market (
                    symbol, price, circulating_supply, buy_pressure, sell_pressure,
                    volatility, floor_price, ceiling_price, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("ETH", 1800.0, 300.0, 0.0, 0.0, 0.02, 400.0, 12000.0, current_time),
            )
            self.execute(
                """
                INSERT INTO market (
                    symbol, price, circulating_supply, buy_pressure, sell_pressure,
                    volatility, floor_price, ceiling_price, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("TON", 6.0, 20000.0, 0.0, 0.0, 0.03, 1.0, 50.0, current_time),
            )

    def close(self) -> None:
        self.conn.close()
