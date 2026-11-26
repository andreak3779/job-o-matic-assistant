"""Render hand-tailored resume and cover-letter content to a DOCX (ADR 0035).

The deterministic generators (``generate-resume``, ``generate-cover-letter``) pick content by rule.
These commands are the other path the skill describes: a model reads the posting, writes the
tailored content as JSON that follows ``schema``, and ``run`` lays it out. ``draft`` hands out the
deterministic content as the grounded starting point, because a client such as Claude Desktop has
no other way to see the career facts (``profile show full`` has no tool).

``run`` gates a posting exactly as the generators do (fit, duplicate, pay), before it writes
anything, so the rule holds for every caller (ADR 0003, 0028). Without a posting (``out`` only) no
gate runs and nothing is logged, as before.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jobomatic import bootstrap
from jobomatic.applications import outputs
from jobomatic.commands.cover_letter import draft_letter
from jobomatic.commands.resume import draft_resume
from jobomatic.commands.support import (
    Confirmations,
    DocumentData,
    bootstrap_load_profile,
    finish_document,
    gate_documents,
    note_logged,
    vault_write_lock,
)
from jobomatic.documents import service
from jobomatic.documents.model import TailoredCoverLetter, TailoredResume
from jobomatic.documents.service import DocumentError
from jobomatic.fit.engine import FitResult, rate_parsed_jd
from jobomatic.fit.parser import parse_jd
from jobomatic.provenance import write_sidecar
from jobomatic.results import CommandResult, Message, guarded, ok

# The kinds that belong to one posting. The part-time kinds are rendered by the command line only.
TAILORED_KINDS = ("resume", "cover-letter")
_DOCUMENT_KIND = {"resume": "resume", "cover-letter": "cover_letter"}
FILE_NAMES = {"resume": "resume.docx", "cover-letter": "cover-letter.docx"}


def _tailored(kind: str) -> str:
    if kind not in TAILORED_KINDS:
        raise DocumentError(
            f"unknown document kind {kind!r}; expected one of {list(TAILORED_KINDS)}"
        )
    return kind


# -- schema ----------------------------------------------------------------------------------


def schema(kind: str) -> CommandResult[dict[str, Any]]:
    """The JSON Schema of the content a ``kind`` takes."""
    return guarded(lambda: ok(service.schema(_tailored(kind))))


def render_schema(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2)


# -- draft -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class DraftData:
    """The deterministic content for a posting, as JSON text a caller can edit and render."""

    kind: str
    content: str
    fit: FitResult | None


def draft(
    kind: str,
    jd_text: str,
    *,
    company: str | None = None,
    confirm: Confirmations = Confirmations(),
) -> CommandResult[DraftData]:
    """The content ``generate-resume`` / ``generate-cover-letter`` would render for this posting.

    Gated like the documents are, because it hands out the career material for that posting. It
    writes nothing and logs nothing.
    """

    def body() -> CommandResult[DraftData]:
        _tailored(kind)
        notes: list[Message] = []
        profile = bootstrap_load_profile()
        fit = gate_documents(jd_text, profile, confirm, notes)
        parsed = parse_jd(jd_text)
        model: TailoredResume | TailoredCoverLetter
        if kind == "resume":
            model = draft_resume(profile, parsed, jd_text)
        else:
            rated = rate_parsed_jd(parsed, profile)
            model, low_confidence = draft_letter(profile, parsed, rated, company or parsed.company)
            if low_confidence:
                notes.append(
                    Message("warning", "only a little verified evidence; the draft is cautious.")
                )
        # The content is the product and goes to stdout alone; what the gate said is the log.
        said = tuple(Message("log", n.text) if n.level in ("info", "note") else n for n in notes)
        return ok(DraftData(kind, model.model_dump_json(indent=2), fit), messages=said)

    return guarded(body)


def render_draft(data: DraftData) -> str:
    return data.content


# -- render ----------------------------------------------------------------------------------


def run(
    kind: str,
    content_text: str,
    *,
    jd_text: str | None = None,
    source: Path | None = None,
    company: str | None = None,
    out: Path | None = None,
    check_pages: bool = False,
    pdf: bool = False,
    confirm: Confirmations = Confirmations(),
    content_name: str = "content",
) -> CommandResult[DocumentData]:
    """Check the content, gate the posting when there is one, and write the DOCX.

    ``content_text`` is JSON for ``kind`` (``schema`` shows it). With ``jd_text`` the posting is
    gated (fit, duplicate, pay), the document goes in that posting's application folder (unless
    ``out`` is given) and a draft is logged, never an application. With only ``out`` nothing is
    gated or logged. Bad content stops with the field that is wrong, before anything is written.
    """

    def body() -> CommandResult[DocumentData]:
        _tailored(kind)
        notes: list[Message] = []
        profile = None
        fit: FitResult | None = None
        if jd_text is not None:
            profile = bootstrap_load_profile()
            fit = gate_documents(jd_text, profile, confirm, notes)
        elif out is None:
            raise DocumentError(
                "give an output path, or the job description so the document goes in the posting's folder"
            )
        content = service.parse_content(kind, content_text, content_name)
        service.ensure_skimmable(content, content_name)
        target = out
        if jd_text is not None:
            located = outputs.locate_application(
                jd_text,
                log=True,
                documents=(_DOCUMENT_KIND[kind],),
                fit_rating=fit.rating if fit else None,
                company=company,
                create_folder=out is None,
            )
            note_logged(notes, located)
            if target is None:
                target = located.folder / FILE_NAMES[kind]
        assert target is not None  # out, or a posting that names the folder
        written = service.render_document(content, bootstrap.document_renderer(kind), target)
        files = [written]
        if profile is not None:
            files.append(
                write_sidecar(
                    written,
                    script="render.py",
                    profile=profile,
                    inputs=[str(source)] if source else [],
                    fit_rating=fit.rating if fit else None,
                )
            )
        files += finish_document(kind, written, notes, pdf=pdf, check_pages=check_pages)
        return ok(DocumentData(written, fit), messages=tuple(notes), written=tuple(files))

    with vault_write_lock():
        return guarded(body)
