"""The Pluralsight import page: choose the file, see the dry run, then apply (ADR 0025).

The screen form of ``learning_import`` and the ``pluralsight-updater`` skill. A dry run saves
nothing. **Apply** is not on the page until a dry run with something to save is on screen, and it
carries only the id of the held upload, never a path. The page reads the import file from the
browser import page or a saved history page, as the command does; it does not parse a pasted table
(the standalone page is the only place that does).
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from flask import Flask, current_app, render_template, request

from jobomatic.commands import learning_import
from jobomatic.interfaces.web.uploads import Uploads
from jobomatic.interfaces.web.views import show

PROVIDER = "pluralsight"
SHOWN_ITEMS = 50  # how many new items to list before summarising


def _uploads() -> Uploads:
    uploads: Uploads = current_app.extensions["uploads"]
    return uploads


def _run(text: str, *, apply: bool):  # type: ignore[no-untyped-def]
    """Hand the command a file, as the MCP tool does with pasted content: a throwaway folder, and a
    stable dated name, because the name is recorded as each new item's source."""
    suffix = ".json" if text.lstrip()[:1] in ("{", "[") else ".html"
    with tempfile.TemporaryDirectory(prefix="pluralsight-import-") as scratch:
        export = Path(scratch) / f"pluralsight_import_{date.today().isoformat()}{suffix}"
        export.write_text(text, encoding="utf-8")
        return learning_import.run(export, PROVIDER, apply=apply)


def register(app: Flask) -> None:
    app.extensions["uploads"] = Uploads()

    @app.get("/pluralsight")
    def pluralsight_page() -> str:
        return render_template("pluralsight.html", preview=None, saved=None, problem=None)

    @app.post("/pluralsight/preview")
    def pluralsight_preview():  # type: ignore[no-untyped-def]
        sent = request.files.get("export")
        raw = sent.read() if sent is not None else b""
        if not raw.strip():
            page = render_template(
                "pluralsight.html", preview=None, saved=None, problem="Choose a file first."
            )
            return page, 400
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            page = render_template(
                "pluralsight.html",
                preview=None,
                saved=None,
                problem="That file is not text (UTF-8). Choose the import file or a saved history page.",
            )
            return page, 400
        result = _run(text, apply=False)
        shown = show(result)
        upload_id = _uploads().hold(text) if shown.ok and result.data.plan.has_changes else None  # type: ignore[union-attr]
        return render_template(
            "pluralsight.html",
            preview=shown,
            upload_id=upload_id,
            saved=None,
            problem=None,
            shown_items=SHOWN_ITEMS,
        )

    @app.post("/pluralsight/apply")
    def pluralsight_apply():  # type: ignore[no-untyped-def]
        text = _uploads().take(request.form.get("upload_id", ""))
        if text is None:
            page = render_template(
                "pluralsight.html",
                preview=None,
                saved=None,
                problem="That preview has expired. Choose the file again to see what would change.",
            )
            return page, 400
        return render_template(
            "pluralsight.html",
            preview=None,
            saved=show(_run(text, apply=True)),
            problem=None,
            shown_items=SHOWN_ITEMS,
        )
