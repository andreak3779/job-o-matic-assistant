"""The applications module with the log in its usual place (the vault's JSONL file).

Every function here is the matching use case in ``service`` with the log wired in, so callers
(CLI, MCP server, generator scripts) keep one simple, path-based interface. Tests and other
callers pass ``path=`` to use a log somewhere else.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from jobomatic import paths
from jobomatic.applications import service
from jobomatic.applications.adapters import csv_import
from jobomatic.applications.adapters.jsonl_log import open_log
from jobomatic.applications.model import Application, ImportReport, PostingCheck


def log_path() -> Path:
    """The applications log (override: CLAUDE_JOBS_APPLICATIONS_LOG)."""
    return paths.applications_log()


def read_events(path: Path | None = None) -> list[dict[str, Any]]:
    """Read every event; a malformed line raises ``ValueError`` naming the line."""
    return open_log(path).read_events()


def append_event(op: str, app_id: str, data: dict[str, Any], path: Path | None = None) -> None:
    service.append_event(open_log(path), op, app_id, data)


def load_applications(path: Path | None = None) -> list[Application]:
    return service.load_applications(open_log(path))


def create_application(
    company: str,
    title: str,
    *,
    status: str = "drafted",
    path: Path | None = None,
    day: str | None = None,
    **fields: Any,
) -> str:
    return service.create_application(
        open_log(path), company, title, status=status, day=day, **fields
    )


def update_application(app_id: str, path: Path | None = None, **fields: Any) -> None:
    service.update_application(open_log(path), app_id, **fields)


def get_application(app_id: str, path: Path | None = None) -> Application:
    return service.get_application(open_log(path), app_id)


def mark_applied(
    app_id: str, applied_on: str | None = None, path: Path | None = None
) -> Application:
    """Explicitly record that the application was submitted (the only way to 'applied')."""
    return service.mark_applied(open_log(path), app_id, applied_on)


def set_status(
    app_id: str,
    status: str,
    *,
    next_step: str | None = None,
    notes: str | None = None,
    path: Path | None = None,
) -> Application:
    return service.set_status(open_log(path), app_id, status, next_step=next_step, notes=notes)


def check_posting(
    company: str,
    title: str,
    job_id: str | None = None,
    *,
    applications: list[Application] | None = None,
    today: date | None = None,
    path: Path | None = None,
) -> PostingCheck:
    return service.check_posting(
        open_log(path),
        company,
        title,
        job_id,
        applications=applications,
        today=today,
    )


def check_jd_text(
    jd_text: str, *, path: Path | None = None, today: date | None = None
) -> PostingCheck:
    return service.check_jd_text(open_log(path), jd_text, today=today)


def find_for_jd(jd_text: str, path: Path | None = None) -> Application | None:
    return service.find_for_jd(open_log(path), jd_text)


def record_draft(
    jd_text: str,
    *,
    documents: tuple[str, ...] = (),
    fit_rating: str | None = None,
    company_fallback: str | None = None,
    path: Path | None = None,
    day: str | None = None,
) -> str | None:
    return service.record_draft(
        open_log(path),
        jd_text,
        documents=documents,
        fit_rating=fit_rating,
        company_fallback=company_fallback,
        day=day,
    )


def import_csv(csv_path: Path, *, dry_run: bool = False, path: Path | None = None) -> ImportReport:
    """Import a tracker export. Idempotent: rows already in the log are skipped."""
    return csv_import.import_csv(open_log(path), csv_path, dry_run=dry_run)
