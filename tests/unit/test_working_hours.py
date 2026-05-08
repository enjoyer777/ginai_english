from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.utils.working_hours import default_schedule, is_within, parse_hours_range

MSK = ZoneInfo("Europe/Moscow")


def test_parse_hours_range_basic():
    assert parse_hours_range("09:00-19:00") == (time(9, 0), time(19, 0))


def test_parse_hours_range_empty_means_dayoff():
    assert parse_hours_range("") is None
    assert parse_hours_range(None) is None  # type: ignore[arg-type]


def test_parse_hours_range_invalid():
    assert parse_hours_range("garbage") is None
    assert parse_hours_range("9-19") is None  # без формата HH:MM


def test_is_within_inside_window():
    schedule = default_schedule()
    monday_noon = datetime(2026, 5, 11, 12, 0, tzinfo=MSK)  # понедельник
    assert is_within(monday_noon, schedule) is True


def test_is_within_before_window():
    schedule = default_schedule()
    monday_morning = datetime(2026, 5, 11, 8, 59, tzinfo=MSK)
    assert is_within(monday_morning, schedule) is False


def test_is_within_at_window_start():
    schedule = default_schedule()
    monday_open = datetime(2026, 5, 11, 9, 0, tzinfo=MSK)
    assert is_within(monday_open, schedule) is True


def test_is_within_at_window_end_exclusive():
    """Конец окна 19:00 — НЕ рабочее (FR-8.1: 9-19, не включая 19:00)."""
    schedule = default_schedule()
    monday_close = datetime(2026, 5, 11, 19, 0, tzinfo=MSK)
    assert is_within(monday_close, schedule) is False


def test_is_within_saturday_short_day():
    schedule = default_schedule()
    sat_late = datetime(2026, 5, 16, 14, 30, tzinfo=MSK)
    assert is_within(sat_late, schedule) is True
    sat_too_late = datetime(2026, 5, 16, 16, 0, tzinfo=MSK)
    assert is_within(sat_too_late, schedule) is False


def test_is_within_sunday_off():
    schedule = default_schedule()
    sunday_noon = datetime(2026, 5, 17, 12, 0, tzinfo=MSK)
    assert is_within(sunday_noon, schedule) is False


def test_custom_schedule_overrides_default():
    schedule = {
        "mon": (time(10, 0), time(18, 0)),
        "tue": None,
        "wed": (time(9, 0), time(19, 0)),
        "thu": (time(9, 0), time(19, 0)),
        "fri": (time(9, 0), time(19, 0)),
        "sat": None,
        "sun": None,
    }
    tuesday = datetime(2026, 5, 12, 12, 0, tzinfo=MSK)
    assert is_within(tuesday, schedule) is False
    monday_9 = datetime(2026, 5, 11, 9, 30, tzinfo=MSK)
    assert is_within(monday_9, schedule) is False  # начало в 10:00 по этому расписанию
