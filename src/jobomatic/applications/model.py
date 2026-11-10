"""Applications: which postings were drafted for and applied to, and what happened (ADR 0010).

The pure part of the module: the application record, the event fold, and the rules for telling
whether two postings are the same one. No file access here; the log is reached through a port
(``ports.ApplicationLog``) by ``service``.

Status model — the one rule that matters: **a document being generated is not an application
being submitted.** Generators only ever record ``drafted``; moving to ``applied`` (or anything
later) happens only through an explicit call the user asked for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from jobomatic import paths
from jobomatic.fit.parser import looks_unknown

STATUSES = ("drafted", "applied", "phone_screen", "technical", "offer", "rejected", "withdrawn")
# Everything past "drafted" means the application was actually submitted.
SUBMITTED_STATUSES = frozenset(STATUSES[1:])
DUPLICATE_WINDOW_DAYS = 60
# This many submitted applications to one company that never progressed past
# "applied" is the "repeat cold applications with no response" pattern.
NO_RESPONSE_PATTERN_COUNT = 2

FIELDS = (
    "company",
    "title",
    "job_id",
    "url",
    "platform",
    "status",
    "applied_on",
    "fit_rating",
    "documents",
    "next_step",
    "notes",
    "source",
)


@dataclass(frozen=True)
class Application:
    id: str
    company: str
    title: str
    status: str
    created: str
    updated: str
    job_id: str | None = None
    url: str | None = None
    platform: str | None = None
    applied_on: str | None = None
    fit_rating: str | None = None
    documents: tuple[str, ...] = ()
    next_step: str | None = None
    notes: str | None = None
    source: str | None = None

    @property
    def submitted(self) -> bool:
        return self.status in SUBMITTED_STATUSES

    def anchor_date(self) -> date | None:
        """When it was submitted (or, if unknown, last touched)."""
        raw = self.applied_on or self.updated[:10]
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def event_problem(event: Any) -> str | None:
    """Why ``event`` is not a valid log event, or ``None`` when it is."""
    if (
        not isinstance(event, dict)
        or event.get("op") not in ("create", "update")
        or not isinstance(event.get("id"), str)
        or not isinstance(event.get("ts"), str)
        or not isinstance(event.get("data"), dict)
    ):
        return "is not a valid event (needs op create|update, id, ts and data)"
    unknown = sorted(set(event["data"]) - set(FIELDS))
    if unknown:
        return f"has unknown field(s) {unknown}"
    return None


def fold_events(events: list[dict[str, Any]]) -> dict[str, Application]:
    state: dict[str, dict[str, Any]] = {}
    # Stable sort: same-timestamp events keep file order.
    for event in sorted(events, key=lambda e: e["ts"]):
        app_id, data = event["id"], event["data"]
        if event["op"] == "create":
            state.setdefault(
                app_id, {"id": app_id, "created": event["ts"][:10], "documents": []}
            ).update(without_none(data))
        elif app_id in state:  # an update for an unknown id (lost create) is ignored
            current = state[app_id]
            docs = list(dict.fromkeys([*current["documents"], *data.get("documents", ())]))
            current.update({k: v for k, v in data.items() if k != "documents"})
            current["documents"] = docs
        else:
            continue
        state[app_id]["updated"] = event["ts"]
    result: dict[str, Application] = {}
    for app_id, raw in state.items():
        raw["documents"] = tuple(raw.get("documents", ()))
        raw.setdefault("company", "")
        raw.setdefault("title", "")
        raw.setdefault("status", "drafted")
        result[app_id] = Application(**raw)
    return result


def without_none(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if v is not None}


def validate_data(data: dict[str, Any]) -> None:
    unknown = sorted(set(data) - set(FIELDS))
    if unknown:
        raise ValueError(f"unknown application field(s) {unknown}")
    status = data.get("status")
    if status is not None and status not in STATUSES:
        raise ValueError(f"status must be one of {list(STATUSES)}, got {status!r}")
    applied_on = data.get("applied_on")
    if applied_on is not None:
        try:
            date.fromisoformat(applied_on)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"applied_on must be an ISO date (YYYY-MM-DD), got {applied_on!r}"
            ) from exc


def folder_name_for(app: Application) -> str:
    """The name of the folder holding this application's documents.

    The id itself for applications created since ids became readable; for older ones with a
    random id, the same name built from when it was created, its company and its title.
    """
    if paths.is_dated_name(app.id):
        return app.id
    return paths.folder_name(app.created, app.company, app.title)


# ── matching a posting to the log ────────────────────────────────────────────

_LEGAL_SUFFIXES = {
    "inc",
    "incorporated",
    "ltd",
    "limited",
    "llc",
    "corp",
    "corporation",
    "co",
    "plc",
}


def company_key(name: str) -> str:
    words = re.sub(r"[^a-z0-9 ]+", " ", name.lower()).split()
    return " ".join(w for w in words if w not in _LEGAL_SUFFIXES)


def title_tokens(title: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9#+. ]+", " ", title.lower()).split())


def normalize_id(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def same_company(a: str, b: str) -> bool:
    ka, kb = company_key(a), company_key(b)
    return bool(ka) and ka == kb


def is_same_posting(app: Application, company: str, title: str, job_id: str | None) -> bool:
    """Same company, and the same job ID — or, with no IDs to compare, the same title.

    Unknown company/title placeholders never match: ``parse_jd`` returns
    "Unknown Company" for a posting it could not read, and treating every such
    posting as the same one would block unrelated applications.
    """
    if (
        looks_unknown(company)
        or looks_unknown(app.company)
        or not same_company(app.company, company)
    ):
        return False
    a_id, b_id = normalize_id(app.job_id), normalize_id(job_id)
    if a_id and b_id:
        return a_id == b_id
    if looks_unknown(title) or looks_unknown(app.title):
        return False
    ta, tb = title_tokens(app.title), title_tokens(title)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.75


@dataclass(frozen=True)
class PostingCheck:
    """Result of looking a posting up in the log."""

    verdict: str  # new | related | drafted | repeat | duplicate
    match: Application | None = None
    related: tuple[Application, ...] = ()
    no_response_pattern: bool = False
    days_ago: int | None = None
    notes: tuple[str, ...] = field(default=())

    @property
    def blocking(self) -> bool:
        """True when the same posting was submitted inside the duplicate window."""
        return self.verdict == "duplicate"

    def summary(self) -> str:
        m = self.match
        if self.verdict == "duplicate" and m:
            return (
                f"DUPLICATE — already applied to this posting {self.days_ago} day(s) ago "
                f"({m.company}, {m.title}; status {m.status}; id {m.id})."
            )
        if self.verdict == "repeat" and m:
            return (
                f"REPEAT — this posting was applied to {self.days_ago} day(s) ago, outside the "
                f"{DUPLICATE_WINDOW_DAYS}-day window ({m.company}, {m.title}; status {m.status}; "
                f"id {m.id}). Confirm it is a genuinely new posting."
            )
        if self.verdict == "drafted" and m:
            return (
                f"DRAFTED — documents were already generated for this posting but it is not "
                f"marked applied (id {m.id})."
            )
        if self.verdict == "related" and self.related:
            return (
                f"RELATED — {len(self.related)} other application(s) to {self.related[0].company}, "
                "none for this role."
            )
        return "NEW — no application to this posting in the log."


def check_in(
    apps: list[Application],
    company: str,
    title: str,
    job_id: str | None = None,
    *,
    today: date | None = None,
) -> PostingCheck:
    """Look a posting up in a list of applications (see ``PostingCheck.verdict``)."""
    today = today or date.today()
    same = [a for a in apps if is_same_posting(a, company, title, job_id)]
    company_apps = [
        a for a in apps if same_company(a.company, company) and not looks_unknown(company)
    ]
    notes: list[str] = []

    submitted_company = [a for a in company_apps if a.submitted]
    pattern = (
        sum(1 for a in submitted_company if a.status == "applied") >= NO_RESPONSE_PATTERN_COUNT
    )
    if pattern:
        notes.append(
            f"{company}: {NO_RESPONSE_PATTERN_COUNT}+ earlier applications with no response — "
            "consider a referral or recruiter contact instead of another cold application."
        )

    submitted_same = [a for a in same if a.submitted]
    if submitted_same:
        latest = max(submitted_same, key=lambda a: a.anchor_date() or date.min)
        anchor = latest.anchor_date()
        days = (today - anchor).days if anchor else None
        in_window = days is not None and days <= DUPLICATE_WINDOW_DAYS
        verdict = "duplicate" if in_window else "repeat"
        return PostingCheck(verdict, latest, tuple(company_apps), pattern, days, tuple(notes))
    if same:
        return PostingCheck("drafted", same[-1], tuple(company_apps), pattern, None, tuple(notes))
    others = tuple(a for a in company_apps)
    if others:
        return PostingCheck("related", None, others, pattern, None, tuple(notes))
    return PostingCheck("new", None, (), pattern, None, tuple(notes))


_STATUS_ALIASES = {
    "drafted": "drafted",
    "draft": "drafted",
    "applied": "applied",
    "submitted": "applied",
    "phone screen": "phone_screen",
    "phone screening": "phone_screen",
    "screen": "phone_screen",
    "technical": "technical",
    "technical interview": "technical",
    "offer": "offer",
    "rejected": "rejected",
    "declined": "rejected",
    "withdrawn": "withdrawn",
    "withdrew": "withdrawn",
}
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d %Y",
)


def parse_date(raw: str) -> str:
    """Parse a spreadsheet date to ISO. Ambiguous ``a/b/YYYY`` dates are an error, not a guess."""
    text = raw.strip()
    text = re.sub(r"[ T]\d{1,2}:\d{2}(:\d{2})?(\.\d+)?$", "", text)  # Excel "2026-04-21 00:00:00"
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    slash = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if slash:
        a, b, year = (int(g) for g in slash.groups())
        if a > 12 >= b:
            return date(year, b, a).isoformat()
        if b > 12 >= a:
            return date(year, a, b).isoformat()
        raise ValueError(f"ambiguous date {raw!r} (day/month or month/day) — use YYYY-MM-DD")
    raise ValueError(f"unrecognised date {raw!r} — use YYYY-MM-DD")


def parse_status(raw: str) -> str:
    key = re.sub(r"[\s_-]+", " ", raw.strip().lower())
    if key in _STATUS_ALIASES:
        return _STATUS_ALIASES[key]
    raise ValueError(
        f"unrecognised status {raw!r} (known: {sorted(set(_STATUS_ALIASES.values()))})"
    )


@dataclass
class ImportReport:
    created: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
