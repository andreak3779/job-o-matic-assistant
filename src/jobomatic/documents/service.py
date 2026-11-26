"""Document use cases: check content, then hand it to a renderer.

Depends only on the model and ports: no files are read here beyond the JSON text passed in.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from jobomatic.documents import skim
from jobomatic.documents.model import KINDS
from jobomatic.documents.ports import DocumentRenderer, PageCounter


class DocumentError(Exception):
    """Content cannot be used to make a document (ADR 0007: fail loud)."""


class PageCountUnavailable(DocumentError):
    """The real page count cannot be measured here (no LibreOffice, no ``pdfinfo``)."""


class PdfExportUnavailable(DocumentError):
    """A PDF cannot be made here (no working LibreOffice)."""


# Page limits by kind of document: (fewest, most). Only these two have a rule (CLAUDE.md).
PAGE_LIMITS: dict[str, tuple[int, int]] = {"resume": (1, 2), "cover-letter": (1, 1)}


def check_pages(
    kind: str, path: Path, counter: PageCounter, *, measured: Path | None = None
) -> int:
    """Measure ``path`` and refuse it if it breaks its kind's page limit. Returns the page count.

    A kind with no limit is only measured. ``measured`` is the file's PDF, when one was already
    made, so it is not converted twice. The file is left where it is either way, so the caller can
    open it.
    """
    pages = counter.count(measured or path)
    fewest, most = PAGE_LIMITS.get(kind, (1, 10**6))
    if pages > most or pages < fewest:
        allowed = f"exactly {most}" if fewest == most else f"at most {most}"
        raise DocumentError(f"{path.name} is {pages} page(s); a {kind} must be {allowed}")
    return pages


def parse_content(kind: str, text: str, source: str = "content") -> Any:
    """Validate JSON text as the content of ``kind``; the error names the field that is wrong."""
    model = KINDS.get(kind)
    if model is None:
        raise DocumentError(f"unknown document kind {kind!r}; expected one of {sorted(KINDS)}")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise DocumentError(f"{source}: not valid JSON: {exc}") from exc
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        lines = [f"{source}: invalid {kind}"]
        for err in exc.errors():
            where = ""
            for part in err["loc"]:
                where += f"[{part}]" if isinstance(part, int) else f"{'.' if where else ''}{part}"
            lines.append(f"  {where or '<root>'}: {err['msg']}")
        raise DocumentError("\n".join(lines)) from exc


def ensure_skimmable(content: Any, source: str = "content") -> None:
    """Refuse content a recruiter could not read in fifteen seconds, naming every field over its
    budget (``documents.skim``). A kind with no budget passes."""
    over = skim.problems(content)
    if over:
        lines = [f"{source}: too long to skim in 15 seconds; shorten these and render again"]
        lines += [f"  {line}" for line in over]
        raise DocumentError("\n".join(lines))


def render_document(content: Any, renderer: DocumentRenderer[Any], out_path: Path) -> Path:
    """Render validated content to ``out_path``."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return renderer.render(content, out_path)


def schema(kind: str) -> dict[str, Any]:
    model = KINDS.get(kind)
    if model is None:
        raise DocumentError(f"unknown document kind {kind!r}; expected one of {sorted(KINDS)}")
    return model.model_json_schema()
