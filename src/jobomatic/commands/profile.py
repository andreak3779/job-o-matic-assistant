"""The profile: check it, and print it whole or in slices (ADR 0028).

``validate`` returns the consistency issues and the counts that drifted from the imported learning
data. ``show`` returns the profile as markdown (the product *is* text, so the payload is a string).
Neither prints. The JSON Schema printer stays in the command line module: nothing else asks for it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from jobomatic import bootstrap
from jobomatic.learning.model import Kind, LearningItem, Provider
from jobomatic.learning.service import LearningError
from jobomatic.privacy.guard import scan_text
from jobomatic.profile import profile_text, service
from jobomatic.profile.model import Profile
from jobomatic.profile.service import Issue, ProfileError, check
from jobomatic.results import CommandResult, Message, guarded, ok

PARTS = ("full", "facts", "contact", "section")


# -- validate ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidateData:
    roles: int
    certifications: int
    projects: int
    stories: int
    issues: tuple[Issue, ...]
    drift: tuple[str, ...]

    @property
    def errors(self) -> int:
        return sum(1 for i in self.issues if i.level == "error")


def validate() -> CommandResult[ValidateData]:
    """Load the profile and run its checks. A profile with an error is a failed result that still
    carries what was found."""
    return guarded(_validate)


def _problem(text: str) -> CommandResult[Any]:
    """A failure the profile commands have always printed as ``[ERROR] ...`` on stdout."""
    return CommandResult("error", messages=(Message("info", f"[ERROR] {text}"),))


def _validate() -> CommandResult[ValidateData]:
    try:
        profile = bootstrap.profile_repository().load()
    except ProfileError as exc:
        return _problem(str(exc))
    issues = check(profile)
    try:
        drift = learning_drift(profile, bootstrap.learning_store().load())
    except LearningError as exc:
        drift = [f"learning data unreadable, so counts were not compared: {exc}"]
    data = ValidateData(
        len(profile.roles),
        len(profile.certifications),
        len(profile.projects),
        len(profile.stories),
        tuple(issues),
        tuple(drift),
    )
    if data.errors:
        # A plain line on stdout after the issues, as the command has always printed it.
        return CommandResult(
            "error", data, (Message("info", f"Profile has {data.errors} error(s)."),)
        )
    return ok(data)


def render_validate(data: ValidateData) -> str:
    lines = [f"[{i.level.upper()}] {i.where}: {i.message}" for i in data.issues]
    lines += [f"[WARNING] {message}" for message in data.drift]
    if not data.errors:
        warnings = len(data.issues) + len(data.drift)
        lines.append(
            f"[OK] Profile valid: {data.roles} roles, {data.certifications} "
            f"certifications, {data.projects} projects, {data.stories} stories"
            + (f", {warnings} warning(s)" if warnings else "")
        )
    return "\n".join(lines)


# -- show --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ShowData:
    """A slice of the profile as markdown, and the names asked for that are not in it."""

    text: str
    missing: tuple[str, ...] = ()


def show(
    part: str, names: tuple[str, ...] = (), *, public: bool = False
) -> CommandResult[ShowData]:
    """The profile as markdown: ``full``, ``facts``, ``contact`` or ``section`` (with ``names``).

    ``public`` is the view that may appear on LinkedIn, GitHub and job boards: no contact details,
    and nothing that looks like personal data (ADR 0018).
    """
    return guarded(lambda: _show(part, list(names), public))


def _show(part: str, names: list[str], public: bool) -> CommandResult[ShowData]:
    try:
        profile = bootstrap.load_profile()
    except ProfileError as exc:
        return _problem(str(exc))
    if public:
        sections = profile_text.presence_sections(service.presence_view(profile))
        if part == "contact":
            return _problem("contact details are not part of the public view")
        if part == "facts":
            part = "full"
    else:
        facts = profile_text.facts_sections(profile)
        sections = [*facts, profile_text.resume_section(profile)]
        if part == "contact":
            return ok(ShowData(profile_text.contact_text(profile) + "\n"))
        if part == "facts":
            sections = facts
    missing: tuple[str, ...] = ()
    if part == "section":
        sections, not_found = profile_text.pick(sections, names)
        missing = tuple(not_found)
        if not sections:
            lines = [f"[ERROR] no section called {name!r}" for name in missing]
            return CommandResult(
                "error",
                messages=tuple(Message("info", t) for t in lines or ["[ERROR] no section named"]),
            )
    text = profile_text.render(sections)
    if public:
        problems = scan_text(text, source="public profile")
        if problems:
            return _problem(f"possible personal data in the public text: {problems}")
    return ok(ShowData(text, missing))


def render_show(data: ShowData) -> str:
    """What the command line printed: an ``[ERROR]`` line for each name not found, then the slice
    exactly as it is (the slices end with their own newline, so none is added)."""
    lines = "".join(f"[ERROR] no section called {name!r}\n" for name in data.missing)
    return (lines + data.text).removesuffix("\n")


_AZURE_COUNTS = re.compile(r"(\d+)\s*courses?\s*\+\s*(\d+)\s*labs", re.IGNORECASE)
_PACE = re.compile(
    r"Pace of learning:\s*(\d+)\s*courses completed.*?(\d+)\s*labs\s*\((\d+)\s*completed", re.I
)
_COPILOT = re.compile(r"GitHub Copilot:\s*(\d+)\s*courses", re.IGNORECASE)
_LEADERSHIP = re.compile(r"Communication:\s*(\d+)\s*leadership/communication", re.IGNORECASE)


def learning_drift(profile: Profile, items: list[LearningItem]) -> list[str]:
    """Counts written by hand in the profile that no longer match the imported learning data.

    Replaces the old cross-file course-count lint. Only completed work is compared, because
    only completed work is stored. Returns warnings; the wording is the candidate's own and is
    never edited here.
    """
    if not items:
        return []
    ps = [i for i in items if i.provider is Provider.PLURALSIGHT]
    courses = sum(i.kind is Kind.COURSE for i in ps)
    labs = sum(i.kind is Kind.LAB for i in ps)
    azure = [i for i in ps if "Microsoft Azure" in i.topics]
    claims: list[tuple[str, str, int, int]] = []

    def add(where: str, label: str, claimed: int, actual: int) -> None:
        if claimed != actual:
            claims.append((where, label, claimed, actual))

    summary = _AZURE_COUNTS.search(profile.coursework_summary or "")
    if summary:
        add(
            "coursework_summary",
            "Azure courses",
            int(summary[1]),
            sum(i.kind is Kind.COURSE for i in azure),
        )
        add(
            "coursework_summary",
            "Azure labs",
            int(summary[2]),
            sum(i.kind is Kind.LAB for i in azure),
        )
    for text in profile.identity.differentiators:
        if m := _PACE.search(text):
            add("identity.differentiators", "completed Pluralsight courses", int(m[1]), courses)
            add("identity.differentiators", "completed Pluralsight labs", int(m[3]), labs)
        if m := _COPILOT.search(text):
            n = sum(i.kind is Kind.COURSE and "copilot" in i.title.lower() for i in ps)
            add("identity.differentiators", "GitHub Copilot courses", int(m[1]), n)
        if m := _LEADERSHIP.search(text):
            n = sum("Leadership & Soft Skills" in i.topics for i in ps)
            add("identity.differentiators", "leadership/communication courses", int(m[1]), n)
    return [
        f"{where}: says {claimed} {label}, the imported learning data has {actual}"
        for where, label, claimed, actual in claims
    ]
