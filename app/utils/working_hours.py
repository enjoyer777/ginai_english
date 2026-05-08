from __future__ import annotations

from datetime import datetime, time

from app.utils.time import now

WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def parse_hours_range(value: str) -> tuple[time, time] | None:
    """Парсит '09:00-19:00' → (09:00, 19:00). Пустая строка / None → None (выходной)."""
    if not value or not value.strip():
        return None
    try:
        start_s, end_s = [p.strip() for p in value.split("-", 1)]
        start = time.fromisoformat(start_s)
        end = time.fromisoformat(end_s)
        return (start, end)
    except (ValueError, AttributeError):
        return None


def is_within(
    moment: datetime,
    schedule: dict[str, tuple[time, time] | None],
) -> bool:
    """Проверяет, попадает ли moment в рабочее окно по расписанию.

    schedule: {"mon": (09:00, 19:00), "sat": (10:00, 15:00), "sun": None, ...}
    """
    key = WEEKDAY_KEYS[moment.weekday()]
    window = schedule.get(key)
    if window is None:
        return False
    start, end = window
    current = moment.time()
    return start <= current < end


def is_working_now(schedule: dict[str, tuple[time, time] | None]) -> bool:
    return is_within(now(), schedule)


def default_schedule() -> dict[str, tuple[time, time] | None]:
    """Дефолт по FR-8.1 на случай, если KB ещё не загрузилась."""
    return {
        "mon": (time(9, 0), time(19, 0)),
        "tue": (time(9, 0), time(19, 0)),
        "wed": (time(9, 0), time(19, 0)),
        "thu": (time(9, 0), time(19, 0)),
        "fri": (time(9, 0), time(19, 0)),
        "sat": (time(10, 0), time(15, 0)),
        "sun": None,
    }
