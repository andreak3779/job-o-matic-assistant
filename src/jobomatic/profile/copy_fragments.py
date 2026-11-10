"""Compute the "Copy Fragments" — course-count sentence, cert status short form, etc. —
that Project 3's profile-update generators splice into draft copy instead of hand-embedding a
number that goes stale.

Called directly with the public view's differentiators, certifications and coursework line.
"""

from __future__ import annotations

import re

from jobomatic.profile.model import Certification, CertStatus

_AZURE_COUNTS_RE = re.compile(r"(\d+)\s*courses?\s*\+\s*(\d+)\s*labs", re.IGNORECASE)

FRAGMENT_KEYS = [
    "course_count_sentence",
    "cert_status_short",
    "azure_course_lab_sentence",
    "github_copilot_course_count",
    "leadership_course_count",
]


def _cert_status_short(cert_registry: list[Certification]) -> str:
    parts: list[str] = []
    for c in cert_registry:
        if c.status == CertStatus.CERTIFIED:
            parts.append(f"{c.code} Certified")
        elif c.status == CertStatus.IN_PROGRESS:
            parts.append(f"{c.code} in progress")
    return " · ".join(parts)


def _differentiator_match(differentiators: list[str], pattern: str) -> re.Match[str] | None:
    for item in differentiators:
        match = re.search(pattern, item, re.IGNORECASE)
        if match:
            return match
    return None


def _azure_coursework_counts(cell: str | None) -> tuple[str, str] | None:
    if not cell:
        return None
    match = _AZURE_COUNTS_RE.search(cell)
    return (match.group(1), match.group(2)) if match else None


def compute_copy_fragments(
    differentiators: list[str],
    cert_registry: list[Certification],
    azure_coursework: str | None,
) -> dict[str, str]:
    fragments: dict[str, str] = {"cert_status_short": _cert_status_short(cert_registry)}

    copilot = _differentiator_match(differentiators, r"GitHub Copilot:\s*(\d+)\s*courses")
    fragments["github_copilot_course_count"] = copilot.group(1) if copilot else ""

    leadership = _differentiator_match(
        differentiators, r"Communication:\s*(\d+)\s*leadership/communication"
    )
    fragments["leadership_course_count"] = leadership.group(1) if leadership else ""

    azure = _azure_coursework_counts(azure_coursework)
    if azure:
        courses, labs = azure
        fragments["azure_course_lab_sentence"] = (
            f"{courses} Pluralsight courses and {labs} hands-on labs across Azure"
        )
    else:
        fragments["azure_course_lab_sentence"] = ""

    pace = _differentiator_match(
        differentiators,
        r"Pace of learning:\s*(\d+)\s*courses completed \+\s*(\d+)\s*in progress \+\s*"
        r"(\d+)\s*labs\s*\((\d+)\s*completed,\s*(\d+)\s*in progress\)\s*=\s*\*{0,2}(\d+)\s*total",
    )
    if pace:
        completed, in_progress, labs, labs_done, labs_wip, total = pace.groups()
        fragments["course_count_sentence"] = (
            f"{completed} Pluralsight courses completed and {in_progress} more in progress, "
            f"plus {labs} hands-on labs ({labs_done} completed, {labs_wip} in progress) — {total} total"
        )
    else:
        fragments["course_count_sentence"] = ""

    return fragments


def fragments_block(fragments: dict[str, str]) -> str:
    return "\n".join(f'{k}: "{fragments.get(k, "")}"' for k in FRAGMENT_KEYS)
