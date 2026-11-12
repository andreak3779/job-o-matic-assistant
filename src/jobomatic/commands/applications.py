"""The applications log: check a posting, list, mark applied, change a status (ADR 0028).

Each function takes plain values (a posting as text, an id) and returns a ``CommandResult`` with a
typed payload; a ``render_*`` function turns the payload into the text the command line prints and
the MCP tools return. Nothing here prints or reads a file. The log is append-only, so the writes
(``applied`` and ``set_status``) add an event and never edit an old entry (ADR 0010).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jobomatic import applications as apps
from jobomatic.commands.support import vault_write_lock
from jobomatic.fit.parser import looks_unknown, parse_jd
from jobomatic.results import CommandResult, guarded, ok


@dataclass(frozen=True)
class CheckData:
    title: str
    company: str
    check: apps.PostingCheck


@dataclass(frozen=True)
class ApplicationList:
    rows: tuple[apps.Application, ...]


def table(rows: list[apps.Application] | tuple[apps.Application, ...]) -> str:
    if not rows:
        return "No applications."
    lines = ["| id | company | role | status | applied | next step |", "|---|---|---|---|---|---|"]
    for a in rows:
        lines.append(
            f"| {a.id} | {a.company} | {a.title} | {a.status} | {a.applied_on or ''} "
            f"| {a.next_step or ''} |"
        )
    return "\n".join(lines)


def _known_status(status: str) -> str:
    """The command line's ``choices`` check, for callers that do not go through ``argparse``."""
    if status not in apps.STATUSES:
        raise ValueError(f"unknown status {status!r}; expected one of {', '.join(apps.STATUSES)}")
    return status


# -- check a posting ---------------------------------------------------------------------------


def check(jd_text: str) -> CommandResult[CheckData]:
    """Look the posting up in the log (the duplicate check). It never writes."""
    return guarded(lambda: _check(jd_text))


def _check(jd_text: str) -> CommandResult[CheckData]:
    parsed = parse_jd(jd_text)
    found = apps.check_posting(parsed.company, parsed.title, parsed.job_id)
    return ok(CheckData(parsed.title, parsed.company, found))


def render_check(data: CheckData) -> str:
    found = data.check
    text = f"## Applications check — {data.title} at {data.company}\n\n{found.summary()}"
    for note in found.notes:
        text += f"\n- ⚠️ {note}"
    if found.verdict == "related":
        text += "\n\n" + table(list(found.related))
    return text


# -- list --------------------------------------------------------------------------------------


def list_applications(
    *, status: str | None = None, company: str | None = None
) -> CommandResult[ApplicationList]:
    return guarded(lambda: _list(status, company))


def _list(status: str | None, company: str | None) -> CommandResult[ApplicationList]:
    rows = apps.load_applications()
    if status:
        status = _known_status(status)
        rows = [a for a in rows if a.status == status]
    if company:
        rows = [a for a in rows if apps.same_company(a.company, company)]
    return ok(ApplicationList(tuple(rows)))


def render_list(data: ApplicationList) -> str:
    return table(data.rows)


# -- mark applied ------------------------------------------------------------------------------


def applied(
    *,
    application_id: str | None = None,
    jd_text: str | None = None,
    date: str | None = None,
    platform: str | None = None,
    url: str | None = None,
) -> CommandResult[apps.Application]:
    """Record that the user submitted an application. It is only ever set on purpose (ADR 0010):
    give the id of an entry, or the posting (the entry is created if it was never drafted)."""
    return guarded(lambda: _applied(application_id, jd_text, date, platform, url))


def _applied(
    application_id: str | None,
    jd_text: str | None,
    date: str | None,
    platform: str | None,
    url: str | None,
) -> CommandResult[apps.Application]:
    with vault_write_lock():
        if application_id is None:
            if jd_text is None:
                raise ValueError("give an application id or a job description")
            parsed = parse_jd(jd_text)
            existing = apps.find_for_jd(jd_text)
            if existing is None:
                if looks_unknown(parsed.company):
                    raise ValueError("could not read a company name from the job description")
                application_id = apps.create_application(
                    parsed.company, parsed.title, job_id=parsed.job_id, source="manual"
                )
            else:
                application_id = existing.id
        extra: dict[str, Any] = {k: v for k, v in {"platform": platform, "url": url}.items() if v}
        if extra:
            apps.update_application(application_id, **extra)
        return ok(apps.mark_applied(application_id, date))


def render_applied(done: apps.Application) -> str:
    return f"Marked applied on {done.applied_on}: {done.company} — {done.title} (id {done.id})"


# -- change a status ---------------------------------------------------------------------------


def set_status(
    application_id: str, status: str, *, next_step: str | None = None, note: str | None = None
) -> CommandResult[apps.Application]:
    return guarded(lambda: _set_status(application_id, status, next_step, note))


def _set_status(
    application_id: str, status: str, next_step: str | None, note: str | None
) -> CommandResult[apps.Application]:
    _known_status(status)
    with vault_write_lock():
        return ok(apps.set_status(application_id, status, next_step=next_step, notes=note))


def render_status(done: apps.Application) -> str:
    return f"{done.company} — {done.title} (id {done.id}) is now {done.status}"
