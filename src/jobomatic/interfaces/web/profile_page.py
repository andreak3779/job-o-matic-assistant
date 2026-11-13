"""The profile page: validate the profile and see what is wrong (ADR 0025).

The command the MCP tool ``validate_profile`` calls. It reads the profile and writes nothing.
"""

from __future__ import annotations

from flask import Flask, render_template

from jobomatic.commands import profile
from jobomatic.interfaces.web.views import show


def register(app: Flask) -> None:
    @app.get("/profile")
    def profile_page() -> str:
        return render_template("profile.html", checked=None)

    @app.post("/profile")
    def profile_check_page() -> str:
        return render_template("profile.html", checked=show(profile.validate()))
