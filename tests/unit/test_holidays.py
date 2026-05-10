"""Тесты на лист 'Праздники' и логику date_overrides — что особые даты перекрывают
обычное недельное расписание."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.utils.working_hours import (
    default_schedule,
    effective_window_for,
    is_within,
    is_working_now,
)
from app.kb.yandex_client import _parse_holidays

MSK = ZoneInfo("Europe/Moscow")


# --- effective_window_for ---


def test_effective_window_falls_back_to_weekly_schedule_when_no_overrides():
    schedule = default_schedule()
    monday = date(2026, 5, 11)
    assert effective_window_for(monday, schedule, None) == (time(9, 0), time(19, 0))


def test_effective_window_override_none_makes_working_day_off():
    """9 мая 2026 = суббота, по неделе с 10:00. Овердрайд None = выходной."""
    schedule = default_schedule()
    saturday = date(2026, 5, 9)
    overrides = {saturday: None}
    assert effective_window_for(saturday, schedule, overrides) is None


def test_effective_window_override_custom_hours():
    """Сокращённый предновогодний — 31 декабря."""
    schedule = default_schedule()
    nye = date(2026, 12, 31)  # четверг
    overrides = {nye: (time(9, 0), time(15, 0))}
    assert effective_window_for(nye, schedule, overrides) == (time(9, 0), time(15, 0))


def test_effective_window_override_makes_weekend_working():
    """Странный кейс: воскресенье объявлено рабочим (например, перенос рабочего дня)."""
    schedule = default_schedule()
    sunday = date(2026, 5, 10)
    overrides = {sunday: (time(10, 0), time(15, 0))}
    assert effective_window_for(sunday, schedule, overrides) == (time(10, 0), time(15, 0))


# --- is_within with overrides ---


def test_is_within_respects_holiday_override():
    """9 мая (суббота) в полдень: по обычному расписанию рабочее, по овердрайду — нет."""
    schedule = default_schedule()
    saturday_noon = datetime(2026, 5, 9, 12, 0, tzinfo=MSK)
    overrides = {date(2026, 5, 9): None}
    assert is_within(saturday_noon, schedule) is True  # без оверрайда — рабочее
    assert is_within(saturday_noon, schedule, overrides) is False  # с оверрайдом — нет


def test_is_within_respects_shortened_hours():
    """31 декабря в 15:30 (после конца сокращённого дня) — нерабочее."""
    schedule = default_schedule()
    overrides = {date(2026, 12, 31): (time(9, 0), time(15, 0))}
    nye_late = datetime(2026, 12, 31, 15, 30, tzinfo=MSK)
    assert is_within(nye_late, schedule) is True  # обычное расписание чт 9-19
    assert is_within(nye_late, schedule, overrides) is False  # сокращённое до 15


def test_is_working_now_signature_with_overrides():
    """is_working_now должна принимать опциональные overrides (не падать)."""
    schedule = default_schedule()
    overrides: dict[date, tuple[time, time] | None] = {}
    # Просто проверяем, что вызов не падает с правильным типом
    result = is_working_now(schedule, overrides)
    assert isinstance(result, bool)


# --- _parse_holidays (преобразование строк xlsx в overrides + notes) ---


def test_parse_holidays_full_dayoff():
    rows = [{"date": date(2026, 5, 9), "hours": "", "note": "День Победы"}]
    overrides, notes = _parse_holidays(rows)
    assert overrides == {date(2026, 5, 9): None}
    assert notes == {date(2026, 5, 9): "День Победы"}


def test_parse_holidays_custom_hours():
    rows = [{"date": date(2026, 12, 31), "hours": "09:00-15:00", "note": "Сокращённый"}]
    overrides, notes = _parse_holidays(rows)
    assert overrides == {date(2026, 12, 31): (time(9, 0), time(15, 0))}
    assert notes[date(2026, 12, 31)] == "Сокращённый"


def test_parse_holidays_note_optional():
    rows = [{"date": date(2026, 1, 1), "hours": "", "note": ""}]
    overrides, notes = _parse_holidays(rows)
    assert overrides == {date(2026, 1, 1): None}
    assert notes == {}  # пустую заметку не сохраняем


def test_parse_holidays_skips_rows_without_date():
    rows = [
        {"date": "", "hours": "", "note": "пустая дата"},
        {"date": date(2026, 1, 1), "hours": "", "note": "Новый год"},
        {"date": None, "hours": "10:00-15:00", "note": "тоже пусто"},
    ]
    overrides, notes = _parse_holidays(rows)
    assert len(overrides) == 1
    assert date(2026, 1, 1) in overrides


def test_parse_holidays_string_date_formats():
    """Парсер должен принимать YYYY-MM-DD и DD.MM.YYYY."""
    rows = [
        {"date": "2026-05-09", "hours": "", "note": "ISO"},
        {"date": "31.12.2026", "hours": "09:00-15:00", "note": "Russian"},
    ]
    overrides, notes = _parse_holidays(rows)
    assert overrides == {
        date(2026, 5, 9): None,
        date(2026, 12, 31): (time(9, 0), time(15, 0)),
    }


def test_parse_holidays_empty_input():
    overrides, notes = _parse_holidays([])
    assert overrides == {}
    assert notes == {}
