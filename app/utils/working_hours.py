from __future__ import annotations

from datetime import date, datetime, time

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


def effective_window_for(
    target: date,
    schedule: dict[str, tuple[time, time] | None],
    date_overrides: dict[date, tuple[time, time] | None] | None = None,
) -> tuple[time, time] | None:
    """Вернуть рабочее окно на конкретную дату с учётом исключений (праздников).

    Приоритет: date_overrides → недельное расписание.
    None в овердрайде = принудительно выходной (даже если по неделе должен работать).
    Кортеж в овердрайде = особый график для этой даты (например, сокращённый предпраздничный).
    """
    if date_overrides and target in date_overrides:
        return date_overrides[target]
    return schedule.get(WEEKDAY_KEYS[target.weekday()])


def is_within(
    moment: datetime,
    schedule: dict[str, tuple[time, time] | None],
    date_overrides: dict[date, tuple[time, time] | None] | None = None,
) -> bool:
    """Проверяет, попадает ли moment в рабочее окно с учётом овердрайдов по датам."""
    window = effective_window_for(moment.date(), schedule, date_overrides)
    if window is None:
        return False
    start, end = window
    current = moment.time()
    return start <= current < end


def is_working_now(
    schedule: dict[str, tuple[time, time] | None],
    date_overrides: dict[date, tuple[time, time] | None] | None = None,
) -> bool:
    return is_within(now(), schedule, date_overrides)


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
