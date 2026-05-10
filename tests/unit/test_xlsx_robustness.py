"""Парсер должен переваривать xlsx-файлы, экспортированные онлайн-редакторами
(Я.Документы, Google Sheets), которые иногда отдают файл с битым/отсутствующим
xl/styles.xml. Calamine это переваривает; openpyxl — нет.
"""

import io
import zipfile
from pathlib import Path

import pytest

from app.kb.yandex_client import (
    _read_sheets_with_calamine,
    _read_sheets_with_openpyxl,
    _sanitize_xlsx_styles,
    parse_xlsx,
)


@pytest.fixture(scope="module")
def template_blob() -> bytes:
    template_path = Path(__file__).resolve().parents[2] / "docs" / "kb_template.xlsx"
    if not template_path.exists():
        pytest.skip("kb_template.xlsx not built; run scripts/build_kb_template.py first")
    return template_path.read_bytes()


def _corrupt_styles_xml(blob: bytes) -> bytes:
    """Имитируем экспорт из Я.Документов: оставляем zip валидным,
    но xl/styles.xml делаем пустым."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zin:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                if name == "xl/styles.xml":
                    zout.writestr(name, b"")  # пустой — то, что валит openpyxl
                else:
                    zout.writestr(name, zin.read(name))
    return out.getvalue()


# --- calamine как primary ---


def test_calamine_reads_normal_xlsx(template_blob):
    sheets = _read_sheets_with_calamine(template_blob)
    assert "Курсы" in sheets
    assert "Расписание" in sheets
    assert "Преподаватели" in sheets
    assert "FAQ" in sheets
    assert "Настройки" in sheets


def test_calamine_reads_xlsx_with_empty_styles_xml(template_blob):
    """Самый важный кейс: calamine не падает, даже если styles.xml пустой."""
    corrupted = _corrupt_styles_xml(template_blob)
    sheets = _read_sheets_with_calamine(corrupted)
    assert len(sheets["Курсы"]) > 0


def test_parse_xlsx_end_to_end_on_corrupted_file(template_blob):
    """parse_xlsx целиком: calamine как primary вытягивает данные несмотря на битый styles.xml."""
    corrupted = _corrupt_styles_xml(template_blob)
    snapshot = parse_xlsx(corrupted)

    assert len(snapshot.courses) > 0
    assert len(snapshot.teachers) > 0
    assert snapshot.settings.greeting_text


# --- openpyxl-fallback с санитайзером ---


def test_openpyxl_falls_back_through_sanitizer(template_blob):
    """openpyxl-вариант сам подменяет styles.xml на минимально валидный."""
    corrupted = _corrupt_styles_xml(template_blob)
    sheets = _read_sheets_with_openpyxl(corrupted)
    assert len(sheets["Курсы"]) > 0


def test_sanitize_xlsx_styles_replaces_broken_styles(template_blob):
    corrupted = _corrupt_styles_xml(template_blob)
    sanitized = _sanitize_xlsx_styles(corrupted)

    # После санитайза в файле есть styles.xml с непустым содержимым
    with zipfile.ZipFile(io.BytesIO(sanitized), "r") as zf:
        styles_content = zf.read("xl/styles.xml")
    assert b"styleSheet" in styles_content
    assert len(styles_content) > 100


def test_sanitize_xlsx_styles_creates_styles_if_missing(template_blob):
    """Если в zip вообще нет xl/styles.xml — санитайзер его создаст."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template_blob), "r") as zin:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                if name != "xl/styles.xml":
                    zout.writestr(name, zin.read(name))

    sanitized = _sanitize_xlsx_styles(out.getvalue())
    with zipfile.ZipFile(io.BytesIO(sanitized), "r") as zf:
        assert "xl/styles.xml" in zf.namelist()
        assert b"styleSheet" in zf.read("xl/styles.xml")
