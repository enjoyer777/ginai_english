from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from loguru import logger

from app.bot.keyboards import CONTACT_BUTTON_TEXT, main_keyboard
from app.dialog import guardrails
from app.dialog.engine import handover_flow, process_user_message
from app.kb.cache import get_snapshot
from app.state import repository as repo

DEFAULT_GREETING = (
    "Здравствуйте! 👋 Я — AI-ассистент онлайн-школы английского school_english_pro. "
    "Помогу разобраться в курсах, ценах и расписании, либо соединю с менеджером."
)
DEFAULT_DISCLAIMER = (
    "Если оставите контакт, передам его менеджеру для связи. "
    "Все данные используем только чтобы помочь записаться на курс."
)

router = Router(name="main")


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    if message.from_user is None:
        return
    user = await repo.upsert_user(
        tg_user_id=message.from_user.id,
        tg_username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    snapshot = await get_snapshot()
    greeting = (snapshot.settings.greeting_text if snapshot else "") or DEFAULT_GREETING
    disclaimer = (snapshot.settings.pii_disclaimer if snapshot else "") or DEFAULT_DISCLAIMER
    text = f"{greeting}\n\n{disclaimer}"
    await message.answer(text, reply_markup=main_keyboard())
    logger.info("/start from tg_user={}", user.tg_user_id)


@router.message(F.text == CONTACT_BUTTON_TEXT)
async def on_contact_button(message: Message, bot: Bot) -> None:
    if message.from_user is None:
        return
    user = await repo.upsert_user(
        tg_user_id=message.from_user.id,
        tg_username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    reply = await handover_flow(bot, user)
    await message.answer(reply, reply_markup=main_keyboard())


@router.message(F.contact)
async def on_contact_share(message: Message) -> None:
    """Когда клиент шарит контакт через нативный share-button."""
    if message.from_user is None or message.contact is None:
        return
    await repo.upsert_user(
        tg_user_id=message.from_user.id,
        tg_username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    if message.contact.phone_number:
        await repo.set_contact_phone(message.from_user.id, message.contact.phone_number)
    await message.answer("Спасибо, телефон сохранён.", reply_markup=main_keyboard())


@router.message(F.text)
async def on_text(message: Message, bot: Bot) -> None:
    if message.from_user is None or message.text is None:
        return
    user = await repo.upsert_user(
        tg_user_id=message.from_user.id,
        tg_username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    reply = await process_user_message(bot, user, message.text)
    await message.answer(reply, reply_markup=main_keyboard())


# Голосовые / стикеры / фото / гифки — единый ответ (R-12, FR-11.3)
@router.message(F.voice | F.audio | F.video | F.video_note | F.sticker | F.photo | F.document | F.animation)
async def on_non_text(message: Message) -> None:
    if message.from_user is None:
        return
    await repo.upsert_user(
        tg_user_id=message.from_user.id,
        tg_username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    await message.answer(guardrails.NON_TEXT_RESPONSE, reply_markup=main_keyboard())


@router.message()
async def on_anything_else(message: Message) -> None:
    """Всё, что не поймали выше (например, чат-апдейты из группы менеджеров).

    Логируем chat_id, чтобы заказчик мог удобно его взять для .env.
    """
    chat = message.chat
    logger.info("Unhandled update in chat_id={} type={}", chat.id, chat.type)
