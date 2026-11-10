"""``render`` subcommands: turn a content file into a DOCX (part-time resume and cover letter).

A thin driving adapter over ``jobomatic.documents``. The content is JSON that follows the schema
printed by ``render schema <kind>``; Claude writes it from the posting and the vault's part-time
notes, and this command lays it out.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from jobomatic import bootstrap, paths
from jobomatic.applications import outputs
from jobomatic.documents import service
from jobomatic.documents.model import KINDS
from jobomatic.documents.service import DocumentError

COMMAND = "render"
_TAILORED = ("resume", "cover-letter")
_DOCUMENT_KIND = {"resume": "resume", "cover-letter": "cover_letter"}
_FILE_NAMES = {
    "resume": "resume.docx",
    "cover-letter": "cover-letter.docx",
    "part-time-resume": "resume.docx",
    "part-time-cover-letter": "cover-letter.docx",
}


def register(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    render = subparsers.add_parser("render", help="Render a content file to a DOCX")
    sub = render.add_subparsers(dest="render_command", required=True)
    schema = sub.add_parser("schema", help="Print the JSON Schema of a kind's content")
    schema.add_argument("kind", choices=sorted(KINDS))
    for kind in sorted(KINDS):
        one = sub.add_parser(kind, help=f"Render {kind.replace('-', ' ')} content to a DOCX")
        one.add_argument("content", type=Path, help="JSON content file")
        one.add_argument("--out", type=Path, help="Output path (default: the part-time folder)")
        if kind in service.PAGE_LIMITS:
            one.add_argument(
                "--check-pages",
                action="store_true",
                help="Count the real pages with LibreOffice and fail if over the limit "
                "(slow; needs LibreOffice)",
            )
        if kind in _TAILORED:
            one.add_argument(
                "--jd",
                type=Path,
                help="The job description: files the document in that application's folder "
                "and logs the posting as drafted (never applied)",
            )
        else:
            one.add_argument(
                "--employer",
                help="Employer name for the output folder (default: the cover letter's recipient)",
            )


def run(args: argparse.Namespace) -> int:
    try:
        if args.render_command == "schema":
            print(json.dumps(service.schema(args.kind), indent=2))
            return 0
        return _render(
            args.render_command,
            args.content,
            args.out,
            getattr(args, "employer", None),
            getattr(args, "jd", None),
            getattr(args, "check_pages", False),
        )
    except DocumentError as exc:
        print(f"[ERROR] {exc}")
        return 1


def _render(
    kind: str,
    content_path: Path,
    out: Path | None,
    employer: str | None,
    jd: Path | None,
    check_pages: bool = False,
) -> int:
    try:
        text = content_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DocumentError(f"{content_path}: {exc}") from exc
    content = service.parse_content(kind, text, content_path.name)
    if out is None:
        out = _default_path(kind, content, employer, jd)
    written = service.render_document(content, bootstrap.document_renderer(kind), out)
    print(f"Wrote {written}")
    if check_pages:
        pages = service.check_pages(kind, written, bootstrap.page_counter())
        print(f"Pages: {pages}")
    return 0


def _default_path(kind: str, content: Any, employer: str | None, jd: Path | None) -> Path:
    if kind in _TAILORED:
        if jd is None:
            raise DocumentError("give --out, or --jd so the document goes in the posting's folder")
        try:
            jd_text = jd.read_text(encoding="utf-8")
        except OSError as exc:
            raise DocumentError(f"{jd}: {exc}") from exc
        located = outputs.locate_application(
            jd_text, log=True, documents=(_DOCUMENT_KIND[kind],), company=None
        )
        outputs.report(located)
        return located.folder / _FILE_NAMES[kind]
    employer = employer or (content.recipient[1] if kind == "part-time-cover-letter" else None)
    if not employer:
        raise DocumentError("give --out or --employer so the document has a folder")
    return paths.output_dir("part-time", day=date.today(), company=employer) / _FILE_NAMES[kind]
