"""``applications`` and ``constraints`` subcommands for the claude-jobs CLI.

Kept out of ``src/jobomatic/interfaces/cli/main.py`` so that file stays a thin dispatcher; it calls
``register`` while building its parser and ``run`` to dispatch.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from jobomatic import applications as apps
from jobomatic.fit.constraints import MISSING_MESSAGE, constraints_path, load_constraints
from jobomatic.fit.parser import looks_unknown, parse_jd

COMMANDS = ("applications", "constraints")


def register(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    app = subparsers.add_parser("applications", help="Applications log (what was applied to)")
    sub = app.add_subparsers(dest="applications_command", required=True)

    check = sub.add_parser("check", help="Look a job description up in the log (duplicate check)")
    check.add_argument("jd", type=Path)
    check.add_argument(
        "--strict", action="store_true", help="Exit 2 if the posting was applied to recently"
    )

    add = sub.add_parser("add", help="Add a posting to the log as 'drafted'")
    add.add_argument("jd", type=Path)
    add.add_argument("--platform")
    add.add_argument("--url")

    applied = sub.add_parser(
        "applied", help="Record that you submitted an application (explicit — never automatic)"
    )
    target = applied.add_mutually_exclusive_group(required=True)
    target.add_argument("--id", dest="app_id", help="Application id from 'applications list'")
    target.add_argument("--jd", type=Path, help="Job description of the posting you applied to")
    applied.add_argument("--date", help="Date submitted, YYYY-MM-DD (default: today)")
    applied.add_argument("--platform")
    applied.add_argument("--url")

    status = sub.add_parser("status", help="Move an application to a new status")
    status.add_argument("app_id")
    status.add_argument("status", choices=apps.STATUSES)
    status.add_argument("--next-step")
    status.add_argument("--note")

    listing = sub.add_parser("list", help="List applications")
    listing.add_argument("--status", choices=apps.STATUSES)
    listing.add_argument("--company")

    imp = sub.add_parser("import-csv", help="Import a spreadsheet tracker exported as CSV")
    imp.add_argument("csv", type=Path)
    imp.add_argument("--dry-run", action="store_true", help="Show what would be imported")

    constraints = subparsers.add_parser(
        "constraints", help="Show your private job-search constraints (salary minimums)"
    )
    csub = constraints.add_subparsers(dest="constraints_command", required=True)
    csub.add_parser("show", help="Print the minimums, or say they are not configured")


def _read_jd(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"job description file not found: {path}")
    return path.read_text(encoding="utf-8")


def _table(rows: list[apps.Application]) -> str:
    if not rows:
        return "No applications."
    lines = ["| id | company | role | status | applied | next step |", "|---|---|---|---|---|---|"]
    for a in rows:
        lines.append(
            f"| {a.id} | {a.company} | {a.title} | {a.status} | {a.applied_on or ''} "
            f"| {a.next_step or ''} |"
        )
    return "\n".join(lines)


def _check(jd: Path, strict: bool) -> int:
    parsed = parse_jd(_read_jd(jd))
    check = apps.check_posting(parsed.company, parsed.title, parsed.job_id)
    print(f"## Applications check — {parsed.title} at {parsed.company}\n")
    print(check.summary())
    for note in check.notes:
        print(f"- ⚠️ {note}")
    if check.verdict == "related":
        print("\n" + _table(list(check.related)))
    return 2 if strict and check.blocking else 0


def _add(jd: Path, platform: str | None, url: str | None) -> int:
    text = _read_jd(jd)
    parsed = parse_jd(text)
    if looks_unknown(parsed.company):
        raise ValueError("could not read a company name from the job description")
    existing = apps.find_for_jd(text)
    if existing:
        print(
            f"Already in the log: {existing.company} — {existing.title} (id {existing.id}, {existing.status})"
        )
        return 0
    fields: dict[str, Any] = {
        k: v for k, v in {"platform": platform, "url": url, "job_id": parsed.job_id}.items() if v
    }
    app_id = apps.create_application(parsed.company, parsed.title, source="manual", **fields)
    print(f"Added as drafted: {parsed.company} — {parsed.title} (id {app_id})")
    return 0


def _applied(
    app_id: str | None, jd: Path | None, date: str | None, platform: str | None, url: str | None
) -> int:
    if app_id is None:
        assert jd is not None
        text = _read_jd(jd)
        parsed = parse_jd(text)
        existing = apps.find_for_jd(text)
        if existing is None:
            if looks_unknown(parsed.company):
                raise ValueError("could not read a company name from the job description")
            app_id = apps.create_application(
                parsed.company, parsed.title, job_id=parsed.job_id, source="manual"
            )
        else:
            app_id = existing.id
    if platform or url:
        extra: dict[str, Any] = {k: v for k, v in {"platform": platform, "url": url}.items() if v}
        apps.update_application(app_id, **extra)
    done = apps.mark_applied(app_id, date)
    print(f"Marked applied on {done.applied_on}: {done.company} — {done.title} (id {done.id})")
    return 0


def _status(app_id: str, status: str, next_step: str | None, note: str | None) -> int:
    done = apps.set_status(app_id, status, next_step=next_step, notes=note)
    print(f"{done.company} — {done.title} (id {done.id}) is now {done.status}")
    return 0


def _list(status: str | None, company: str | None) -> int:
    rows = apps.load_applications()
    if status:
        rows = [a for a in rows if a.status == status]
    if company:
        rows = [a for a in rows if apps.same_company(a.company, company)]
    print(_table(rows))
    return 0


def _import(csv_path: Path, dry_run: bool) -> int:
    if not csv_path.is_file():
        raise ValueError(f"CSV file not found: {csv_path}")
    report = apps.import_csv(csv_path, dry_run=dry_run)
    verb = "Would import" if dry_run else "Imported"
    print(
        f"{verb} {len(report.created)} application(s); skipped {len(report.skipped_existing)} already in the log."
    )
    for line in report.created:
        print(f"  + {line}")
    for line in report.skipped_existing:
        print(f"  = {line} (already logged)")
    for line in report.errors:
        print(f"  ! {line}", file=sys.stderr)
    return 1 if report.errors else 0


def _constraints_show() -> int:
    constraints = load_constraints()
    if constraints is None:
        print(MISSING_MESSAGE)
        return 0
    print(f"Minimums ({constraints_path().name}): {constraints.describe()}")
    return 0


def run(args: argparse.Namespace) -> int:
    try:
        if args.command == "constraints":
            return _constraints_show()
        command = args.applications_command
        if command == "check":
            return _check(args.jd, args.strict)
        if command == "add":
            return _add(args.jd, args.platform, args.url)
        if command == "applied":
            return _applied(args.app_id, args.jd, args.date, args.platform, args.url)
        if command == "status":
            return _status(args.app_id, args.status, args.next_step, args.note)
        if command == "list":
            return _list(args.status, args.company)
        if command == "import-csv":
            return _import(args.csv, args.dry_run)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    raise AssertionError(f"unhandled applications command: {command}")  # pragma: no cover
