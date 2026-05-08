"""Простые предфильтры до похода в LLM (FR-11).

Цель — поймать дешёвые случаи (jailbreak / явный спам) и ответить шаблоном,
не тратя токены OpenAI и не давая модели шанс «сорваться».
"""

from __future__ import annotations

import re

JAILBREAK_PATTERNS = [
    r"\bзабудь\s+(все|всё)\s+инструкции",
    r"\bignore\s+(all\s+)?previous\s+instructions",
    r"\bты\s+теперь\s+не\s+бот",
    r"\bsystem\s+prompt",
    r"\bdeveloper\s+mode",
    r"\bDAN\b",
    r"\bjailbreak",
]

JAILBREAK_RESPONSE = (
    "Я ассистент школы school_english_pro и обсуждаю только курсы и обучение. "
    "Могу рассказать про программы или соединить с менеджером — что вам интереснее?"
)


def is_jailbreak_attempt(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(re.search(p, lower) for p in JAILBREAK_PATTERNS)


def is_empty_or_garbage(text: str) -> bool:
    """Сообщение, на которое осмысленного ответа не дать (только пробелы / только эмодзи)."""
    if not text or not text.strip():
        return True
    if len(text.strip()) < 2:
        return True
    # Только не-буквенно-цифровые символы (эмодзи, пунктуация)
    return not re.search(r"[\wЀ-ӿ]", text)


GARBAGE_RESPONSE = "Не уверен, что понял — расскажите, пожалуйста, словами, что хотите узнать."

NON_TEXT_RESPONSE = (
    "Я понимаю только текстовые сообщения. Опишите, пожалуйста, словами — "
    "и я постараюсь помочь с подбором курса или соединить с менеджером."
)
