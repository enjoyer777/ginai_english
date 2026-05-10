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


def _xlsx_with_minimal_styles(blob: bytes) -> bytes:
    """Имитируем экспорт из Я.Документов: zip валидный, но styles.xml урезан до
    почти пустого <styleSheet/> — XML валидный, но без cellXfs / fonts / fills,
    что openpyxl терпеть не любит."""
    minimal = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        b'<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'
    )
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zin:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                if name == "xl/styles.xml":
                    zout.writestr(name, minimal)
                else:
                    zout.writestr(name, zin.read(name))
    return out.getvalue()


def _xlsx_without_styles(blob: bytes) -> bytes:
    """Полностью убираем xl/styles.xml — openpyxl на этом тоже спотыкается."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zin:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                if name != "xl/styles.xml":
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


def test_calamine_reads_xlsx_with_minimal_styles(template_blob):
    """Calamine терпимее openpyxl: читает данные даже если styles.xml — пустая болванка."""
    corrupted = _xlsx_with_minimal_styles(template_blob)
    sheets = _read_sheets_with_calamine(corrupted)
    assert len(sheets["Курсы"]) > 0


def test_parse_xlsx_end_to_end_on_minimal_styles(template_blob):
    """parse_xlsx целиком: calamine как primary вытягивает данные несмотря на урезанный styles.xml."""
    corrupted = _xlsx_with_minimal_styles(template_blob)
    snapshot = parse_xlsx(corrupted)

    assert len(snapshot.courses) > 0
    assert len(snapshot.teachers) > 0
    assert snapshot.settings.greeting_text


# --- openpyxl-fallback с санитайзером ---


def test_openpyxl_falls_back_through_sanitizer_on_missing_styles(template_blob):
    """openpyxl-вариант сам подменяет styles.xml на минимально валидный, даже если файла нет."""
    no_styles = _xlsx_without_styles(template_blob)
    sheets = _read_sheets_with_openpyxl(no_styles)
    assert len(sheets["Курсы"]) > 0


def test_sanitize_xlsx_styles_replaces_with_valid_minimal(template_blob):
    no_styles = _xlsx_without_styles(template_blob)
    sanitized = _sanitize_xlsx_styles(no_styles)

    # После санитайза в файле есть styles.xml с непустым содержимым
    with zipfile.ZipFile(io.BytesIO(sanitized), "r") as zf:
        assert "xl/styles.xml" in zf.namelist()
        styles_content = zf.read("xl/styles.xml")
    assert b"styleSheet" in styles_content
    assert b"cellXfs" in styles_content   # минимум структуры есть
    assert len(styles_content) > 100
