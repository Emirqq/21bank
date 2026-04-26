from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_path: str
    admin_ids: set[int]
    starting_balance: float = 1000.0
    bot_name: str = "21БАНК"


def get_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set. Copy .env.example to .env and add your bot token.")

    database_name = os.getenv("DATABASE_PATH", "bot.db").strip() or "bot.db"
    admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
    admin_ids = {int(item.strip()) for item in admin_ids_raw.split(",") if item.strip()}

    bot_name = os.getenv("BOT_NAME", "21БАНК").strip() or "21БАНК"

    return Config(
        bot_token=token,
        database_path=str(BASE_DIR / database_name),
        admin_ids=admin_ids,
        bot_name=bot_name,
    )
