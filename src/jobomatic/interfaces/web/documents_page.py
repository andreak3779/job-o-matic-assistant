"""The documents page: a tailored resume and cover letter for a posting (ADR 0025).

The same commands the MCP tool ``generate_application_documents`` calls, so the gate, the page budget
and the duplicate and pay checks apply exactly as they do there. A refusal shows its reason and, only
when the result names an override, one unticked box that says what is being overridden. A skills Pass
or a location Pass has no override, so it has no box, and nothing in a request can clear it. Files are
offered for download only if the result lists them as written.
"""

from __future__ import annotations

from typing import Any

from flask import Flask, current_app, render_template, request

from jobomatic import gate
from jobomatic.commands import cover_letter, resume
from jobomatic.commands.support import Confirmations
from jobomatic.interfaces.web.downloads import Downloads
from jobomatic.interfaces.web.views import Shown, show
from jobomatic.results import CommandResult

# The override a refusal names -> the confirmation it sets, and the sentence beside its box.
OVERRIDES = {
    gate.CONFIRM_GAPS: (
        "gaps",
        "I know this posting rates below Good on skills, and I want the documents anyway.",
    ),
    gate.CONFIRM_REAPPLY: (
        "reapply",
        "I know I already applied to this posting, and I want new documents anyway.",
    ),
    gate.CONFIRM_BELOW_MINIMUM: (
        "below_minimum",
        "I know the posted pay is below my minimum, and I want the documents anyway.",
    ),
}
# What can be downloaded: the documents themselves, not the provenance files written beside them.
DOWNLOADABLE = {".docx": "Word document"}


def _downloads() -> Downloads:
    downloads: Downloads = current_app.extensions["downloads"]
    return downloads


def _confirmed(form) -> tuple[str, ...]:  # type: ignore[no-untyped-def]
    """The overrides the person has ticked in this request, only those the gate knows."""
    return tuple(name for name in OVERRIDES if form.get(name) == "on")


def _confirmations(names: tuple[str, ...]) -> Confirmations:
    return Confirmations(**{OVERRIDES[name][0]: True for name in names})


def _offer(result: CommandResult, label: str) -> list[dict[str, str]]:  # type: ignore[type-arg]
    """One download per written document, each by an id the server issues."""
    return [
        {
            "label": f"{label} ({DOWNLOADABLE[path.suffix.lower()]})",
            "name": path.name,
            "id": _downloads().issue(path),
        }
        for path in result.written
        if path.suffix.lower() in DOWNLOADABLE
    ]


def register(app: Flask) -> None:
    @app.get("/documents")
    def documents_page() -> str:
        return _page(posting="")

    @app.post("/documents")
    def documents_generate():  # type: ignore[no-untyped-def]
        posting = request.form.get("posting", "")
        if not posting.strip():
            return _page(posting="", problem="Paste a posting first."), 400
        confirmed = _confirmed(request.form)
        confirm = _confirmations(confirmed)
        resume_result = resume.run(posting, confirm=confirm)
        steps: list[tuple[str, Shown]] = [("Resume", show(resume_result))]
        downloads = _offer(resume_result, "Resume")
        stopped = steps[0][1]
        if resume_result.status == "ok":
            letter_result = cover_letter.run(posting, confirm=confirm)
            steps.append(("Cover letter", show(letter_result)))
            downloads += _offer(letter_result, "Cover letter")
            stopped = steps[-1][1]
        # An override is offered only when the last refusal names one that is not already given.
        asked = stopped.override if stopped.refused and stopped.override in OVERRIDES else None
        return _page(
            posting=posting,
            steps=steps,
            downloads=downloads,
            asked=asked,
            confirmed=confirmed,
        )


def _page(**fields: Any) -> str:
    fields.setdefault("problem", None)
    fields.setdefault("steps", [])
    fields.setdefault("downloads", [])
    fields.setdefault("asked", None)
    fields.setdefault("confirmed", ())
    return render_template("documents.html", overrides=OVERRIDES, **fields)
