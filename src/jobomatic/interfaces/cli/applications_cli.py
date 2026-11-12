"""``applications`` and ``constraints`` subcommands for the ``jobo`` command line.

Kept out of ``src/jobomatic/interfaces/cli/main.py`` so that file stays a thin dispatcher; it calls
``register`` while building its parser and ``run`` to dispatch.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from jobomatic import applications as apps
from jobomatic import paths
from jobomatic.commands import applications as app_commands
from jobomatic.commands import constraints as constraints_command
from jobomatic.fit.parser import looks_unknown, parse_jd
from jobomatic.results import emit

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
        raise ValueError(paths.not_found_message(path, "Job description file"))
    return path.read_text(encoding="utf-8")


def _check(jd: Path, strict: bool) -> int:
    result = app_commands.check(_read_jd(jd))
    code = emit(result, app_commands.render_check)
    blocking = result.data is not None and result.data.check.blocking
    return 2 if strict and blocking else code


def _applied(
    app_id: str | None, jd: Path | None, date: str | None, platform: str | None, url: str | None
) -> int:
    jd_text = _read_jd(jd) if app_id is None and jd is not None else None
    result = app_commands.applied(
        application_id=app_id, jd_text=jd_text, date=date, platform=platform, url=url
    )
    return emit(result, app_commands.render_applied)


def _status(app_id: str, status: str, next_step: str | None, note: str | None) -> int:
    result = app_commands.set_status(app_id, status, next_step=next_step, note=note)
    return emit(result, app_commands.render_status)


def _list(status: str | None, company: str | None) -> int:
    result = app_commands.list_applications(status=status, company=company)
    return emit(result, app_commands.render_list)


def _constraints_show() -> int:
    return emit(constraints_command.show(), constraints_command.render)


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


def _import(csv_path: Path, dry_run: bool) -> int:
    if not csv_path.is_file():
        raise ValueError(paths.not_found_message(csv_path, "CSV file"))
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
