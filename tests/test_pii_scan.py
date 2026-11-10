"""jobomatic.privacy.scan: personal identifiers restated in tracked files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobomatic.privacy.scan import find_pii, load_terms

# Fictional values only: this file is tracked.
TERMS = {
    "names": ["Jordan Example"],
    "emails": ["jordan@example.com"],
    "phones": ["204-555-0100"],
    "employers": ["Acme Widgets"],
    "identifiers": ["share0123abc"],
}


def test_finds_each_category_and_reports_path_line_but_never_the_value() -> None:
    files = {
        "a.md": "ok\nBy Jordan Example\n",
        "b.md": "mail jordan@example.com",
        "c.md": "call (204) 555-0100",
        "d.md": "worked at Acme Widgets",
        "e.md": "link ?id=share0123abc",
    }
    findings = find_pii(TERMS, files)
    assert findings == [
        "a.md:2 (names)",
        "b.md:1 (emails)",
        "c.md:1 (phones)",
        "d.md:1 (employers)",
        "e.md:1 (identifiers)",
    ]
    assert all("Jordan" not in f and "555" not in f for f in findings)


def test_names_and_emails_ignore_case_but_employers_do_not() -> None:
    files = {"a.md": "JORDAN EXAMPLE and JORDAN@EXAMPLE.COM", "b.md": "acme widgets"}
    assert find_pii(TERMS, files) == ["a.md:1 (names)", "a.md:1 (emails)"]


def test_matches_whole_words_only() -> None:
    assert find_pii(TERMS, {"a.md": "Acme WidgetsPlus and xAcme Widgets"}) == []


def test_a_term_after_a_written_out_newline_is_still_found() -> None:
    # In a string literal such as "# Company\\nAcme Widgets" the character before the name is
    # the letter n of the escape, which must not hide the name.
    files = {"a.py": '# "# Company\\nAcme Widgets\\n\\n# Position"'}
    assert find_pii(TERMS, files) == ["a.py:1 (employers)"]
    assert find_pii(TERMS, {"b.py": "Mining Widgets"}) == []


def test_phone_matches_any_separator_style() -> None:
    for text in ("204-555-0100", "(204) 555-0100", "204.555.0100", "2045550100"):
        assert find_pii(TERMS, {"a.md": text}) == ["a.md:1 (phones)"], text


def test_allowlisted_paths_are_skipped() -> None:
    files = {"old.md": "Jordan Example", "new.md": "Jordan Example"}
    assert find_pii(TERMS, files, allow={"old.md"}) == ["new.md:1 (names)"]


def test_load_terms_validates_shape(tmp_path: Path) -> None:
    good = tmp_path / "good.json"
    good.write_text(json.dumps(TERMS), encoding="utf-8")
    assert load_terms(good) == TERMS
    for bad in ({"colours": ["red"]}, {"names": "Jordan"}, {"names": [""]}, ["names"]):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError):
            load_terms(path)
