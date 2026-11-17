from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import load_config
from bot.database.db import create_pool, init_db
from bot.handlers import admin, user
from bot.middlewares.config import ConfigMiddleware
from bot.middlewares.db import DbSessionMiddleware


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
    )


async def main() -> None:
    setup_logging()

    config = load_config()
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    pool = await create_pool(config.database_url)
    await init_db(pool, client_code_start=config.client_code_start)

    dp.update.middleware(ConfigMiddleware(config))
    dp.update.middleware(DbSessionMiddleware(pool))

    dp.include_router(admin.router)
    dp.include_router(user.router)

    logging.getLogger(__name__).info(
        "Bot started. Admins=%s", ",".join(str(x) for x in sorted(config.admin_ids))
    )

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())

