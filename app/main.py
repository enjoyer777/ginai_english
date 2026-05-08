from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from app.bot.handlers import router
from app.config import settings
from app.kb.cache import get_snapshot
from app.state.db import init_db
from app.utils.logging import setup_logging


async def main() -> None:
    setup_logging()
    logger.info("Starting school_english_pro bot")

    await init_db()

    # Прогрев KB-кэша на старте — лучше упасть здесь, чем при первом сообщении
    snapshot = await get_snapshot()
    if snapshot is None:
        logger.warning("KB snapshot is empty at startup — bot will rely on fallbacks")
    else:
        logger.info(
            "KB warmed: {} courses, {} schedule slots",
            len(snapshot.courses),
            len(snapshot.schedules),
        )

    bot = Bot(
        token=settings.tg_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    me = await bot.get_me()
    logger.info("Bot authorized as @{} (id={})", me.username, me.id)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
