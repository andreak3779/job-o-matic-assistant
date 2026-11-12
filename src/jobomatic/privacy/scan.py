"""Find personal identifiers restated in tracked files (ADR 0013).

The identifiers themselves (the candidate's name, contact details, employers, share-link
IDs) live in the vault's ``private/pii-terms.json``, never in this repo, so the scan can
run in the pre-commit hook without the check itself holding any personal data. Findings
are reported as ``path:line (category)``; the matching text is never printed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Iterable, Mapping
from pathlib import Path

CATEGORIES = ("names", "emails", "phones", "employers", "identifiers")
# Matched case-insensitively; everything else (employers, identifiers) case-sensitively.
_CASE_INSENSITIVE = frozenset({"names", "emails"})


def load_terms(path: Path) -> dict[str, list[str]]:
    """Read ``{category: [terms]}``; unknown categories and non-string terms are errors."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object of category -> list of terms")
    terms: dict[str, list[str]] = {}
    for category, values in data.items():
        if category not in CATEGORIES:
            raise ValueError(f"{path}: unknown category {category!r} (expected {CATEGORIES})")
        if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
            raise ValueError(f"{path}: {category} must be a list of non-empty strings")
        terms[category] = values
    return terms


def _compile(category: str, values: Iterable[str]) -> re.Pattern[str] | None:
    """One pattern per category.

    The boundary tests are written once around all the literal terms, not once per term: with a
    lookbehind at the start of every alternative the regex engine cannot skip ahead to a literal,
    and a scan of the tracked files took 17 s instead of 1.3 s (ADR 0032). The two forms match the
    same lines; ``tests/test_pii_scan_equivalence.py`` keeps the older one as the reference.
    """
    literals: list[str] = []
    shaped: list[str] = []
    for value in sorted({v.strip() for v in values if len(v.strip()) >= 3}, key=len, reverse=True):
        if category == "phones":
            # Any separator style between digit groups.
            digits = re.sub(r"\D", "", value)
            if len(digits) == 10:
                shaped.append(rf"\(?{digits[:3]}\)?[-. ]?{digits[3:6]}[-. ]?{digits[6:]}")
                continue
        literals.append(re.escape(value))
    if literals:
        # A term must not sit inside a longer word, but one that follows a written-out
        # escape such as the two characters ``\n`` in a string literal still counts.
        shaped.append(
            r"(?:(?<![\w])|(?<=\\n)|(?<=\\t)|(?<=\\r))(?:" + "|".join(literals) + r")(?![\w])"
        )
    if not shaped:
        return None
    flags = re.IGNORECASE if category in _CASE_INSENSITIVE else 0
    return re.compile("|".join(shaped), flags)


def find_pii(
    terms: Mapping[str, Iterable[str]],
    files: Mapping[str, str],
    allow: Collection[str] = (),
) -> list[str]:
    """``path:line (category)`` for each line naming a private identifier.

    ``allow`` lists paths still waiting to be cleaned up; matches in them are skipped.
    """
    patterns = {c: p for c, v in terms.items() if (p := _compile(c, v)) is not None}
    findings: list[str] = []
    for path, text in files.items():
        if path in allow:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for category, pattern in patterns.items():
                if pattern.search(line):
                    findings.append(f"{path}:{number} ({category})")
    return findings
