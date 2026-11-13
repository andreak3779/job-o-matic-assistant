"""The Flask application of the local web UI (ADR 0025).

``create_app`` builds the app; ``launch.serve`` runs it. A route parses a form, calls a command from
``jobomatic.commands`` and renders the ``CommandResult``; it holds no rules and reads no printed
text. Every template is escaped by Jinja, because pages show text that came from outside.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from pathlib import Path

from flask import Flask, abort, render_template, send_file, send_from_directory
from werkzeug.exceptions import HTTPException

from jobomatic.interfaces.web import fit_page, guards, profile_page
from jobomatic.interfaces.web.downloads import Downloads

BRANDING = Path(__file__).resolve().parents[2] / "branding"
# The only branding files a page may ask for, by name.
BRAND_FILES = frozenset({"tokens.css", "job-o-matic-icon.svg", "favicon.ico"})
MAX_REQUEST_BYTES = 2 * 1024 * 1024  # as the MCP server's import tool

ERROR_TEXT = {
    403: (
        "Not allowed",
        "This page only opens from the address printed in the terminal by `jobo web`, "
        "which works once. Start `jobo web` again if you closed that window.",
    ),
    404: ("Not found", "There is nothing at this address."),
    413: ("Too large", "That is more than this page accepts (2 MB). Use a smaller file."),
    500: ("Something went wrong", "The page could not be made. The terminal has the details."),
}


@dataclass(frozen=True)
class Page:
    """A page the header links to."""

    endpoint: str
    label: str


PAGES = (
    Page("fit_page", "Fit check"),
    Page("profile_page", "Profile check"),
)


def create_app(*, launch_token: str, pages: tuple[Page, ...] = PAGES) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=secrets.token_bytes(32),  # new for every launch, so no session outlives it
        MAX_CONTENT_LENGTH=MAX_REQUEST_BYTES,
        LAUNCH_TOKEN=launch_token,
        LAUNCH_USED=False,
        LAUNCH_LOCK=threading.Lock(),
        ALLOWED_HOSTS=frozenset(),  # set by launch once the port is known
        PAGES=pages,
        DEBUG=False,
        TESTING=False,
    )
    app.extensions["downloads"] = Downloads()
    guards.install(app)
    fit_page.register(app)
    profile_page.register(app)

    @app.context_processor
    def shared() -> dict[str, object]:
        from flask import session

        return {"pages": app.config["PAGES"], "csrf": session.get("csrf", "")}

    @app.get("/")
    def home() -> str:
        return render_template("home.html")

    @app.get("/brand/<name>")
    def brand(name: str):  # type: ignore[no-untyped-def]
        if name not in BRAND_FILES:
            abort(404)
        return send_from_directory(BRANDING, name)

    @app.get("/download/<download_id>")
    def download(download_id: str):  # type: ignore[no-untyped-def]
        path = app.extensions["downloads"].get(download_id)
        if path is None:
            abort(404)
        return send_file(path, as_attachment=True)

    def error_page(error: HTTPException):  # type: ignore[no-untyped-def]
        title, text = ERROR_TEXT.get(error.code or 500, ERROR_TEXT[500])
        return render_template("error.html", title=title, text=text), error.code or 500

    for code in ERROR_TEXT:
        app.register_error_handler(code, error_page)
    return app
