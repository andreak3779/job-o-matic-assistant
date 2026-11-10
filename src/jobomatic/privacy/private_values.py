"""Detect private job-search values leaking into tracked files.

``private/search-constraints.json`` is gitignored on purpose. The way it leaks is not
by being committed but by being *retyped* — into a SKILL.md, a doc, a test fixture.
This finds those copies so the pre-commit hook can stop them.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from jobomatic.fit.constraints import SearchConstraints


def _patterns(constraints: SearchConstraints) -> dict[str, re.Pattern[str]]:
    found: dict[str, re.Pattern[str]] = {}
    base = constraints.min_permanent_base_cad
    if base is not None:
        whole = int(base)
        alternatives = [
            rf"(?<![\d,.]){whole:,}(?!\d)",
            rf"(?<![\d,.]){whole}(?!\d)",
        ]
        if whole % 1000 == 0:
            alternatives.append(rf"(?<![\d.]){whole // 1000}\s?[kK]\b")
        found["permanent base minimum"] = re.compile("|".join(alternatives))
    hourly = constraints.min_contract_hourly_cad
    if hourly is not None:
        number = re.escape(f"{hourly:g}")
        found["contract hourly minimum"] = re.compile(
            rf"\$\s?{number}(?:\.\d+)?\s?(?:/\s?h|per\s+h|an\s+hour)", re.IGNORECASE
        )
    return found


def find_leaks(constraints: SearchConstraints, files: Mapping[str, str]) -> list[str]:
    """``path:line (what)`` for every tracked line that restates a private minimum."""
    leaks: list[str] = []
    patterns = _patterns(constraints)
    for path, text in files.items():
        for number, line in enumerate(text.splitlines(), start=1):
            for what, pattern in patterns.items():
                if pattern.search(line):
                    leaks.append(f"{path}:{number} ({what})")
    return leaks
