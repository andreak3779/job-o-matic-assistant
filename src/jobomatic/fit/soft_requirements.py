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
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Protocol

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
    # For an education line: the user's own credentials, shown beside it for the user to compare.
    on_file: str = ""


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


# Credential levels a posting can name, and the stored levels that answer each one.
_NAMED_LEVELS: tuple[tuple[str, re.Pattern[str], frozenset[str]], ...] = (
    ("certificate", re.compile(r"\bcertificat\w*", re.IGNORECASE), frozenset({"certificate"})),
    (
        "diploma",
        re.compile(r"\bdiploma\b", re.IGNORECASE),
        frozenset({"diploma", "advanced-diploma"}),
    ),
    (
        "degree",
        re.compile(r"\bdegree\b|\bbachelor\w*", re.IGNORECASE),
        frozenset({"bachelor", "master", "doctorate"}),
    ),
    (
        "master's",
        re.compile(r"\bmaster(?:['’]?s| of)\b", re.IGNORECASE),
        frozenset({"master", "doctorate"}),
    ),
)
_NAMED_FIELD_RE = re.compile(r"\bcomputer science\b", re.IGNORECASE)


class EducationEntry(Protocol):
    """What the cross-reference reads from a stored education entry. A structural type, so this
    module does not import the profile module (the fit rules stay independent of it)."""

    @property
    def credential(self) -> str: ...
    @property
    def level(self) -> str | None: ...
    @property
    def field_of_study(self) -> str | None: ...
    @property
    def completed(self) -> bool: ...


def education_on_file(line: str, education: Iterable[EducationEntry]) -> str:
    """The user's structured education entries beside a posting's education line.

    Facts only: the levels the posting names, the levels on file that answer them, and each entry
    with its level, field and whether it was finished. It never says the requirement is met: that
    is for the user (and the employer) to judge. Entries with no level and no field are not
    schooling and are left out; with none on file the result is empty.
    """
    entries = [e for e in education if e.level or e.field_of_study]
    if not entries:
        return ""
    named = [(label, held) for label, pattern, held in _NAMED_LEVELS if pattern.search(line)]
    field_named = _NAMED_FIELD_RE.search(line) is not None
    parts = []
    if named or field_named:
        wants = [label for label, _ in named] + (["computer science"] if field_named else [])
        parts.append("Posting names " + ", ".join(wants))
    described = []
    for e in entries:
        facts: list[str] = [e.level] if e.level else []
        if e.field_of_study:
            facts.append(f"field: {e.field_of_study}")
        if not e.completed:
            facts.append("not completed")
        described.append(f"{e.credential} ({'; '.join(facts)})" if facts else e.credential)
    parts.append("You have " + "; ".join(described))
    if named:
        held = sorted(
            {
                e.level
                for e in entries
                if e.level and e.completed and any(e.level in levels for _, levels in named)
            }
        )
        parts.append("Named levels held: " + (", ".join(held) if held else "none on file"))
    return ". ".join(parts) + ". Whether the level and field fit is for you to judge."


def with_education_on_file(
    soft: Iterable[SoftRequirement], education: Iterable[EducationEntry]
) -> tuple[SoftRequirement, ...]:
    """Each education requirement with the user's credentials attached; others unchanged."""
    entries = list(education)
    return tuple(
        replace(s, on_file=education_on_file(s.line, entries)) if s.kind == "education" else s
        for s in soft
    )
