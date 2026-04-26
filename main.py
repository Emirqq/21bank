import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import get_config
from app.database import Database
from app.handlers import create_router
from app.service import BotService


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    config = get_config()
    database = Database(config.database_path)
    database.initialize()

    service = BotService(
        db=database,
        starting_balance=config.starting_balance,
        admin_ids=config.admin_ids,
        bot_name=config.bot_name,
    )

    bot = Bot(token=config.bot_token)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(create_router(service))

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot)
    finally:
        database.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
