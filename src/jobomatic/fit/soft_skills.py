"""Soft-skill requirement lines ("Excellent communication"), kept out of the core set (ADR 0021).

The phrase list lives in ``soft_skill_phrases.json`` so it can be edited without touching code.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_PHRASES_FILE = Path(__file__).with_name("soft_skill_phrases.json")


@lru_cache(maxsize=1)
def _phrases() -> tuple[str, ...]:
    data = json.loads(_PHRASES_FILE.read_text(encoding="utf-8"))
    return tuple(p.lower() for p in data["phrases"])


def is_soft_skill(requirement: str) -> bool:
    """True when the requirement text contains a soft-skill phrase."""
    lowered = requirement.lower()
    return any(phrase in lowered for phrase in _phrases())
