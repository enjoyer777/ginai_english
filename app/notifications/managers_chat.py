"""Уведомления в групповой Telegram-чат менеджеров (FR-9).

Только в рабочее время (FR-6.4, FR-8.2). Дедуп: не чаще раза в N минут на одного клиента.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from loguru import logger

from app.config import settings
from app.state import repository as repo
from app.state.models import User
from app.utils.time import format_msk, now


async def notify_hot_lead(
    bot: Bot,
    user: User,
    deal_url: str,
) -> bool:
    """Возвращает True, если уведомление было отправлено; False если зарезано дедупом."""

    if await repo.was_notified_recently(user.tg_user_id):
        logger.info("Notification skipped (dedup window) for tg_user={}", user.tg_user_id)
        return False

    name = user.first_name or "—"
    handle = f"@{user.tg_username}" if user.tg_username else "—"
    text = (
        "🔥 Новый горячий лид из Telegram\n"
        f"👤 {name} ({handle})\n"
        f"💬 {deal_url}\n"
        f"🕐 {format_msk(now())}"
    )
    try:
        await bot.send_message(chat_id=settings.managers_chat_id, text=text)
        await repo.record_notification(user.tg_user_id)
        return True
    except TelegramAPIError as e:
        logger.error("Failed to notify managers chat: {}", e)
        return False
