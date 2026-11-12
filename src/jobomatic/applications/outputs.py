"""Where the documents for a job posting go, and the application-log entry that goes with them.

Every generator that works from a job description calls ``locate_application`` and gets that
application's folder (ADR 0015). The path is built in ``jobomatic.paths``; the application id is
built in ``jobomatic.applications``.

Whether a document is logged follows ADR 0010. Documents you make in order to apply (resume,
cover letter, job-site letter) log the posting as ``drafted``, never ``applied``. Documents that
are exploratory (gap analysis) or only make sense once an application exists (interview prep,
thank-you letter) reuse the entry if there is one and never create one.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from jobomatic import applications, paths
from jobomatic.fit.parser import looks_unknown, parse_jd

JD_FILE = "jd.md"


@dataclass(frozen=True)
class Located:
    """An application's output folder.

    ``app_id`` is the log entry the folder belongs to, or ``None`` when there is none.
    ``logged`` is true when this call wrote to the log.
    """

    app_id: str | None
    folder: Path
    logged: bool = False


def locate_application(
    jd_text: str,
    *,
    log: bool,
    documents: tuple[str, ...] = (),
    fit_rating: str | None = None,
    company: str | None = None,
    create_folder: bool = True,
) -> Located:
    """Find the folder for this posting's documents, logging the posting if ``log`` is true.

    A failure to write the log must not lose the document being generated, so it is reported
    on stderr and the document goes to a folder named from today's date and the posting.
    ``create_folder=False`` leaves the disk alone: use it when the caller was given an
    explicit output path and only the log entry is wanted.
    """
    parsed = parse_jd(jd_text)
    known = company or (None if looks_unknown(parsed.company) else parsed.company)
    adopted = _unlogged_folder(known, parsed.title)

    app_id: str | None = None
    logged = False
    try:
        if log:
            app_id = applications.record_draft(
                jd_text,
                documents=documents,
                fit_rating=fit_rating,
                company_fallback=company,
                day=adopted.name[:10] if adopted else None,
            )
            logged = app_id is not None
        else:
            existing = applications.find_for_jd(jd_text)
            app_id = existing.id if existing else None
    except (OSError, ValueError) as exc:
        print(f"WARNING: could not read or write the applications log: {exc}", file=sys.stderr)

    if app_id:
        name = applications.folder_name_for(applications.get_application(app_id))
        folder = paths.output_dir("application", name=name)
    elif adopted is not None:
        folder = adopted
    else:
        folder = paths.output_dir(
            "application",
            day=date.today(),
            company=known or "unknown-company",
            role=parsed.title,
        )
    if create_folder:
        folder.mkdir(parents=True, exist_ok=True)
        saved = folder / JD_FILE
        if not saved.exists():  # keep the posting as it was when first seen
            saved.write_text(jd_text, encoding="utf-8")
    return Located(app_id, folder, logged)


def _unlogged_folder(company: str | None, title: str) -> Path | None:
    """An earlier folder for the same company and role that has no log entry yet.

    A gap analysis creates its folder before any entry exists. When the resume later creates the
    entry, it takes that folder's date, so the posting still has exactly one folder.
    """
    if not company:
        return None
    base = paths.output_dir("application", name="x").parent
    if not base.is_dir():
        return None
    tail = "_".join([paths.slug(company), paths.slug(title)])
    matches = sorted(d for d in base.iterdir() if d.is_dir() and d.name[11:] == tail)
    return matches[0] if matches else None


def logged_note(located: Located) -> str | None:
    """The line saying which log entry a document was filed under, when this call wrote one."""
    if located.logged and located.app_id:
        return f"Logged as drafted (not applied): application {located.app_id}"
    return None


def report(located: Located) -> None:
    """Print ``logged_note`` (for the commands that have not moved to structured results)."""
    note = logged_note(located)
    if note:
        print(note)
