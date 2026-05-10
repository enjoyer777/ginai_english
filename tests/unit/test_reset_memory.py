"""CLI сброса памяти бота (app.scripts.reset_memory). Тестим на in-memory SQLite,
не трогая боевую БД."""

from datetime import datetime, timezone

import aiosqlite
import pytest

from app.config import settings
from app.scripts.reset_memory import list_users, wipe_all, wipe_user
from app.state import db
from app.state import repository as repo


@pytest.fixture(autouse=True)
async def isolated_db(tmp_path, monkeypatch):
    """Каждый тест получает свежую базу во временной папке.

    Все модули используют один и тот же синглтон settings, так что патчим его in-place.
    """
    test_db = tmp_path / "state.db"
    monkeypatch.setattr(settings, "sqlite_path", test_db)
    await db.init_db()
    yield test_db


async def _seed_user(tg_id: int, with_profile: bool = True, with_messages: int = 0):
    await repo.upsert_user(tg_id, f"u{tg_id}", f"User{tg_id}")
    if with_profile:
        await repo.update_lead_profile(tg_id, goal="IELTS")
        await repo.mark_hot(tg_id)
    for i in range(with_messages):
        await repo.append_message(tg_id, "user", f"msg {i}")
    if with_profile:
        # Имитируем созданную сделку
        await repo.save_deal_ref(tg_id, f"deal-{tg_id}", "summary")
        await repo.record_notification(tg_id)


async def _count_rows(tg_id: int) -> dict[str, int]:
    """Помогает асситить, что у юзера в БД ничего не осталось."""
    counts = {}
    async with aiosqlite.connect(settings.sqlite_path) as conn:
        for tbl in ("users", "lead_profiles", "messages", "deals", "notify_events"):
            cur = await conn.execute(
                f"SELECT COUNT(*) FROM {tbl} WHERE tg_user_id = ?", (tg_id,)
            )
            row = await cur.fetchone()
            counts[tbl] = row[0] if row else 0
    return counts


async def test_wipe_user_removes_all_per_user_rows():
    await _seed_user(111, with_messages=5)
    assert (await _count_rows(111))["messages"] == 5

    await wipe_user(111, dry_run=False)

    counts = await _count_rows(111)
    assert counts == {
        "users": 0,
        "lead_profiles": 0,
        "messages": 0,
        "deals": 0,
        "notify_events": 0,
    }


async def test_wipe_user_dry_run_does_not_delete():
    await _seed_user(222, with_messages=3)
    await wipe_user(222, dry_run=True)

    counts = await _count_rows(222)
    assert counts["users"] == 1
    assert counts["messages"] == 3
    assert counts["lead_profiles"] == 1


async def test_wipe_user_does_not_touch_other_users():
    await _seed_user(333, with_messages=4)
    await _seed_user(444, with_messages=2)

    await wipe_user(333, dry_run=False)

    assert (await _count_rows(333))["users"] == 0
    assert (await _count_rows(444))["users"] == 1
    assert (await _count_rows(444))["messages"] == 2


async def test_wipe_nonexistent_user_is_safe():
    await _seed_user(555)
    await wipe_user(99999, dry_run=False)  # не существует
    # Существующего юзера не задеваем
    assert (await _count_rows(555))["users"] == 1


async def test_wipe_all_clears_everything():
    await _seed_user(111, with_messages=3)
    await _seed_user(222, with_messages=5)

    await wipe_all(dry_run=False)

    for tg in (111, 222):
        counts = await _count_rows(tg)
        assert all(v == 0 for v in counts.values())


async def test_wipe_all_dry_run_keeps_data():
    await _seed_user(111, with_messages=3)
    await wipe_all(dry_run=True)
    assert (await _count_rows(111))["messages"] == 3


async def test_list_users_handles_empty_db(capsys):
    """list_users на пустой БД не падает."""
    await list_users()
    out = capsys.readouterr().out
    assert "нет ни одного" in out.lower() or "no users" in out.lower()


async def test_list_users_shows_seeded_data(capsys):
    await _seed_user(777, with_messages=2)
    await list_users()
    out = capsys.readouterr().out
    assert "777" in out
    assert "User777" in out or "u777" in out
