from __future__ import annotations

import aiosqlite
from loguru import logger

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    tg_user_id INTEGER PRIMARY KEY,
    tg_username TEXT,
    first_name TEXT,
    contact_phone TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS lead_profiles (
    tg_user_id INTEGER PRIMARY KEY,
    goal TEXT,
    level_self TEXT,
    horizon TEXT,
    readiness TEXT,
    is_hot INTEGER NOT NULL DEFAULT 0,
    last_updated TIMESTAMP,
    FOREIGN KEY (tg_user_id) REFERENCES users(tg_user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (tg_user_id) REFERENCES users(tg_user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_user_time
    ON messages(tg_user_id, created_at);

CREATE TABLE IF NOT EXISTS deals (
    bitrix_deal_id TEXT PRIMARY KEY,
    tg_user_id INTEGER NOT NULL UNIQUE,
    last_summary TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (tg_user_id) REFERENCES users(tg_user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notify_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_user_id INTEGER NOT NULL,
    sent_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notify_user_time
    ON notify_events(tg_user_id, sent_at);
"""


async def init_db() -> None:
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    logger.info("SQLite initialized at {}", settings.sqlite_path)


def get_connection() -> aiosqlite.Connection:
    """Использовать через `async with get_connection() as db`."""
    return aiosqlite.connect(settings.sqlite_path)
