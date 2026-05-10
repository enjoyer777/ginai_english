"""Тесты на _compose_calendar_block — это блок, который инжектится в системный
промпт при каждом запросе к LLM, чтобы модель не вычисляла даты сама."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.dialog.engine import _compose_calendar_block

MSK = ZoneInfo("Europe/Moscow")


def _full_schedule() -> dict[str, tuple[time, time] | None]:
    return {
        "mon": (time(9, 0), time(19, 0)),
        "tue": (time(9, 0), time(19, 0)),
        "wed": (time(9, 0), time(19, 0)),
        "thu": (time(9, 0), time(19, 0)),
        "fri": (time(9, 0), time(19, 0)),
        "sat": (time(10, 0), time(15, 0)),
        "sun": None,
    }


def test_today_line_contains_correct_weekday_and_date():
    """Воскресенье 10 мая — выходной по обычному графику."""
    moment = datetime(2026, 5, 10, 8, 30, tzinfo=MSK)  # вс
    block = _compose_calendar_block(_full_schedule(), {}, {}, moment)

    assert "2026-05-10" in block
    assert "воскресенье" in block.lower()
    assert "выходной" in block.lower()
    assert "Сегодня:" in block


def test_tomorrow_line_picks_correct_next_day():
    moment = datetime(2026, 5, 10, 8, 30, tzinfo=MSK)  # вс → завтра пн 11 мая
    block = _compose_calendar_block(_full_schedule(), {}, {}, moment)

    assert "2026-05-11" in block
    assert "понедельник" in block.lower()
    assert "Завтра:" in block


def test_now_working_marker_during_business_hours():
    moment = datetime(2026, 5, 11, 14, 0, tzinfo=MSK)  # пн 14:00 — рабочее
    block = _compose_calendar_block(_full_schedule(), {}, {}, moment)

    assert "СЕЙЧАС рабочее время" in block


def test_after_hours_marker_in_evening():
    moment = datetime(2026, 5, 11, 20, 0, tzinfo=MSK)  # пн 20:00 — после работы
    block = _compose_calendar_block(_full_schedule(), {}, {}, moment)

    assert "уже поздно" in block.lower() or "вне часов" in block.lower()


def test_before_hours_marker_early_morning():
    moment = datetime(2026, 5, 11, 7, 30, tzinfo=MSK)  # пн 7:30 — до открытия
    block = _compose_calendar_block(_full_schedule(), {}, {}, moment)

    assert "ещё рано" in block.lower()


def test_next_working_window_skips_sundays_and_holidays():
    """Воскресенье 10 мая. Следующее рабочее окно = понедельник 11 мая 9:00."""
    moment = datetime(2026, 5, 10, 8, 30, tzinfo=MSK)
    block = _compose_calendar_block(_full_schedule(), {}, {}, moment)

    assert "Ближайшее рабочее окно" in block
    assert "понедельник" in block.lower()
    assert "2026-05-11" in block
    assert "09:00–19:00" in block


def test_holiday_override_marks_date_as_dayoff():
    """9 мая (суббота) объявлен нерабочим — должно отразиться в строке завтра."""
    moment = datetime(2026, 5, 8, 12, 0, tzinfo=MSK)  # пятница
    overrides = {date(2026, 5, 9): None}
    notes = {date(2026, 5, 9): "День Победы"}

    block = _compose_calendar_block(_full_schedule(), overrides, notes, moment)

    # Завтра суббота 9 мая
    assert "2026-05-09" in block
    assert "выходной" in block.lower()
    assert "День Победы" in block


def test_holiday_override_in_next_window_calculation():
    """Сб 9 мая выходной → ближайшее окно после неё = понедельник 11."""
    moment = datetime(2026, 5, 8, 20, 0, tzinfo=MSK)  # пятница после 19:00 = off
    overrides = {date(2026, 5, 9): None}
    notes = {date(2026, 5, 9): "День Победы"}

    block = _compose_calendar_block(_full_schedule(), overrides, notes, moment)

    # next_working_window должен пропустить субботу-праздник и указать понедельник
    assert "Ближайшее рабочее окно" in block
    # Ищем строку «понедельник, 2026-05-11» в next-line
    lines = block.splitlines()
    nxt_line = next(line for line in lines if line.startswith("Ближайшее рабочее окно"))
    assert "2026-05-11" in nxt_line


def test_upcoming_overrides_listed_in_block():
    """Праздники в ближайшие 30 дней должны быть видны в блоке."""
    moment = datetime(2026, 5, 1, 12, 0, tzinfo=MSK)
    overrides = {
        date(2026, 5, 9): None,
        date(2026, 5, 11): None,
    }
    notes = {
        date(2026, 5, 9): "День Победы",
        date(2026, 5, 11): "Перенос",
    }

    block = _compose_calendar_block(_full_schedule(), overrides, notes, moment)

    assert "2026-05-09" in block
    assert "2026-05-11" in block
    assert "День Победы" in block
    assert "Перенос" in block


def test_block_does_not_pollute_with_far_future_overrides():
    """Праздники более чем через 30 дней не должны загромождать блок."""
    moment = datetime(2026, 5, 1, 12, 0, tzinfo=MSK)
    overrides = {date(2026, 12, 31): (time(9, 0), time(15, 0))}
    notes = {date(2026, 12, 31): "Сокращённый предновогодний"}

    block = _compose_calendar_block(_full_schedule(), overrides, notes, moment)

    assert "Сокращённый предновогодний" not in block
    # Но базовый блок «нет особых дат на месяц» должен быть
    assert "Особые даты" in block


def test_weekly_schedule_section_has_all_seven_days():
    moment = datetime(2026, 5, 11, 12, 0, tzinfo=MSK)
    block = _compose_calendar_block(_full_schedule(), {}, {}, moment)

    for day in ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]:
        assert day in block, f"missing weekday: {day}"
