"""The applications use cases. They depend only on the log port, never on a file."""

from __future__ import annotations

from datetime import date
from typing import Any

from jobomatic import paths
from jobomatic.applications.model import (
    SUBMITTED_STATUSES,
    Application,
    PostingCheck,
    check_in,
    fold_events,
    is_same_posting,
    now,
    validate_data,
)
from jobomatic.applications.ports import ApplicationLog
from jobomatic.fit.parser import looks_unknown, parse_jd


def append_event(log: ApplicationLog, op: str, app_id: str, data: dict[str, Any]) -> None:
    """Append one event. Never rewrites existing lines."""
    validate_data(data)
    log.append({"ts": now(), "id": app_id, "op": op, "data": data})


def load_applications(log: ApplicationLog) -> list[Application]:
    """Current state of every application, oldest first."""
    return sorted(fold_events(log.read_events()).values(), key=lambda a: (a.created, a.id))


def create_application(
    log: ApplicationLog,
    company: str,
    title: str,
    *,
    status: str = "drafted",
    day: str | None = None,
    **fields: Any,
) -> str:
    """Create an application and return its id.

    The id is also the name of its output folder: ``2026-10-31_acme-health_net-developer``
    (ADR 0015). A second application with the same date, company and title gets ``-2``.
    ``day`` replaces today's date in the id, to adopt a folder that already exists.
    Applications logged before that scheme keep their random ids; see ``folder_name_for``.
    """
    existing = {a.id for a in load_applications(log)}
    base = paths.folder_name(day or now()[:10], company, title)
    app_id, n = base, 1
    while app_id in existing:
        n += 1
        app_id = f"{base}-{n}"
    append_event(
        log, "create", app_id, {"company": company, "title": title, "status": status, **fields}
    )
    return app_id


def update_application(log: ApplicationLog, app_id: str, **fields: Any) -> None:
    if app_id not in {a.id for a in load_applications(log)}:
        raise ValueError(f"no application with id {app_id!r}")
    append_event(log, "update", app_id, fields)


def get_application(log: ApplicationLog, app_id: str) -> Application:
    for app in load_applications(log):
        if app.id == app_id:
            return app
    raise ValueError(f"no application with id {app_id!r}")


def mark_applied(log: ApplicationLog, app_id: str, applied_on: str | None = None) -> Application:
    """Explicitly record that the application was submitted (the only way to 'applied')."""
    update_application(
        log, app_id, status="applied", applied_on=applied_on or date.today().isoformat()
    )
    return get_application(log, app_id)


def set_status(
    log: ApplicationLog,
    app_id: str,
    status: str,
    *,
    next_step: str | None = None,
    notes: str | None = None,
) -> Application:
    fields: dict[str, Any] = {"status": status}
    if next_step is not None:
        fields["next_step"] = next_step
    if notes is not None:
        fields["notes"] = notes
    if status in SUBMITTED_STATUSES and not get_application(log, app_id).applied_on:
        fields["applied_on"] = date.today().isoformat()
    update_application(log, app_id, **fields)
    return get_application(log, app_id)


def check_posting(
    log: ApplicationLog,
    company: str,
    title: str,
    job_id: str | None = None,
    *,
    applications: list[Application] | None = None,
    today: date | None = None,
) -> PostingCheck:
    """Look a posting up in the log (see ``PostingCheck.verdict``)."""
    apps = applications if applications is not None else load_applications(log)
    return check_in(apps, company, title, job_id, today=today)


def check_jd_text(log: ApplicationLog, jd_text: str, *, today: date | None = None) -> PostingCheck:
    parsed = parse_jd(jd_text)
    return check_posting(log, parsed.company, parsed.title, parsed.job_id, today=today)


def find_for_jd(log: ApplicationLog, jd_text: str) -> Application | None:
    """The existing application for this posting, preferring a submitted one."""
    parsed = parse_jd(jd_text)
    matches = [
        a
        for a in load_applications(log)
        if is_same_posting(a, parsed.company, parsed.title, parsed.job_id)
    ]
    if not matches:
        return None
    return max(matches, key=lambda a: (a.submitted, a.updated))


def record_draft(
    log: ApplicationLog,
    jd_text: str,
    *,
    documents: tuple[str, ...] = (),
    fit_rating: str | None = None,
    company_fallback: str | None = None,
    day: str | None = None,
) -> str | None:
    """Record that documents were generated for a posting — status ``drafted`` only.

    Adds the document kinds to an existing entry for the same posting, or creates a
    new ``drafted`` one. Returns the application id, or ``None`` when the posting's
    company cannot be read (nothing useful to record).
    """
    parsed = parse_jd(jd_text)
    company = parsed.company
    if looks_unknown(company) and company_fallback:
        company = company_fallback
    if looks_unknown(company):
        return None
    existing = find_for_jd(log, jd_text)
    if existing is None and company != parsed.company:
        existing = next(
            (
                a
                for a in load_applications(log)
                if is_same_posting(a, company, parsed.title, parsed.job_id)
            ),
            None,
        )
    if existing:
        fields: dict[str, Any] = {}
        if documents:
            fields["documents"] = list(documents)
        if fit_rating:
            fields["fit_rating"] = fit_rating
        if fields:
            update_application(log, existing.id, **fields)
        return existing.id
    return create_application(
        log,
        company,
        parsed.title,
        job_id=parsed.job_id,
        fit_rating=fit_rating,
        documents=list(documents),
        source="generated",
        day=day,
    )
