from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

import aiosqlite

from app.config import settings
from app.state.db import get_connection
from app.state.models import DealRef, LeadProfile, Message, User
from app.utils.time import now


# ---------- users ----------

async def upsert_user(
    tg_user_id: int,
    tg_username: str | None,
    first_name: str | None,
) -> User:
    ts = now()
    async with get_connection() as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """
            INSERT INTO users (tg_user_id, tg_username, first_name, contact_phone, created_at, updated_at)
            VALUES (?, ?, ?, NULL, ?, ?)
            ON CONFLICT(tg_user_id) DO UPDATE SET
                tg_username = excluded.tg_username,
                first_name  = COALESCE(excluded.first_name, users.first_name),
                updated_at  = excluded.updated_at
            """,
            (tg_user_id, tg_username, first_name, ts, ts),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM users WHERE tg_user_id = ?", (tg_user_id,))
        row = await cur.fetchone()
    assert row is not None
    return _row_to_user(row)


async def set_contact_phone(tg_user_id: int, phone: str) -> None:
    async with get_connection() as db:
        await db.execute(
            "UPDATE users SET contact_phone = ?, updated_at = ? WHERE tg_user_id = ?",
            (phone, now(), tg_user_id),
        )
        await db.commit()


async def set_first_name(tg_user_id: int, first_name: str) -> None:
    """Перезаписывает имя — используется когда клиент явно представился в диалоге.
    Имя из Telegram-профиля при этом затирается (намеренно — клиент сказал, как обращаться)."""
    async with get_connection() as db:
        await db.execute(
            "UPDATE users SET first_name = ?, updated_at = ? WHERE tg_user_id = ?",
            (first_name, now(), tg_user_id),
        )
        await db.commit()


async def get_user(tg_user_id: int) -> User | None:
    async with get_connection() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE tg_user_id = ?", (tg_user_id,))
        row = await cur.fetchone()
    return _row_to_user(row) if row else None


def _row_to_user(row: aiosqlite.Row) -> User:
    return User(
        tg_user_id=row["tg_user_id"],
        tg_username=row["tg_username"],
        first_name=row["first_name"],
        contact_phone=row["contact_phone"],
        created_at=_parse_ts(row["created_at"]),
        updated_at=_parse_ts(row["updated_at"]),
    )


# ---------- lead profile ----------

async def get_lead_profile(tg_user_id: int) -> LeadProfile:
    async with get_connection() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM lead_profiles WHERE tg_user_id = ?", (tg_user_id,)
        )
        row = await cur.fetchone()
    if not row:
        return LeadProfile(tg_user_id=tg_user_id)
    return LeadProfile(
        tg_user_id=row["tg_user_id"],
        goal=row["goal"],
        level_self=row["level_self"],
        horizon=row["horizon"],
        readiness=row["readiness"],
        is_hot=bool(row["is_hot"]),
        last_updated=_parse_ts(row["last_updated"]) if row["last_updated"] else None,
    )


async def update_lead_profile(
    tg_user_id: int,
    goal: str | None = None,
    level_self: str | None = None,
    horizon: str | None = None,
    readiness: str | None = None,
) -> LeadProfile:
    """Мягкое обновление: непустое значение перетирает старое, None оставляет как есть."""
    current = await get_lead_profile(tg_user_id)
    new_goal = goal or current.goal
    new_level = level_self or current.level_self
    new_horizon = horizon or current.horizon
    new_readiness = readiness or current.readiness
    ts = now()
    async with get_connection() as db:
        await db.execute(
            """
            INSERT INTO lead_profiles (tg_user_id, goal, level_self, horizon, readiness, is_hot, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tg_user_id) DO UPDATE SET
                goal         = excluded.goal,
                level_self   = excluded.level_self,
                horizon      = excluded.horizon,
                readiness    = excluded.readiness,
                last_updated = excluded.last_updated
            """,
            (tg_user_id, new_goal, new_level, new_horizon, new_readiness, int(current.is_hot), ts),
        )
        await db.commit()
    return await get_lead_profile(tg_user_id)


async def mark_hot(tg_user_id: int) -> None:
    ts = now()
    async with get_connection() as db:
        await db.execute(
            """
            INSERT INTO lead_profiles (tg_user_id, is_hot, last_updated)
            VALUES (?, 1, ?)
            ON CONFLICT(tg_user_id) DO UPDATE SET is_hot = 1, last_updated = excluded.last_updated
            """,
            (tg_user_id, ts),
        )
        await db.commit()


# ---------- messages ----------

async def append_message(
    tg_user_id: int,
    role: Literal["user", "assistant", "system", "tool"],
    content: str,
) -> None:
    async with get_connection() as db:
        await db.execute(
            "INSERT INTO messages (tg_user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (tg_user_id, role, content, now()),
        )
        await db.commit()


async def get_recent_messages(tg_user_id: int, pairs: int | None = None) -> list[Message]:
    """Последние N сообщений в порядке возрастания времени.

    pairs — сколько ПАР user/assistant; реальный лимит = pairs * 2 + запас на tool-сообщения.
    """
    pairs = pairs if pairs is not None else settings.history_window_pairs
    limit = pairs * 4
    async with get_connection() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT * FROM messages
            WHERE tg_user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (tg_user_id, limit),
        )
        rows = await cur.fetchall()
    rows.reverse()
    return [
        Message(
            id=r["id"],
            tg_user_id=r["tg_user_id"],
            role=r["role"],
            content=r["content"],
            created_at=_parse_ts(r["created_at"]),
        )
        for r in rows
    ]


# ---------- deals ----------

async def find_deal_by_user(tg_user_id: int) -> DealRef | None:
    async with get_connection() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM deals WHERE tg_user_id = ?", (tg_user_id,)
        )
        row = await cur.fetchone()
    if not row:
        return None
    return DealRef(
        bitrix_deal_id=row["bitrix_deal_id"],
        tg_user_id=row["tg_user_id"],
        last_summary=row["last_summary"],
        created_at=_parse_ts(row["created_at"]),
        updated_at=_parse_ts(row["updated_at"]),
    )


async def save_deal_ref(tg_user_id: int, bitrix_deal_id: str, summary: str) -> None:
    ts = now()
    async with get_connection() as db:
        await db.execute(
            """
            INSERT INTO deals (bitrix_deal_id, tg_user_id, last_summary, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tg_user_id) DO UPDATE SET
                bitrix_deal_id = excluded.bitrix_deal_id,
                last_summary   = excluded.last_summary,
                updated_at     = excluded.updated_at
            """,
            (bitrix_deal_id, tg_user_id, summary, ts, ts),
        )
        await db.commit()


# ---------- notify dedup ----------

async def was_notified_recently(tg_user_id: int) -> bool:
    cutoff = now() - timedelta(minutes=settings.notify_dedup_window_minutes)
    async with get_connection() as db:
        cur = await db.execute(
            "SELECT 1 FROM notify_events WHERE tg_user_id = ? AND sent_at >= ? LIMIT 1",
            (tg_user_id, cutoff),
        )
        row = await cur.fetchone()
    return row is not None


async def record_notification(tg_user_id: int) -> None:
    async with get_connection() as db:
        await db.execute(
            "INSERT INTO notify_events (tg_user_id, sent_at) VALUES (?, ?)",
            (tg_user_id, now()),
        )
        await db.commit()


# ---------- helpers ----------

def _parse_ts(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
