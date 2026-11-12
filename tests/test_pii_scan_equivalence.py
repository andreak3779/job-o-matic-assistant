"""The fast private-value pattern matches the same lines as the older, slower one (ADR 0032).

``scan._compile`` writes the boundary tests once around all the literal terms. The older form, one
lookbehind and lookahead per term, is kept here as the reference, because the scan is a security
control: a line that the old form flagged and the new one does not would be a leak that gets
through. Fictional values only; this file is tracked.
"""

from __future__ import annotations

import random
import re
from collections.abc import Iterable

import pytest

from jobomatic.privacy import scan


def _reference(category: str, values: Iterable[str]) -> re.Pattern[str] | None:
    """The pattern as it was before ADR 0032."""
    parts = []
    for value in sorted({v.strip() for v in values if len(v.strip()) >= 3}, key=len, reverse=True):
        escaped = re.escape(value)
        if category == "phones":
            digits = re.sub(r"\D", "", value)
            if len(digits) == 10:
                parts.append(rf"\(?{digits[:3]}\)?[-. ]?{digits[3:6]}[-. ]?{digits[6:]}")
                continue
        parts.append(rf"(?:(?<![\w])|(?<=\\n)|(?<=\\t)|(?<=\\r)){escaped}(?![\w])")
    if not parts:
        return None
    flags = re.IGNORECASE if category in scan._CASE_INSENSITIVE else 0
    return re.compile("|".join(parts), flags)


TERMS = {
    "names": ["Jordan Example", "Jo Ex", "Sam"],
    "emails": ["jordan@example.com", "j.example@example.org"],
    # 10 digits (any separator style), 7 digits and 11 digits: only the first has no boundary test.
    "phones": ["204-555-0100", "555-0199", "1-800-555-0123"],
    "employers": ["Acme Widgets", "Acme", "R&D (North)", "a+b", "C#", "Widget Co."],
    "identifiers": ["share0123abc", "abc", "x_y"],
}

LINES = [
    "",
    "Jordan Example",
    "JORDAN EXAMPLE worked here",
    "by Jordan Examples",  # inside a longer word: no match
    "xJordan Example",
    "Jordan Example,",
    r"text\nJordan Example",  # after a written-out newline: match
    r"text\tAcme",
    r"text\rAcme",
    r"text\\nAcme",
    "Acme",
    "acme",  # employers are case-sensitive
    "Acmé",
    "Acme Widgets and Acme",
    "AcmeWidgets",
    "R&D (North) team",
    "the a+b rule",
    "C# and C#!",
    "C#sharp",
    "Widget Co.",
    "Widget Co.x",
    "(204) 555-0100",
    "204.555.0100",
    "2045550100",
    "12045550100",  # the 10-digit shape has no boundary test, as before
    "call 555-0199 now",
    "x555-0199",  # a 7-digit phone term does have one
    "555-01990",
    "1-800-555-0123",
    "mail Jordan@Example.com please",
    "mailjordan@example.com",
    "j.example@example.org.",
    "id=share0123abc&x",
    "share0123abcd",
    "abc",
    "ABC",
    "x_y",
    "x_yz",
    "_x_y",
    "Sam is here",
    "Samuel",
    "Sam.",
    "ünïcode Sam ünï",
]


@pytest.mark.parametrize("category", sorted(TERMS))
def test_each_line_in_the_table_is_flagged_alike(category: str) -> None:
    new = scan._compile(category, TERMS[category])
    old = _reference(category, TERMS[category])
    assert new is not None and old is not None
    for line in LINES:
        assert bool(new.search(line)) == bool(old.search(line)), (category, line)


@pytest.mark.parametrize("category", sorted(TERMS))
def test_random_lines_are_flagged_alike(category: str) -> None:
    new = scan._compile(category, TERMS[category])
    old = _reference(category, TERMS[category])
    assert new is not None and old is not None
    pieces = [*(t for ts in TERMS.values() for t in ts), "x", "_", " ", "-", ".", r"\n", r"\t", "é"]
    pieces += [t.upper() for t in pieces] + [t.lower() for t in pieces]
    rng = random.Random(32)  # the number of the ADR; any seed must pass
    flagged = 0
    for _ in range(4000):
        line = "".join(rng.choice(pieces) for _ in range(rng.randint(1, 6)))
        expected = bool(old.search(line))
        flagged += expected
        assert bool(new.search(line)) == expected, (category, line)
    assert flagged > 100, "the fuzz must flag enough lines to mean something"


def test_the_table_flags_some_lines_and_leaves_others() -> None:
    new = scan._compile("employers", TERMS["employers"])
    assert new is not None
    hits = [bool(new.search(line)) for line in LINES]
    assert any(hits) and not all(hits)


def test_find_pii_reports_the_same_findings_as_the_reference() -> None:
    files = {"a.md": "\n".join(LINES), "b.md": r"x\nSam and 204-555-0100"}
    expected = []
    for path, text in files.items():
        for number, line in enumerate(text.splitlines(), start=1):
            for category, values in TERMS.items():
                pattern = _reference(category, values)
                if pattern is not None and pattern.search(line):
                    expected.append(f"{path}:{number} ({category})")
    assert scan.find_pii(TERMS, files) == expected
