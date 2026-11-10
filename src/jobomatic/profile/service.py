"""Profile use cases: load with checks, and the public view.

Depends only on ports and the model: no files, no YAML, no network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from jobomatic.profile.model import (
    Certification,
    CertStatus,
    GapSeverity,
    PresenceView,
    Profile,
    Project,
    Role,
    SkillGroup,
    Story,
)
from jobomatic.profile.ports import ProfileRepository
from jobomatic.profile.visibility import public_view

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_YEAR = re.compile(r"\b(19|20)\d{2}\b")


class ProfileError(Exception):
    """The profile cannot be read or fails its checks (ADR 0007: fail loud)."""


@dataclass(frozen=True)
class Issue:
    level: Literal["error", "warning"]
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level}: {self.where}: {self.message}"


def load_profile(repo: ProfileRepository) -> Profile:
    """Load the profile and refuse to return one that has errors. Warnings do not block."""
    profile = repo.load()
    errors = [issue for issue in check(profile) if issue.level == "error"]
    if errors:
        raise ProfileError("profile failed its checks:\n" + "\n".join(f"  {e}" for e in errors))
    return profile


def public_data(profile: Profile) -> dict[str, Any]:
    """The public part of the profile as plain data (dates as ISO strings)."""
    return public_view(profile)


def presence_view(profile: Profile) -> PresenceView:
    """The part of the profile that may appear on public surfaces (replaces the public profile)."""
    data = public_view(profile)
    return PresenceView(
        headline=data["identity"]["headline"],
        summary=data["identity"]["summary"],
        differentiators=data["identity"].get("differentiators", []),
        certifications=[Certification.model_validate(c) for c in data.get("certifications", [])],
        skill_groups=[
            SkillGroup.model_validate(g) for g in data.get("skills", {}).get("groups", [])
        ],
        projects=[Project.model_validate(p) for p in data.get("projects", [])],
        roles=[Role.model_validate(r) for r in data.get("roles", [])],
        coursework_summary=data.get("coursework_summary"),
    )


def mark_stories_used(
    profile: Profile, titles: list[str], *, last_used: str, used_for: str
) -> list[Story]:
    """The stories with ``last_used`` and ``used_for`` updated for the ones named.

    Fails closed: a title that matches no story raises, so a wrong guess can never quietly edit
    hand-written interview material. Returns the whole story list, ready to save.
    """
    known = {s.title for s in profile.stories}
    missing = [t for t in titles if t not in known]
    if missing:
        raise ProfileError(f"no STAR story with the title(s) {missing}")
    updated: list[Story] = []
    for story in profile.stories:
        if story.title in titles:
            uses = story.used_for if used_for in story.used_for else [*story.used_for, used_for]
            story = story.model_copy(update={"last_used": last_used, "used_for": uses})
        updated.append(story)
    return updated


def check(profile: Profile) -> list[Issue]:
    """Consistency checks the schema cannot express. Runs on every load."""
    issues: list[Issue] = []
    issues += _check_identity(profile)
    issues += _check_certifications(profile)
    issues += _check_skills(profile)
    issues += _check_roles(profile)
    issues += _check_unique(profile)
    issues += _check_split_items(profile)
    return issues


def _check_identity(profile: Profile) -> list[Issue]:
    issues: list[Issue] = []
    identity = profile.identity
    if not identity.name.strip():
        issues.append(Issue("error", "identity.name", "is empty"))
    if not _EMAIL.match(identity.email):
        issues.append(Issue("error", "identity.email", "does not look like an email address"))
    rules = profile.rules
    headline = identity.headline.lower()
    for word in rules.headline_forbidden_words:
        if re.search(rf"\b{re.escape(word.lower())}\b", headline):
            issues.append(
                Issue("error", "identity.headline", f"contains {word!r}, which the rules forbid")
            )
    phrase = rules.headline_required_phrase
    if phrase and phrase.lower() not in headline:
        issues.append(Issue("error", "identity.headline", f"does not contain {phrase!r}"))
    return issues


def _check_certifications(profile: Profile) -> list[Issue]:
    issues: list[Issue] = []
    for cert in profile.certifications:
        where = f"certifications[{cert.code}]"
        if cert.status is CertStatus.CERTIFIED and cert.date is None:
            issues.append(Issue("error", where, "is certified but has no date"))
        if cert.status is not CertStatus.CERTIFIED and cert.date is not None:
            issues.append(Issue("warning", where, f"has a date but status is {cert.status.value}"))
        if cert.credential_url and not cert.credential_url.startswith("https://"):
            issues.append(Issue("error", where, "credential_url must start with https://"))
    return issues


def _check_skills(profile: Profile) -> list[Issue]:
    issues: list[Issue] = []
    by_skill: dict[str, set[GapSeverity]] = {}
    for gap in profile.skills.gaps:
        by_skill.setdefault(gap.skill.strip().lower(), set()).add(gap.severity)
    for skill, severities in by_skill.items():
        if len(severities) > 1:
            issues.append(
                Issue("error", f"skills.gaps[{skill}]", "is both a genuine and a resolved gap")
            )
    return issues


def _first_year(text: str | None) -> int | None:
    match = _YEAR.search(text or "")
    return int(match.group(0)) if match else None


def _check_roles(profile: Profile) -> list[Issue]:
    issues: list[Issue] = []
    window = profile.rules.resume_window_start
    if window is None:
        return issues
    for role in profile.roles:
        start = _first_year(role.dates)
        if role.tier == "resume" and start is not None and start < window.year:
            issues.append(
                Issue(
                    "warning",
                    f"roles[{role.company}]",
                    f"starts in {start}, before the resume window ({window.year}); "
                    "should it be tier: legacy?",
                )
            )
    return issues


def _check_unique(profile: Profile) -> list[Issue]:
    issues: list[Issue] = []
    for label, names in (
        ("certifications", [c.code for c in profile.certifications]),
        ("projects", [p.name for p in profile.projects]),
        ("stories", [s.title for s in profile.stories]),
    ):
        seen: set[str] = set()
        for name in names:
            if name in seen:
                issues.append(Issue("error", label, f"{name!r} appears more than once"))
            seen.add(name)
    return issues


def _unbalanced(text: str) -> bool:
    """True when the brackets in ``text`` do not close, or close before they open."""
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return True
    return depth != 0


def _check_split_items(profile: Profile) -> list[Issue]:
    """List items with unbalanced brackets: a list cut at a comma inside them.

    "NgRx (store, effects, entity)" split on every comma becomes "NgRx (store", "effects",
    "entity)". The generators join a list back with commas, so the damage is invisible there, but
    it shows wherever a list is shortened or matched item by item. A list item is one thing: if its
    brackets do not close, join it with the next one. Free text (summaries, descriptions) is not
    checked, only the items of lists.
    """
    issues: list[Issue] = []

    def walk(value: Any, where: str) -> None:
        if isinstance(value, dict):
            for key, inner in value.items():
                walk(inner, f"{where}.{key}" if where else str(key))
        elif isinstance(value, list):
            for index, inner in enumerate(value):
                if isinstance(inner, str):
                    if _unbalanced(inner):
                        shown = inner if len(inner) <= 60 else inner[:57] + "..."
                        issues.append(
                            Issue(
                                "error",
                                f"{where}[{index}]",
                                f"{shown!r} has unbalanced brackets; it looks like a list item cut "
                                "at a comma inside the brackets, so join it with its neighbour",
                            )
                        )
                else:
                    walk(inner, f"{where}[{index}]")

    walk(profile.model_dump(), "")
    return issues
