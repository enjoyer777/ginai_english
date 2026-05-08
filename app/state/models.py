from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(slots=True)
class User:
    tg_user_id: int
    tg_username: str | None
    first_name: str | None
    contact_phone: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class LeadProfile:
    """Слоты квалификации (FR-5.1). Все поля опциональны — заполняются по ходу диалога."""

    tg_user_id: int
    goal: str | None = None             # "IELTS", "переезд", "работа", "путешествия", "для себя"
    level_self: str | None = None       # "с нуля", "A2", "школьный", "Гарри Поттер"
    horizon: str | None = None          # "в этом месяце", "к лету", "пока изучаю"
    readiness: str | None = None        # "изучает", "готов записаться"
    is_hot: bool = False
    last_updated: datetime | None = None


@dataclass(slots=True)
class Message:
    id: int | None
    tg_user_id: int
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    created_at: datetime


@dataclass(slots=True)
class DealRef:
    """Ссылка на сделку Bitrix24 для дедупликации (FR-6.2)."""

    bitrix_deal_id: str
    tg_user_id: int
    last_summary: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class NotifyEvent:
    """Запись об отправленном уведомлении в чат менеджеров (для дедупа FR-9.4)."""

    id: int | None
    tg_user_id: int
    sent_at: datetime
