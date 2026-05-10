"""Тесты на нормализацию номера телефона при сборе горячего лида.

_normalize_phone — приватный хелпер из engine.py. Принимает что угодно
(пробелы, скобки, тире, +7/8/международный префикс) и приводит к канону.
"""

from app.dialog.engine import _normalize_phone


# --- валидные форматы ---


def test_normalize_e164_russian_plus():
    assert _normalize_phone("+79991234567") == "+79991234567"


def test_normalize_russian_8_to_plus_7():
    """Российский 8XXX → +7XXX (canonical для Битрикса)."""
    assert _normalize_phone("89991234567") == "+79991234567"


def test_normalize_russian_with_spaces_and_dashes():
    assert _normalize_phone("8 (999) 123-45-67") == "+79991234567"
    assert _normalize_phone("+7 999 123 45 67") == "+79991234567"
    assert _normalize_phone("+7-999-123-45-67") == "+79991234567"


def test_normalize_russian_7_without_plus():
    """7XXX без плюса трактуется как +7XXX."""
    assert _normalize_phone("79991234567") == "+79991234567"


def test_normalize_international_us():
    assert _normalize_phone("+12025550100") == "+12025550100"


def test_normalize_international_with_spaces():
    assert _normalize_phone("+44 20 7946 0958") == "+442079460958"


# --- невалидные форматы → None ---


def test_normalize_too_short():
    assert _normalize_phone("12345") is None


def test_normalize_letters_in_number():
    assert _normalize_phone("8-abc-123") is None


def test_normalize_pure_text():
    assert _normalize_phone("позвоните в Telegram") is None


def test_normalize_empty_string():
    assert _normalize_phone("") is None


def test_normalize_only_plus():
    assert _normalize_phone("+") is None


def test_normalize_too_long():
    """E.164 максимум 15 цифр."""
    assert _normalize_phone("+1234567890123456") is None


# --- граничные случаи ---


def test_normalize_strips_unicode_whitespace():
    """Неразрывные пробелы и табы тоже должны вычищаться."""
    assert _normalize_phone("\t+7 999 123 45 67") == "+79991234567"
