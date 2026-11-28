"""Generated documents name the candidate in their file properties, and every part of the text is
checked for stock AI phrasing."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from docx import Document

import jobomatic
from jobomatic.documents import service
from jobomatic.documents.adapters.docx_part_time import (
    DocxPartTimeCoverLetter,
    DocxPartTimeResume,
)
from jobomatic.documents.adapters.docx_tailored import (
    DocxTailoredCoverLetter,
    DocxTailoredResume,
)

FIXTURES = Path(__file__).parent / "fixtures" / "documents"
RENDERERS = {
    "resume": (DocxTailoredResume, "Resume"),
    "cover-letter": (DocxTailoredCoverLetter, "Cover Letter"),
    "part-time-resume": (DocxPartTimeResume, "Resume"),
    "part-time-cover-letter": (DocxPartTimeCoverLetter, "Cover Letter"),
}


def _data(kind: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{kind}.json").read_text(encoding="utf-8"))


def _render(kind: str, data: dict[str, Any], out: Path) -> Path:
    content = service.parse_content(kind, json.dumps(data))
    return service.render_document(content, RENDERERS[kind][0](), out)


@pytest.mark.parametrize("kind", sorted(RENDERERS))
def test_file_properties_name_the_candidate_and_today(kind: str, tmp_path: Path) -> None:
    before = datetime.now(UTC) - timedelta(seconds=2)
    data = _data(kind)
    properties = Document(str(_render(kind, data, tmp_path / "out.docx"))).core_properties

    name = data["contact"]["name"]
    assert properties.author == name
    assert properties.last_modified_by == name
    assert properties.title == f"{name} - {RENDERERS[kind][1]}"
    assert properties.comments == ""
    assert properties.revision == 1
    assert properties.created == properties.modified
    assert before <= properties.created.replace(tzinfo=UTC) <= datetime.now(UTC)


def test_no_generator_starts_from_the_bare_python_docx_template() -> None:
    """``Document()`` carries python-docx's own author and date; ``new_document`` replaces them."""
    source = Path(jobomatic.__file__).parent
    bare = [
        path.relative_to(source).as_posix()
        for path in source.rglob("*.py")
        if re.search(r"^[^#\n`]*\bDocument\(\)", path.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert bare == ["documents/adapters/docx_layout.py"]


def _skill_line(data: dict[str, Any], text: str) -> None:
    data["skills"][0]["skills"] = text


def _bring_body(data: dict[str, Any], text: str) -> None:
    data["bring"][0]["body"] = text


def _highlight_body(data: dict[str, Any], text: str) -> None:
    data["highlights"] = [{"label": "Work", "body": text}]


def _strength_label(data: dict[str, Any], text: str) -> None:
    data["strengths"][0]["label"] = text


@pytest.mark.parametrize(
    ("kind", "put"),
    [
        ("resume", _skill_line),
        ("cover-letter", _bring_body),
        ("cover-letter", _highlight_body),
        ("part-time-resume", _strength_label),
        ("part-time-cover-letter", _strength_label),
    ],
)
def test_stock_phrasing_is_reported_wherever_it_is(
    kind: str, put: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _data(kind)
    put(data, "Spearheaded a rewrite")
    _render(kind, data, tmp_path / "out.docx")
    assert "spearheaded" in capsys.readouterr().err
