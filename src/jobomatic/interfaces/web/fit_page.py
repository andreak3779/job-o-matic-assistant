"""The fit page: paste a posting, see the rating and the duplicate check (ADR 0025).

The same two commands the MCP tools ``fit_check`` and ``applications_check`` call. Neither writes
anything, so there is nothing here to confirm.
"""

from __future__ import annotations

from flask import Flask, render_template, request

from jobomatic.commands import applications, fit_check
from jobomatic.interfaces.web.views import show

# What each match status means, in the words the fit table uses.
STATUS_WORDS = {
    "match": ("●", "Production"),
    "portfolio": ("◐", "Portfolio"),
    "course": ("○", "Course only"),
    "legacy": ("◔", "Legacy"),
    "gap": ("✕", "No evidence"),
}
RATING_CLASS = {
    "Strong": "strong",
    "Good": "good",
    "Worth a try": "worth",
    "Stretch": "stretch",
    "Pass": "pass",
}


def register(app: Flask) -> None:
    @app.get("/fit")
    def fit_page() -> str:
        return render_template("fit.html", posting="", fit=None, duplicate=None, problem=None)

    @app.post("/fit")
    def fit_check_page():  # type: ignore[no-untyped-def]
        posting = request.form.get("posting", "")
        if not posting.strip():
            page = render_template(
                "fit.html", posting="", fit=None, duplicate=None, problem="Paste a posting first."
            )
            return page, 400
        return render_template(
            "fit.html",
            posting=posting,
            fit=show(fit_check.run(posting)),
            duplicate=show(applications.check(posting)),
            problem=None,
            status_words=STATUS_WORDS,
            rating_class=RATING_CLASS,
        )
