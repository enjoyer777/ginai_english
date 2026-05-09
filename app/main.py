from __future__ import annotations

import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
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

    # Опциональный прокси к api.telegram.org. Используется, если RU-провайдер
    # фильтрует Telegram. Поддерживает socks5://, socks4://, http://.
    # Пустая переменная или её отсутствие → прямое соединение.
    telegram_proxy = (os.getenv("TELEGRAM_PROXY") or "").strip() or None
    if telegram_proxy:
        logger.info("Using outbound proxy for Telegram: {}", _safe_proxy_repr(telegram_proxy))
    session = AiohttpSession(proxy=telegram_proxy) if telegram_proxy else AiohttpSession()

    bot = Bot(
        token=settings.tg_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    dp = Dispatcher()
    dp.include_router(router)

    me = await bot.get_me()
    logger.info("Bot authorized as @{} (id={})", me.username, me.id)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


def _safe_proxy_repr(url: str) -> str:
    """Прячет пароль из URL прокси для лога (socks5://user:pass@host:port → socks5://user:***@host:port)."""
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    creds, hostpart = rest.rsplit("@", 1)
    if ":" in creds:
        user, _ = creds.split(":", 1)
        return f"{scheme}://{user}:***@{hostpart}"
    return f"{scheme}://***@{hostpart}"


if __name__ == "__main__":
    asyncio.run(main())
