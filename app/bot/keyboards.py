from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

CONTACT_BUTTON_TEXT = "Связаться с менеджером"


def main_keyboard() -> ReplyKeyboardMarkup:
    """Постоянная reply-клавиатура с кнопкой связи (FR-7.1)."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=CONTACT_BUTTON_TEXT)]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Спросите про курсы или нажмите кнопку",
    )
