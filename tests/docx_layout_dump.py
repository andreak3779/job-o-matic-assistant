"""Describe a DOCX's page and paragraph formatting as plain data, to compare two renderings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml.ns import qn


def _twips(value: Any) -> int | None:
    return None if value is None else round(value.pt * 20)


def dump_layout(path: Path) -> list[Any]:
    document = Document(str(path))
    section = document.sections[0]
    rows: list[Any] = [
        [
            "page",
            round(section.page_width.inches, 2),
            round(section.page_height.inches, 2),
            round(section.top_margin.inches, 3),
            round(section.bottom_margin.inches, 3),
            round(section.left_margin.inches, 3),
            round(section.right_margin.inches, 3),
        ]
    ]
    for paragraph in document.paragraphs:
        fmt = paragraph.paragraph_format
        border = None
        properties = paragraph._p.pPr
        if properties is not None and properties.find(qn("w:pBdr")) is not None:
            bottom = properties.find(qn("w:pBdr")).find(qn("w:bottom"))
            border = [
                bottom.get(qn("w:val")),
                bottom.get(qn("w:sz")),
                bottom.get(qn("w:color")).upper(),
                bottom.get(qn("w:space")),
            ]
        tabs = [[t.alignment.name, round(t.position.pt * 20)] for t in fmt.tab_stops]
        runs = [
            [
                r.font.name,
                r.font.size.pt if r.font.size else None,
                bool(r.bold),
                bool(r.italic),
                str(r.font.color.rgb) if r.font.color and r.font.color.rgb else None,
            ]
            for r in paragraph.runs
        ]
        rows.append(
            [
                paragraph.alignment.name if paragraph.alignment else None,
                _twips(fmt.space_before),
                _twips(fmt.space_after),
                bool(fmt.keep_with_next),
                _twips(fmt.left_indent),
                _twips(fmt.first_line_indent),
                border,
                tabs,
                runs,
            ]
        )
    return rows
