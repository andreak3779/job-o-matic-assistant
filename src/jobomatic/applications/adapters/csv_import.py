"""Import an application tracker exported as CSV (a spreadsheet) into the log."""

from __future__ import annotations

import csv
from pathlib import Path

from jobomatic.applications.model import (
    Application,
    ImportReport,
    is_same_posting,
    now,
    parse_date,
    parse_status,
)
from jobomatic.applications.ports import ApplicationLog
from jobomatic.applications.service import create_application, load_applications

_HEADER_ALIASES = {
    "company": ("company", "employer", "organization", "organisation"),
    "title": ("role", "title", "position", "job title", "job"),
    "platform": ("platform", "source", "site", "board", "where"),
    "applied_on": ("date applied", "applied", "applied on", "date", "application date"),
    "status": ("status", "stage"),
    "next_step": ("next step", "next steps", "next", "follow up", "follow-up"),
    "url": ("url", "link", "posting", "posting url"),
    "job_id": ("job id", "req", "req id", "requisition", "job number", "reference"),
    "notes": ("notes", "comments", "comment"),
}


def _column_map(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for header in headers:
        key = header.strip().lower()
        for target, aliases in _HEADER_ALIASES.items():
            if key in aliases and target not in mapping.values():
                mapping[header] = target
    return mapping


def import_csv(log: ApplicationLog, csv_path: Path, *, dry_run: bool = False) -> ImportReport:
    """Import a tracker export. Idempotent: rows already in the log are skipped.

    Rows are never guessed at: an unreadable date, status or missing company/role is
    reported against its row number and skipped. Rows that carry a submitted status
    are the user's own tracker data, so importing them as ``applied`` is explicit.
    """
    report = ImportReport()
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{csv_path.name} has no header row")
        columns = _column_map(list(reader.fieldnames))
        wanted = set(columns.values())
        if not {"company", "title"} <= wanted:
            raise ValueError(
                f"{csv_path.name} needs a Company column and a Role/Title column "
                f"(found: {list(reader.fieldnames)})"
            )
        apps = load_applications(log)
        for row_number, row in enumerate(reader, start=2):
            values = {columns[h]: (v or "").strip() for h, v in row.items() if h in columns}
            label = f"row {row_number}"
            if not values.get("company") or not values.get("title"):
                if any(values.values()):
                    report.errors.append(f"{label}: missing company or role")
                continue
            try:
                status = parse_status(values["status"]) if values.get("status") else None
                applied_on = parse_date(values["applied_on"]) if values.get("applied_on") else None
            except ValueError as exc:
                report.errors.append(f"{label} ({values['company']}): {exc}")
                continue
            if status is None:
                status = "applied" if applied_on else "drafted"
            job_id = values.get("job_id") or None
            if any(is_same_posting(a, values["company"], values["title"], job_id) for a in apps):
                report.skipped_existing.append(f"{label}: {values['company']} — {values['title']}")
                continue
            fields = {
                k: v
                for k, v in {
                    "job_id": job_id,
                    "url": values.get("url") or None,
                    "platform": values.get("platform") or None,
                    "applied_on": applied_on,
                    "next_step": values.get("next_step") or None,
                    "notes": values.get("notes") or None,
                    "source": "csv-import",
                }.items()
                if v is not None
            }
            summary = f"{label}: {values['company']} — {values['title']} [{status}]"
            stamp = now()
            if dry_run:
                app_id = "(dry run)"
            else:
                app_id = create_application(
                    log, values["company"], values["title"], status=status, **fields
                )
                summary += f" id {app_id}"
            report.created.append(summary)
            # Track what this import has added so a repeated row is caught as a duplicate.
            apps.append(
                Application(
                    id=app_id,
                    company=values["company"],
                    title=values["title"],
                    status=status,
                    created=stamp[:10],
                    updated=stamp,
                    job_id=job_id,
                    applied_on=applied_on,
                )
            )
    return report
