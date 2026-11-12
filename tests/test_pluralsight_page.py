"""The standalone Pluralsight page and the Python reader agree on the import file (ADR 0025).

The page mirrors the format the reader accepts. It used to say so in a comment asking the next
editor to change both places together; these tests are the safeguard instead.
"""

from __future__ import annotations

import re
from pathlib import Path

from jobomatic.learning.adapters import pluralsight_json

PAGE = Path(__file__).resolve().parents[1] / "templates" / "pluralsight_import_template.html"


def _constant(name: str) -> str:
    match = re.search(rf"const {name} = (\"[^\"]*\"|\d+);", PAGE.read_text(encoding="utf-8"))
    assert match, f"the page has no `const {name}`"
    return match.group(1)


def test_the_page_writes_the_format_the_reader_accepts() -> None:
    assert _constant("FORMAT") == f'"{pluralsight_json.FORMAT}"'


def test_the_page_writes_the_version_the_reader_accepts() -> None:
    assert int(_constant("VERSION")) == pluralsight_json.VERSION


def test_the_file_the_page_describes_is_one_the_reader_reads(tmp_path: Path) -> None:
    import json

    entry = {
        "name": "A course",
        "type": "Course",
        "url": "https://app.pluralsight.com/library/courses/a-course",
        "completion_percentage": "100.0%",
        "completed_on": "2026-01-02",
        "completed_date": "Jan 02, 2026",
        "duration": "1h 5m",
        "view_time": "1h 2m",
        "progress": "1h 5m",
        "timing_profile": "Full Course",
    }
    # Written the way the page's importFile() writes it.
    file = tmp_path / "history.json"
    file.write_text(
        json.dumps(
            {
                "format": json.loads(_constant("FORMAT")),
                "version": int(_constant("VERSION")),
                "generated_on": "2026-01-03",
                "entries": [entry],
            }
        ),
        encoding="utf-8",
    )
    batch = pluralsight_json.PluralsightJsonSource(file).read()
    assert [item.title for item in batch.items] == ["A course"]
