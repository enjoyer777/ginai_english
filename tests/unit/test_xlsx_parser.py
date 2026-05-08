"""Парсер xlsx — на реальном demo-файле, который создаёт scripts/build_kb_template.py."""

from pathlib import Path

import pytest

from app.kb.yandex_client import parse_xlsx


@pytest.fixture(scope="module")
def snapshot():
    template_path = Path(__file__).resolve().parents[2] / "docs" / "kb_template.xlsx"
    if not template_path.exists():
        pytest.skip(f"kb_template.xlsx not built; run scripts/build_kb_template.py first")
    return parse_xlsx(template_path.read_bytes())


def test_courses_loaded(snapshot):
    assert len(snapshot.courses) == 6
    names = {c.name for c in snapshot.courses}
    assert "English for IT" in names
    assert "IELTS Preparation" in names


def test_courses_have_valid_directions(snapshot):
    for c in snapshot.courses:
        assert c.direction in {"работа", "переезд", "путешествия", "для себя"}


def test_courses_have_valid_levels(snapshot):
    valid = {"A0-A1", "A2", "B1", "B2"}
    for c in snapshot.courses:
        assert c.levels, f"course {c.name} has no levels"
        for lv in c.levels:
            assert lv in valid


def test_installment_parsed_as_bool(snapshot):
    by_id = {c.id: c for c in snapshot.courses}
    assert by_id["1"].installment is True
    assert by_id["4"].installment is False


def test_schedule_loaded(snapshot):
    assert len(snapshot.schedules) == 8
    s0 = snapshot.schedules[0]
    assert s0.course_id == "1"
    assert s0.seats_left == 4


def test_teachers_loaded(snapshot):
    assert len(snapshot.teachers) == 3


def test_faq_loaded(snapshot):
    assert len(snapshot.faq) == 6


def test_settings_working_hours(snapshot):
    wh = snapshot.settings.working_hours
    assert wh["mon"] is not None
    assert wh["sat"] is not None
    assert wh["sun"] is None
    start, end = wh["mon"]
    assert start.hour == 9
    assert end.hour == 19


def test_settings_greeting_and_disclaimer(snapshot):
    assert "school_english_pro" in snapshot.settings.greeting_text
    assert snapshot.settings.pii_disclaimer
