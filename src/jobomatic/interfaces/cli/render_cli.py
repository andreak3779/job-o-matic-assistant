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
from jobomatic.commands import render as render_command
from jobomatic.commands.support import Confirmations, add_confirmation_flags
from jobomatic.documents import service
from jobomatic.documents.model import KINDS
from jobomatic.documents.service import DocumentError
from jobomatic.results import emit

COMMAND = "render"
_TAILORED = render_command.TAILORED_KINDS
_FILE_NAMES = {"part-time-resume": "resume.docx", "part-time-cover-letter": "cover-letter.docx"}


def register(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    render = subparsers.add_parser("render", help="Render a content file to a DOCX")
    sub = render.add_subparsers(dest="render_command", required=True)
    schema = sub.add_parser("schema", help="Print the JSON Schema of a kind's content")
    schema.add_argument("kind", choices=sorted(KINDS))
    draft = sub.add_parser(
        "draft",
        help="Print the deterministic content for a posting, to edit and render (resume, cover-letter)",
    )
    draft.add_argument("kind", choices=sorted(_TAILORED))
    draft.add_argument("jd", type=Path, help="Path to job description markdown file")
    draft.add_argument("--company", help="Company name for the letter (default: from the posting)")
    add_confirmation_flags(draft, "gaps", "reapply", "below_minimum")
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
                "and logs the posting as drafted (never applied); the posting is gated "
                "like generate-resume (fit, duplicate, pay)",
            )
            add_confirmation_flags(one, "gaps", "reapply", "below_minimum")
        else:
            one.add_argument(
                "--employer",
                help="Employer name for the output folder (default: the cover letter's recipient)",
            )


def run(args: argparse.Namespace) -> int:
    try:
        if args.render_command == "schema" and args.kind in _TAILORED:
            return emit(render_command.schema(args.kind), render_command.render_schema)
        if args.render_command == "schema":
            print(json.dumps(service.schema(args.kind), indent=2))
            return 0
        if args.render_command == "draft":
            return _draft(args)
        if args.render_command in _TAILORED:
            return _render_tailored(args)
        return _render(
            args.render_command,
            args.content,
            args.out,
            getattr(args, "employer", None),
            getattr(args, "check_pages", False),
        )
    except DocumentError as exc:
        print(f"[ERROR] {exc}")
        return 1


def _read(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DocumentError(f"{label} {path}: {exc}") from exc


def _draft(args: argparse.Namespace) -> int:
    jd_text = _read(args.jd, "job description")
    return emit(
        render_command.draft(
            args.kind, jd_text, company=args.company, confirm=Confirmations.from_args(args)
        ),
        render_command.render_draft,
    )


def _render_tailored(args: argparse.Namespace) -> int:
    content = _read(args.content, "content file")
    jd_text = _read(args.jd, "job description") if args.jd else None
    return emit(
        render_command.run(
            args.render_command,
            content,
            jd_text=jd_text,
            source=args.jd,
            out=args.out,
            check_pages=args.check_pages,
            confirm=Confirmations.from_args(args),
            content_name=args.content.name,
        )
    )


def _render(
    kind: str,
    content_path: Path,
    out: Path | None,
    employer: str | None,
    check_pages: bool = False,
) -> int:
    try:
        text = content_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DocumentError(f"{content_path}: {exc}") from exc
    content = service.parse_content(kind, text, content_path.name)
    if out is None:
        out = _default_path(kind, content, employer)
    written = service.render_document(content, bootstrap.document_renderer(kind), out)
    print(f"Wrote {written}")
    if check_pages:
        pages = service.check_pages(kind, written, bootstrap.page_counter())
        print(f"Pages: {pages}")
    return 0


def _default_path(kind: str, content: Any, employer: str | None) -> Path:
    employer = employer or (content.recipient[1] if kind == "part-time-cover-letter" else None)
    if not employer:
        raise DocumentError("give --out or --employer so the document has a folder")
    return paths.output_dir("part-time", day=date.today(), company=employer) / _FILE_NAMES[kind]
