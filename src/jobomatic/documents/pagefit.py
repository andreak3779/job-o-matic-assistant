"""Fit a resume to its page budget by trimming, in the order the old template documented.

Pure: only the content model is used, so this runs anywhere and is tested without LibreOffice.
The height is an ESTIMATE from the layout the DOCX renderer produces (font sizes, spacing, the
width of a line). It is calibrated against LibreOffice's real page count and kept a little
conservative; ``--check-pages`` measures the real count (``PageCounter``).

Trim order, most expendable first. Bullets are already ordered most relevant first, so the last
bullet of a role is the one to drop, and the oldest role gives up bullets before a newer one:

1. at most ``MAX_SKILL_LINES`` skill categories (the first ones: they are ordered by relevance);
2. long skill lists shortened, never inside a parenthesis;
3. bullets: a self-directed role (no employer) first, down to 2 and then 1 bullet while employers
   still keep 4 or more; then the oldest employer first, down to a floor that falls from 5 to 2;
4. the roles older than the ``RECENT_ROLES`` most recent go to 2 bullets first; as a last resort 5
   skill lines of 5 items, one bullet for those older roles, and only then 2 for the recent ones.

A role is never dropped, and a recent role never goes below ``MIN_BULLETS``. If that still does
not fit, the content is refused (ADR 0007) instead of producing a resume that runs onto a third
page.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from jobomatic.documents.model import ResumeJob, SkillLine, TailoredResume
from jobomatic.documents.service import DocumentError

RESUME_MAX_PAGES = 2
MAX_SKILL_LINES = 7
MIN_BULLETS = 2
RECENT_ROLES = 3  # the newest roles keep at least MIN_BULLETS; older ones may fall to one bullet
LAST_RESORT_SKILL_LINES = 5

# Layout constants, mirrored from the DOCX renderer (US Letter, 0.5" top and bottom, 0.75" sides,
# Carlito 9.5 pt body, 10 pt role lines). Calibrated against LibreOffice; see tests/test_pagefit.py.
_PAGE_HEIGHT_PT = 720.0  # 11" minus 1" of margin
_TEXT_WIDTH_PT = 504.0  # 8.5" minus 1.5" of margin
_BULLET_INDENT_PT = 18.0  # 0.25" hanging indent on experience bullets
_CHAR_EM = 0.44  # average character width as a share of the font size (Carlito)
_LINE_HEIGHT = 1.22  # line height as a share of the font size
_BODY = 9.5  # summary, skills, bullets
_TITLE = 10.0  # the tagline and the role lines
_SECTION = 11.0  # section headings
_CONTACT = 9.5
_NAME = 16.0
_HEADING_BEFORE = 19.5
_HEADING_AFTER = 14.6
_NEXT_JOB_BEFORE = 16.0
_CALIBRATION = (
    1.03  # measured: the raw estimate runs 1-5% above LibreOffice's real height at 0.44 em
)
_SAFETY = 0.97  # keep 3% of the budget free so a small estimate error cannot spill a line
_LATER_PAGE_HEADER_PT = (
    26.0  # the compact header (one or two lines) and its gap push the body down on later pages
)
_FIRST_PAGE_HEADER_PT = 0.0  # the empty first-page header fits inside the top margin


def _lines(text: str, size: float, width_pt: float = _TEXT_WIDTH_PT) -> int:
    per_line = max(1, int(width_pt / (size * _CHAR_EM)))
    return sum(max(1, math.ceil(len(part) / per_line)) for part in text.split("\n"))


def _para(
    text: str, size: float, *, before: float = 0, after: float = 0, width: float = _TEXT_WIDTH_PT
) -> float:
    return _lines(text, size, width) * size * _LINE_HEIGHT + before + after


def _heading() -> float:
    return _para("X", _SECTION, before=_HEADING_BEFORE, after=_HEADING_AFTER)


def estimate_height(content: TailoredResume) -> float:
    """Estimated height of the whole resume in points (one tall column)."""
    c = content.contact
    total = _FIRST_PAGE_HEADER_PT
    total += _para(c.name, _NAME, after=6)
    total += _para(content.tagline, _TITLE, after=1.5) if content.tagline else 0
    line1 = "  |  ".join(p for p in (c.email, c.phone, c.location) if p)
    line2 = "  |  ".join(p for p in (c.linkedin, c.github, c.pluralsight) if p)
    total += _para(line1, _CONTACT) + _para(line2, _CONTACT)

    total += _heading()
    total += sum(
        _para(line.strip(), _BODY, before=2 if i else 0)
        for i, line in enumerate(content.summary[:2])
    )

    total += _heading()
    total += sum(
        _para(f"{s.label}: {s.skills}", _BODY, before=1.75 if i else 0)
        for i, s in enumerate(content.skills)
    )

    total += _heading()
    width = _TEXT_WIDTH_PT - _BULLET_INDENT_PT
    for index, job in enumerate(content.experience):
        left = job.title
        if job.company:
            left += f" | {job.company}"
        if job.location:
            left += f", {job.location}"
        total += _para(f"{left}  {job.dates}", _TITLE, before=_NEXT_JOB_BEFORE if index else 0)
        total += sum(
            _para(f"•  {b}", _BODY, before=1 if i else 0, width=width)
            for i, b in enumerate(job.bullets)
        )
    if content.additional_experience.strip():
        total += _para("Additional Experience", _TITLE, before=_NEXT_JOB_BEFORE)
        total += _para(f"•  {content.additional_experience.strip()}", _BODY, width=width)
    if content.education:
        total += _heading() + sum(
            _para(f"•  {e}", _BODY, before=1 if i else 0, width=width)
            for i, e in enumerate(content.education)
        )
    total += _heading() + sum(
        _para(f"•  {line}", _BODY, before=1 if i else 0, width=width)
        for i, line in enumerate(content.certifications)
    )
    return total * _CALIBRATION


def budget_height(max_pages: int = RESUME_MAX_PAGES) -> float:
    """The height the estimate must stay under for ``max_pages`` pages."""
    return (max_pages * _PAGE_HEIGHT_PT - (max_pages - 1) * _LATER_PAGE_HEADER_PT) * _SAFETY


def pages_estimate(content: TailoredResume) -> float:
    """The estimated length in pages (for messages and tests)."""
    return estimate_height(content) / _PAGE_HEIGHT_PT


def split_skills(text: str) -> list[str]:
    """Split a skill list on commas that are not inside a parenthesis."""
    items: list[str] = []
    depth = 0
    current = ""
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            items.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        items.append(current.strip())
    return items


def _cap_skill_items(content: TailoredResume, limit: int) -> TailoredResume:
    lines = []
    for line in content.skills:
        items = split_skills(line.skills)
        lines.append(
            SkillLine(label=line.label, skills=", ".join(items[:limit]))
            if len(items) > limit
            else line
        )
    return content.model_copy(update={"skills": lines})


def _cap_skill_lines(content: TailoredResume, lines: int, items: int) -> TailoredResume:
    """Keep the first ``lines`` skill categories (they are ordered by relevance), ``items`` each."""
    return _cap_skill_items(
        content.model_copy(update={"skills": list(content.skills[:lines])}), items
    )


def _cap_bullets(
    content: TailoredResume,
    floor: int,
    max_height: float,
    from_index: int = 0,
    *,
    own_work_only: bool = False,
) -> TailoredResume:
    """Drop the last bullet of a role while it has more than ``floor`` and the resume is too tall.

    Self-directed roles (no employer) go first, then employers oldest first. Only roles at
    ``from_index`` or later (older) are touched; the list is newest first.
    """
    jobs: list[ResumeJob] = list(content.experience)
    current = content
    own_work = [i for i in range(from_index, len(jobs)) if not jobs[i].company]
    employed = (
        []
        if own_work_only
        else [i for i in range(len(jobs) - 1, from_index - 1, -1) if jobs[i].company]
    )
    for index in own_work + employed:
        while len(jobs[index].bullets) > floor and estimate_height(current) > max_height:
            jobs[index] = jobs[index].model_copy(update={"bullets": jobs[index].bullets[:-1]})
            current = content.model_copy(update={"experience": list(jobs)})
    return current


def fit_resume(content: TailoredResume, max_pages: int = RESUME_MAX_PAGES) -> TailoredResume:
    """Trim ``content`` until it is estimated to fit ``max_pages``; raise if it cannot."""
    limit = budget_height(max_pages)
    fitted = content.model_copy(update={"skills": list(content.skills[:MAX_SKILL_LINES])})

    steps: list[Callable[[TailoredResume], TailoredResume]] = [
        lambda c: _cap_skill_items(c, 16),
        lambda c: _cap_bullets(c, 5, limit),
        lambda c: _cap_bullets(c, 2, limit, own_work_only=True),
        lambda c: _cap_skill_items(c, 12),
        lambda c: _cap_bullets(c, 4, limit),
        lambda c: _cap_bullets(c, 1, limit, own_work_only=True),
        lambda c: _cap_skill_items(c, 9),
        lambda c: _cap_bullets(c, 3, limit),
        lambda c: _cap_skill_items(c, 6),
        lambda c: _cap_bullets(c, MIN_BULLETS, limit, from_index=RECENT_ROLES),
        lambda c: _cap_skill_lines(c, LAST_RESORT_SKILL_LINES, 5),
        lambda c: _cap_bullets(c, 1, limit, from_index=RECENT_ROLES),
        lambda c: _cap_bullets(c, MIN_BULLETS, limit),
    ]
    for step in steps:
        if estimate_height(fitted) <= limit:
            return fitted
        fitted = step(fitted)
    if estimate_height(fitted) <= limit:
        return fitted
    raise DocumentError(
        f"the resume would run to about {pages_estimate(fitted):.1f} pages even after trimming "
        f"skills and trimming each role to its minimum (limit {max_pages}): shorten the summary, "
        "the job headers or the additional experience in the profile"
    )
