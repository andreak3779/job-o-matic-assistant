"""The applications page: the list, and the way to change a status (ADR 0025).

The same commands the MCP tools ``applications_list``, ``applications_set_status`` and
``applications_mark_applied`` call. The log is append-only, so a change shows the new state and never
edits an old entry. "Applied" is never set by a status control (ADR 0010): it is its own action, with
a confirmation that names the posting.
"""

from __future__ import annotations

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from werkzeug.wrappers import Response as BaseResponse

from jobomatic.applications.model import STATUSES
from jobomatic.commands import applications
from jobomatic.interfaces.web.views import show

# What a row's control may set. "applied" is left out on purpose; "drafted" is where an entry starts.
SETTABLE = tuple(s for s in STATUSES if s not in ("applied", "drafted"))


def _rows(status: str | None, company: str | None):  # type: ignore[no-untyped-def]
    return show(applications.list_applications(status=status or None, company=company or None))


def _find(application_id: str):  # type: ignore[no-untyped-def]
    for row in applications.list_applications().data.rows:  # type: ignore[union-attr]
        if row.id == application_id:
            return row
    return None


def register(app: Flask) -> None:
    @app.get("/applications")
    def applications_page() -> str:
        status = request.args.get("status", "")
        company = request.args.get("company", "")
        return render_template(
            "applications.html",
            listed=_rows(status, company),
            status=status,
            company=company,
            statuses=STATUSES,
            settable=SETTABLE,
        )

    @app.post("/applications/<application_id>/status")
    def application_status(application_id: str):  # type: ignore[no-untyped-def]
        status = request.form.get("status", "")
        if status not in SETTABLE:
            return _refuse(
                "Pick one of the statuses in the list. Use “Mark applied” to record a submission."
            )
        result = applications.set_status(
            application_id,
            status,
            next_step=request.form.get("next_step") or None,
            note=request.form.get("note") or None,
        )
        done = show(result)
        if not done.ok:
            return _refuse(
                " ".join(m.text for m in done.alerts + done.info) or "Could not change the status."
            )
        if request.headers.get("HX-Request"):
            return render_template(
                "_application_row.html", row=result.data, settable=SETTABLE, statuses=STATUSES
            )
        flash(applications.render_status(result.data))  # type: ignore[arg-type]
        return redirect(url_for("applications_page"))

    @app.get("/applications/<application_id>/applied")
    def application_applied_confirm(application_id: str) -> str:
        row = _find(application_id)
        if row is None:
            abort(404)
        return render_template("applied_confirm.html", row=row)

    @app.post("/applications/<application_id>/applied")
    def application_applied(application_id: str) -> BaseResponse:
        if _find(application_id) is None:
            abort(404)
        result = applications.applied(application_id=application_id)
        done = show(result)
        if done.ok and result.data is not None:
            flash(applications.render_applied(result.data))
        else:
            flash("Could not mark it applied: " + " ".join(m.text for m in done.alerts + done.info))
        return redirect(url_for("applications_page"))


def _refuse(text: str):  # type: ignore[no-untyped-def]
    return render_template("applications_problem.html", text=text), 400
