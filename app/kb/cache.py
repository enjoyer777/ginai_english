"""TTL-кэш базы знаний (FR-4.3, FR-4.6).

Логика:
  - При первом запросе грузим xlsx с Я.Диска, парсим, кладём в _state.
  - При следующих запросах — отдаём из памяти, если не истёк TTL.
  - При истечении TTL — пробуем обновить. Если Yandex API упал — возвращаем
    последний валидный кэш и пишем warning. Падать на сетевой ошибке нельзя.
  - Если кэша ещё нет (холодный старт + сбой) — отдаём None, вызывающий код
    решает, что делать (обычно: предложить связаться с менеджером).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from loguru import logger

from app.config import settings
from app.kb.schema import KBSnapshot
from app.kb.yandex_client import YandexDiskError, load_kb_snapshot
from app.utils.time import now


@dataclass
class _State:
    snapshot: KBSnapshot | None = None
    fetched_at: datetime | None = None
    last_error: str | None = None


_state = _State()
_lock = asyncio.Lock()


def _is_fresh() -> bool:
    if _state.snapshot is None or _state.fetched_at is None:
        return False
    ttl = timedelta(seconds=settings.kb_cache_ttl_seconds)
    return now() - _state.fetched_at < ttl


async def get_snapshot() -> KBSnapshot | None:
    if _is_fresh():
        return _state.snapshot

    async with _lock:
        if _is_fresh():
            return _state.snapshot
        try:
            snap = await load_kb_snapshot()
            _state.snapshot = snap
            _state.fetched_at = now()
            _state.last_error = None
            logger.info("KB cache refreshed")
            return snap
        except YandexDiskError as e:
            _state.last_error = str(e)
            logger.warning("KB refresh failed, using stale cache. Error: {}", e)
            return _state.snapshot
        except Exception as e:
            _state.last_error = repr(e)
            logger.exception("Unexpected KB refresh error")
            return _state.snapshot


async def force_refresh() -> KBSnapshot | None:
    async with _lock:
        try:
            snap = await load_kb_snapshot()
            _state.snapshot = snap
            _state.fetched_at = now()
            _state.last_error = None
            return snap
        except Exception as e:
            _state.last_error = repr(e)
            logger.exception("Forced KB refresh failed")
            return _state.snapshot
