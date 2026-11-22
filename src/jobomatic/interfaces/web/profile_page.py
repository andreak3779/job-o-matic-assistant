"""The profile page: validate the profile and see what is wrong (ADR 0025).

The command the MCP tool ``validate_profile`` calls. It reads the profile and writes nothing.
"""

from __future__ import annotations

from flask import Flask, current_app, redirect, render_template, url_for
from werkzeug.wrappers import Response as BaseResponse

from jobomatic.commands import profile
from jobomatic.interfaces.web.views import show


def register(app: Flask) -> None:
    @app.get("/profile")
    def profile_page() -> str:
        return render_template("profile.html", checked=None)

    @app.post("/profile")
    def profile_check_page() -> BaseResponse:
        held = current_app.extensions["results"].hold(
            "profile", {"checked": show(profile.validate())}
        )
        return redirect(url_for("profile_result", result_id=held), code=303)

    @app.get("/profile/result/<result_id>")
    def profile_result(result_id: str):  # type: ignore[no-untyped-def]
        context = current_app.extensions["results"].get("profile", result_id)
        if context is None:  # gone: show the form, and run the check again on the next click
            return redirect(url_for("profile_page"), code=303)
        return render_template("profile.html", **context)
