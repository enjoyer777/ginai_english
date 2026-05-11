"""Маскирование ПДн перед отправкой в OpenAI (152-ФЗ, трансграничная передача)."""

from app.utils.pii_mask import mask_message, pre_extract_email, pre_extract_phone


# --- pre_extract_phone ---


def test_extract_russian_plus7():
    assert pre_extract_phone("Мой номер +79991234567 запишите") == "+79991234567"


def test_extract_russian_8_normalized_to_plus7():
    assert pre_extract_phone("Звоните на 89991234567") == "+79991234567"


def test_extract_with_spaces_and_dashes():
    assert pre_extract_phone("+7 (999) 123-45-67") == "+79991234567"
    assert pre_extract_phone("8 999 123-45-67") == "+79991234567"


def test_extract_international():
    assert pre_extract_phone("Call me at +12025550100") == "+12025550100"


def test_extract_none_when_no_phone():
    assert pre_extract_phone("Сколько стоит курс?") is None
    assert pre_extract_phone("") is None


def test_extract_returns_first_match():
    assert pre_extract_phone("+79991111111 или +79992222222") == "+79991111111"


def test_extract_phone_does_not_match_random_digits():
    assert pre_extract_phone("Это код 12345") is None
    assert pre_extract_phone("Курс длится 16 недель") is None


# --- pre_extract_email ---


def test_extract_simple_email():
    assert pre_extract_email("Напишите на ivan@example.com") == "ivan@example.com"


def test_extract_email_with_dots_and_plus():
    assert pre_extract_email("test.user+work@mail.org.ru") == "test.user+work@mail.org.ru"


def test_extract_no_email():
    assert pre_extract_email("@username (это телеграм)") is None


# --- mask_message ---


def test_mask_phone_in_text():
    assert mask_message("позвоните +79991234567") == "позвоните <phone>"


def test_mask_multiple_phones():
    result = mask_message("мои номера: +79991234567 и 89992223344")
    assert "<phone>" in result
    assert "+79991234567" not in result
    assert "89992223344" not in result


def test_mask_email():
    assert mask_message("пишите на ivan@mail.ru") == "пишите на <email>"


def test_mask_name_when_saved():
    """Если имя клиента сохранено — маскируем его повторные упоминания в истории."""
    result = mask_message("Меня зовут Иван и я хочу IELTS", saved_name="Иван")
    assert "<имя>" in result
    assert "Иван" not in result


def test_mask_name_case_insensitive():
    result = mask_message("ИВАН пишет, как и иван", saved_name="Иван")
    assert "<имя>" in result
    assert "Иван" not in result and "ИВАН" not in result and "иван" not in result


def test_mask_name_does_not_match_substring():
    """Имя 'Иван' не должно затирать кусок слова типа 'Ивановский'."""
    result = mask_message("это Ивановский курс", saved_name="Иван")
    # «Ивановский» содержит 'Иван' как ПРЕФИКС, но это часть слова — не маскируем
    assert "Ивановский" in result


def test_mask_does_not_touch_neutral_text():
    text = "Сколько стоит курс IELTS?"
    assert mask_message(text) == text


def test_mask_empty_string():
    assert mask_message("") == ""


def test_mask_short_saved_name_ignored():
    """Однобуквенные имена не маскируем — иначе зацепим всё подряд."""
    result = mask_message("Я А и тебя зовут А", saved_name="А")
    assert result == "Я А и тебя зовут А"


def test_mask_combined_phone_email_name():
    text = "Меня зовут Иван, телефон +79991234567, email ivan@mail.ru"
    result = mask_message(text, saved_name="Иван")
    assert "<phone>" in result
    assert "<email>" in result
    assert "<имя>" in result
    assert "+79991234567" not in result
    assert "ivan@mail.ru" not in result
    assert "Иван" not in result
