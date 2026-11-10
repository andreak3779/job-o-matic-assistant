"""Education and years-of-experience lines in a posting (ADR 0021, step C1).

These lines are listed for the user to read and are never scored: a missing degree or a short
career is not a skill gap. Pure functions, no I/O.

Rules, as the owner stated them:
- the years figure is the MINIMUM: "3+ years" is 3, "7-10 years" is 7, "3+ years or equivalent" is 3;
- "senior-level" with no figure reads as 5 years;
- a line accepts an alternative only when it says "or equivalent", "or related field" or
  "or equivalent experience".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_YEARS_RE = re.compile(
    r"(\d+)\s*(?:\+|plus)?\s*(?:(?:[-–—]|to)\s*\d+\s*\+?\s*)?(?:years?|yrs?)\b",
    re.IGNORECASE,
)
_SENIOR_RE = re.compile(r"\bsenior[\s-]*level\b", re.IGNORECASE)
SENIOR_LEVEL_YEARS = 5

_EDUCATION_RE = re.compile(
    r"\b(?:bachelor|degree|diploma|certificat\w*|certified|college|university|"
    r"post[\s-]?secondary|computer science|formal\s+training)\b|\bmaster['’]?s\b|\bmaster of\b",
    re.IGNORECASE,
)
_ALTERNATIVE_RE = re.compile(
    r"\bor\s+(?:an?\s+)?(?:equivalent|related\s+(?:field|program|programme|discipline|area))\b",
    re.IGNORECASE,
)

EQUIVALENT_NOTE = "equivalent accepted"
OPTIONAL_NOTE = "optional (an asset) — check this yourself"
OPTIONAL_EQUIVALENT_NOTE = "optional (an asset), equivalent accepted"
LEVEL_NOTE = "senior title — check this yourself"
BODY_LEVEL_NOTE = "senior level named in the posting text — check this yourself"
SOFT_SKILL_NOTE = "listed, never scored"
LABELS = {
    "years": "Years",
    "education": "Education",
    "level": "Level",
    "soft skill": "Soft skill",
}

# Title words that mark a senior or leading role. Listed for the user to read; never scored.
_LEVEL_RE = re.compile(r"\b(?:senior|principal|staff|lead|manager|director)\b", re.IGNORECASE)
CHECK_NOTE = "stated as required — check this yourself"


@dataclass(frozen=True)
class SoftRequirement:
    kind: str  # "years", "education", "level" or "soft skill"
    line: str
    note: str
    minimum_years: int | None = None


def minimum_years(text: str) -> int | None:
    """The smallest years figure the line asks for, or ``None`` when it names none."""
    match = _YEARS_RE.search(text)
    if match:
        return int(match.group(1))
    if _SENIOR_RE.search(text):
        return SENIOR_LEVEL_YEARS
    return None


def has_years_figure(text: str) -> bool:
    """True when the line carries an explicit years figure ("5+ years"); "senior-level" alone is not."""
    return _YEARS_RE.search(text) is not None


def is_education(text: str) -> bool:
    return _EDUCATION_RE.search(text) is not None


def classify(line: str) -> list[SoftRequirement]:
    """The soft requirements a line holds: a years entry, an education entry, both, or none."""
    found: list[SoftRequirement] = []
    years = minimum_years(line)
    if years is not None:
        senior_only = _YEARS_RE.search(line) is None
        note = (
            f"senior-level, read as {years}+ years"
            if senior_only
            else f"minimum {years} year{'s' if years != 1 else ''}"
        )
        found.append(SoftRequirement("years", line, note, years))
    if is_education(line):
        accepted = _ALTERNATIVE_RE.search(line) is not None
        found.append(
            SoftRequirement("education", line, EQUIVALENT_NOTE if accepted else CHECK_NOTE)
        )
    return found


def classify_optional(line: str) -> list[SoftRequirement]:
    """An education, certificate or training line under a nice-to-have heading: listed, never
    scored. Whatever skills it names are what the certificate covers, not skills the user is asked
    to have used."""
    if not is_education(line):
        return []
    note = OPTIONAL_EQUIVALENT_NOTE if _ALTERNATIVE_RE.search(line) else OPTIONAL_NOTE
    return [SoftRequirement("education", line, note)]


def title_level(title: str) -> SoftRequirement | None:
    """A senior-level word in the job title ("Principal", "Lead"…), or ``None``."""
    match = _LEVEL_RE.search(title)
    return SoftRequirement("level", title, LEVEL_NOTE) if match else None


def soft_skill(line: str) -> SoftRequirement:
    """A soft-skill line (ADR 0023): listed for the user to read, never scored, never a gap."""
    return SoftRequirement("soft skill", line, SOFT_SKILL_NOTE)


def body_level(title: str, text: str) -> SoftRequirement | None:
    """A level word written in front of the title in the posting text ("Senior Full Stack
    Engineer" under the title "Full Stack Engineer"), or ``None``. Used when the title itself
    names no level."""
    if not title or title_level(title) is not None:
        return None
    match = re.search(
        rf"\b(?:senior|principal|staff|lead|manager|director)\s+{re.escape(title)}",
        text,
        re.IGNORECASE,
    )
    return SoftRequirement("level", match.group(0), BODY_LEVEL_NOTE) if match else None
