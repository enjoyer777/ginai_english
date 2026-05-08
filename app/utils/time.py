from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import settings

TZ = ZoneInfo(settings.timezone)


def now() -> datetime:
    return datetime.now(TZ)


def format_msk(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%H:%M %Z, %Y-%m-%d")
