"""Маскирование персональных данных (ПДн) перед отправкой в OpenAI.

Зачем: серверы OpenAI находятся в США — это трансграничная передача ПДн под
152-ФЗ, для которой нужно отдельное письменное согласие клиента + уведомление
Роскомнадзора. Маскирование позволяет работать с LLM, не отправляя за рубеж
конкретные идентифицирующие данные.

Что маскируем:
  - телефоны (российские и международные форматы)
  - email-адреса
  - сохранённое имя клиента (если LLM ранее извлекла его и мы записали в БД)

Что НЕ маскируем (и почему):
  - Telegram username, first_name из профиля TG — это псевдонимные данные,
    которые УЖЕ есть у самого Telegram. Мы их не передаём за пределы TG
    повторно при общении с ботом.
  - содержательную часть диалога (цели, уровень, мотивацию) — это нужно LLM
    для квалификации, и само по себе оно не идентифицирует субъекта.

API:
  pre_extract_phone(text) -> str | None      — для сохранения server-side
  pre_extract_email(text) -> str | None
  mask_message(text, saved_name=None) -> str — для подачи в LLM
"""

from __future__ import annotations

import re

# Телефон: +7..., 8..., с пробелами/тире/скобками, минимум 10 цифр после префикса.
# Намеренно жадно — лучше замаскировать лишнее, чем пропустить ПДн.
_PHONE_RE = re.compile(
    r"""
    (?<!\w)                              # не часть слова
    (?:                                  # начало номера:
        \+\s*\d                          #   +7, +1, и т.п.
        |
        8(?=[\s\-\(]?\d)                 #   8 перед цифрой (российский)
        |
        7(?=[\s\-\(]?\d)                 #   7 без + (тоже бывает)
    )
    (?:[\s\-\(\)\.]*\d){9,14}            # ещё 9-14 цифр со всякими разделителями
    (?!\w)                               # не середина слова
    """,
    re.VERBOSE,
)

# Email: стандартный
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)


def pre_extract_phone(text: str) -> str | None:
    """Вытаскивает первый телефонный паттерн из текста (для сохранения в БД)."""
    if not text:
        return None
    m = _PHONE_RE.search(text)
    if not m:
        return None
    return _digits_only_with_plus(m.group(0))


def pre_extract_email(text: str) -> str | None:
    if not text:
        return None
    m = _EMAIL_RE.search(text)
    return m.group(0) if m else None


def mask_message(text: str, saved_name: str | None = None) -> str:
    """Возвращает версию текста, безопасную для отправки в OpenAI.

    saved_name — имя клиента из БД (если есть). Подставленные клиентом упоминания
    собственного имени будут заменены на <имя>.
    """
    if not text:
        return text

    masked = _PHONE_RE.sub("<phone>", text)
    masked = _EMAIL_RE.sub("<email>", masked)

    if saved_name and len(saved_name.strip()) >= 2:
        # Целое слово, регистронезависимо. Не маскируем подстроки внутри слов
        # (чтобы случайно не зацепить кусок названия курса и т.п.).
        name_re = re.compile(
            r"\b" + re.escape(saved_name.strip()) + r"\b",
            re.IGNORECASE,
        )
        masked = name_re.sub("<имя>", masked)

    return masked


def _digits_only_with_plus(raw: str) -> str:
    """Чистит номер до канонического вида +XXXXXXXXXX (как _normalize_phone в engine,
    но локально, чтобы не плодить зависимости)."""
    cleaned = "".join(c for c in raw if c.isdigit() or c == "+")
    digits = cleaned.lstrip("+")
    if not digits.isdigit():
        return raw
    # российский «8» → «+7»
    if len(digits) == 11 and digits.startswith("8"):
        return "+7" + digits[1:]
    if cleaned.startswith("+"):
        return "+" + digits
    if len(digits) == 11 and digits.startswith("7"):
        return "+" + digits
    return digits
