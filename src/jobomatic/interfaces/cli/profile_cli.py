"""``profile`` subcommands: check the vault's profile and print its JSON Schema.

A thin driving adapter: it calls the profile use cases through ``jobomatic.bootstrap``.
"""

from __future__ import annotations

import argparse
import json
import re

from jobomatic import bootstrap
from jobomatic.learning.model import Kind, LearningItem, Provider
from jobomatic.learning.service import LearningError
from jobomatic.privacy.guard import scan_text
from jobomatic.profile import profile_text, service
from jobomatic.profile.model import Profile
from jobomatic.profile.service import ProfileError, check

COMMAND = "profile"


def register(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    profile = subparsers.add_parser("profile", help="The typed profile stored in the vault")
    sub = profile.add_subparsers(dest="profile_command", required=True)
    sub.add_parser("validate", help="Load the profile and run its consistency checks")
    sub.add_parser("schema", help="Print the JSON Schema generated from the profile models")
    show = sub.add_parser("show", help="Print the profile as markdown, whole or in slices")
    show.add_argument(
        "--public",
        action="store_true",
        help="Only what may appear on LinkedIn, GitHub and job boards (no contact details)",
    )
    show.add_argument("part", choices=("full", "facts", "contact", "section"))
    show.add_argument("names", nargs="*", help="Section names, for 'section'")


def run(args: argparse.Namespace) -> int:
    if args.profile_command == "schema":
        print(json.dumps(Profile.model_json_schema(), indent=2))
        return 0
    if args.profile_command == "show":
        return _show(args.part, args.names, args.public)
    return _validate()


def _show(part: str, names: list[str], public: bool) -> int:
    try:
        profile = bootstrap.load_profile()
    except ProfileError as exc:
        print(f"[ERROR] {exc}")
        return 1
    if public:
        sections = profile_text.presence_sections(service.presence_view(profile))
        if part == "contact":
            print("[ERROR] contact details are not part of the public view")
            return 1
        if part == "facts":
            part = "full"
    else:
        facts = profile_text.facts_sections(profile)
        sections = [*facts, profile_text.resume_section(profile)]
        if part == "contact":
            print(profile_text.contact_text(profile))
            return 0
        if part == "facts":
            sections = facts
    if part == "section":
        sections, missing = profile_text.pick(sections, names)
        for name in missing:
            print(f"[ERROR] no section called {name!r}")
        if not sections:
            return 1
    text = profile_text.render(sections)
    if public:
        problems = scan_text(text, source="public profile")
        if problems:
            print(f"[ERROR] possible personal data in the public text: {problems}")
            return 1
    print(text, end="")
    return 0


def _validate() -> int:
    try:
        profile = bootstrap.profile_repository().load()
    except ProfileError as exc:
        print(f"[ERROR] {exc}")
        return 1
    issues = check(profile)
    for issue in issues:
        print(f"[{issue.level.upper()}] {issue.where}: {issue.message}")
    try:
        drift = learning_drift(profile, bootstrap.learning_store().load())
    except LearningError as exc:
        drift = [f"learning data unreadable, so counts were not compared: {exc}"]
    for message in drift:
        print(f"[WARNING] {message}")
    errors = sum(1 for i in issues if i.level == "error")
    if errors:
        print(f"Profile has {errors} error(s).")
        return 1
    print(
        f"[OK] Profile valid: {len(profile.roles)} roles, {len(profile.certifications)} "
        f"certifications, {len(profile.projects)} projects, {len(profile.stories)} stories"
        + (f", {len(issues) + len(drift)} warning(s)" if issues or drift else "")
    )
    return 0


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
