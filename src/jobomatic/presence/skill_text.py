"""Generic markdown-parsing helpers for reading a skill's own SKILL.md prose
templates (fenced code blocks, `## ` sections) at generation time, plus a
skill-term cleanup helper for deriving an ATS-taggable skills list from the
typed public profile's ``technical_skills``. Shared by every
profile-update generator (LinkedIn, GitHub, Jobgether, Indeed/ZipRecruiter,
Pluralsight) so this parsing logic exists in exactly one place — see
CLAUDE.md ("Skills", on hardcoded facts) for why duplicating this per
generator is the failure mode to avoid.

This module used to also parse the *rendered* the public profile — that need
went away once the generators moved to `jobomatic.bootstrap.load_presence_view`
and `jobomatic.profile.copy_fragments.compute_copy_fragments` for profile data directly;
what's left here is purely about SKILL.md's own prose templates.
"""

from __future__ import annotations

import re
from collections.abc import Set as AbstractSet


def md_sections(text: str) -> list[tuple[str, int, int]]:
    """Return (heading, start_line, end_line) for every top-level '## ' heading.

    Lines inside a fenced code block never count as headings: a README template
    in a SKILL.md can legitimately contain its own ``## Hi, I'm ...`` line, and
    treating that as a section boundary would cut the section short.
    """
    lines = text.split("\n")
    headings: list[tuple[int, str]] = []
    in_fence = False
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("## "):
            headings.append((i, line))
    headings.append((len(lines), ""))
    return [
        (headings[i][1][3:].strip(), headings[i][0], headings[i + 1][0])
        for i in range(len(headings) - 1)
    ]


def section_text(text: str, name: str) -> str | None:
    lines = text.split("\n")
    for heading, start, end in md_sections(text):
        if heading.lower() == name.lower():
            return "\n".join(lines[start + 1 : end]).strip()
    return None


def fenced_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] | None = None
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            if current is None:
                current = []
            else:
                blocks.append("\n".join(current))
                current = None
            continue
        if current is not None:
            current.append(line)
    return blocks


def curated_tags(skill_text: str, heading: str, *, cap: int) -> list[str] | None:
    """Comma- or newline-separated tags from the first fenced block under ``heading``.

    Returns ``None`` when the section has no fenced block, so a caller can fall
    back to deriving tags from the profile. The result is cut to ``cap``.
    """
    blocks = fenced_blocks(section_text(skill_text, heading) or "")
    if not blocks:
        return None
    tags = [t.strip() for t in re.split(r"[,\n]", blocks[0]) if t.strip()]
    return tags[:cap]


def substitute_fragments(text: str, fragments: dict[str, str]) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: fragments.get(m.group(1), m.group(0)), text)


def split_top_level_commas(text: str) -> list[str]:
    """Split on commas that aren't inside parentheses."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def clean_skill_term(raw: str) -> str | None:
    term = re.sub(r"\s*\([^)]*\)\s*$", "", raw).strip()
    if not term or len(term.split()) > 4:
        return None
    return term


def derive_skill_terms(
    skills_categories: dict[str, str],
    *,
    exclude: AbstractSet[str] = frozenset(),
    limit: int | None = None,
) -> list[str]:
    """Flatten every category's comma-separated terms into a deduped,
    cleaned, LinkedIn/ATS-taggable list — dropping ``(course-level)``
    qualifiers and multi-clause phrases, and anything already in ``exclude``
    (case-insensitive). ``skills_categories`` is typically built by joining
    each ``PresenceView.technical_skills`` category's list back into one
    comma string (see any Project 3 generator's ``_step3_skills``/
    ``_skills_categories`` helper) so this can re-split on top-level commas
    only and strip trailing qualifiers.
    """
    seen = {t.strip().lower() for t in exclude}
    result: list[str] = []
    for items_text in skills_categories.values():
        for raw in split_top_level_commas(items_text):
            term = clean_skill_term(raw)
            if term and term.lower() not in seen:
                seen.add(term.lower())
                result.append(term)
    return result[:limit] if limit is not None else result
