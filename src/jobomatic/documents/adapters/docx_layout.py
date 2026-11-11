"""Shared DOCX layout helpers for the resume, cover-letter and letter generators.

Brand color, margins and font come from ``docx-style.json``.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from jobomatic.documents.humanize import find_ai_tells


class Contact(Protocol):
    """What a document header needs: the profile's identity and a resume's contact both fit."""

    @property
    def name(self) -> str: ...
    @property
    def email(self) -> str: ...
    @property
    def phone(self) -> str: ...
    @property
    def location(self) -> str: ...
    @property
    def linkedin(self) -> str: ...
    @property
    def github(self) -> str: ...
    @property
    def pluralsight(self) -> str: ...


_SLUGIFY_RE = re.compile(r"[^a-z0-9]+")


# Brand color, margins and font live in one file so every generator agrees.
_STYLE = json.loads((Path(__file__).parent / "docx-style.json").read_text(encoding="utf-8"))
BLUE = RGBColor.from_string(_STYLE["blue_hex"])
MARGIN_TOP_BOT = Inches(_STYLE["margin_top_bottom_in"])
MARGIN_SIDES = Inches(_STYLE["margin_sides_in"])
BODY_SIZE = Pt(_STYLE["body_size_pt"])
SUMMARY_SIZE = Pt(_STYLE["summary_size_pt"])
SECTION_SIZE = Pt(_STYLE["section_size_pt"])
NAME_SIZE = Pt(_STYLE["name_size_pt"])
DEFAULT_SIGNATURE_NAME = _STYLE["default_signature_name"]
FONT_NAME = _STYLE["font_name"]
RULE_HEX = _STYLE["rule_hex"]  # the thin gray rule under the contact block and page-2 header
TAGLINE_SIZE = Pt(_STYLE["tagline_size_pt"])
CONTACT_SIZE = Pt(_STYLE["contact_size_pt"])
LETTER_BODY_SIZE = Pt(_STYLE["letter_body_size_pt"])
RESUME_BODY_SIZE = Pt(_STYLE["resume_body_size_pt"])
RESUME_TITLE_SIZE = Pt(_STYLE["resume_title_size_pt"])
PAGE2_HEADER_SIZE = Pt(_STYLE["page2_header_size_pt"])
HEADER_DISTANCE = Inches(_STYLE["header_distance_in"])


def set_margins(section: Any) -> None:
    """Set US-Letter margins."""
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = MARGIN_TOP_BOT
    section.bottom_margin = MARGIN_TOP_BOT
    section.left_margin = MARGIN_SIDES
    section.right_margin = MARGIN_SIDES
    section.header_distance = HEADER_DISTANCE


def apply_base_font(doc: Document) -> None:
    """Make Carlito the document's default font, single-spaced with no paragraph gap.

    A run that does not name a font (a tab, a trailing ``add_run``) inherits it instead of falling
    back to the template's serif face.
    """
    normal = doc.styles["Normal"]
    normal.font.name = FONT_NAME
    fonts = normal.element.get_or_add_rPr().rFonts
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attr), FONT_NAME)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = 1.0


# What follows ``w:pBdr`` in a paragraph's properties (the schema fixes the order).
_AFTER_PBDR = (
    "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct",
    "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd",
    "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents",
    "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment", "w:textboxTightWrap",
    "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange",
)  # fmt: skip


def add_bottom_border(
    paragraph: Any, color_hex: str, *, eighths_pt: int = 6, space_pt: int = 1
) -> None:
    """Draw a single bottom rule under a paragraph (``eighths_pt`` 6 = 0.75 pt, 4 = 0.5 pt).

    python-docx has no border API, so this writes ``w:pBdr`` itself.
    """
    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(eighths_pt))
    bottom.set(qn("w:space"), str(space_pt))
    bottom.set(qn("w:color"), color_hex)
    borders.append(bottom)
    p_pr.insert_element_before(borders, *_AFTER_PBDR)


def long_date(day: date | None = None) -> str:
    """``November 5, 2026``: the month spelled out and no zero-padded day."""
    day = day or date.today()
    return f"{day:%B} {day.day}, {day.year}"


_BOLD_MD = re.compile(r"\*\*(.+?)\*\*")


def _split_bold(text: str) -> list[tuple[str, bool]]:
    """Split ``**bold**`` markdown into ``(text, is_bold)`` chunks so no literal asterisks reach a DOCX."""
    parts: list[tuple[str, bool]] = []
    pos = 0
    for m in _BOLD_MD.finditer(text):
        if m.start() > pos:
            parts.append((text[pos : m.start()], False))
        parts.append((m.group(1), True))
        pos = m.end()
    if pos < len(text) or not parts:
        parts.append((text[pos:], False))
    return parts


def add_paragraph(
    doc: Document,
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    align: Any = WD_ALIGN_PARAGRAPH.LEFT,
    size: Any = BODY_SIZE,
    color: Any = None,
    space_before: Any = Pt(0),
    space_after: Any = Pt(0),
    keep_next: bool = False,
) -> Any:
    """Add a single-run paragraph with the standard font.

    Warns on stderr when the text contains stock AI phrasing (see ``humanize``).
    """
    tells = find_ai_tells(text)
    if tells:
        print(f"WARNING: AI-sounding wording in document: {', '.join(tells)}", file=sys.stderr)
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before = space_before
    p.paragraph_format.space_after = space_after
    p.paragraph_format.keep_with_next = keep_next
    for chunk, chunk_bold in _split_bold(text):
        run = p.add_run(chunk)
        run.font.name = FONT_NAME
        run.font.size = size
        run.font.bold = bold or chunk_bold
        run.font.italic = italic
        if color:
            run.font.color.rgb = color
    return p


def section_heading(
    doc: Document, text: str, *, space_before: Any = Pt(8), space_after: Any = Pt(2)
) -> Any:
    """ALL CAPS blue section heading with a blue rule under it."""
    p = add_paragraph(
        doc,
        text.upper(),
        bold=True,
        color=BLUE,
        size=SECTION_SIZE,
        space_before=space_before,
        space_after=space_after,
    )
    add_bottom_border(p, _STYLE["blue_hex"])
    return p


def centered_contact_block(
    doc: Document,
    contact: Contact,
    tagline: str,
    *,
    space_after: Any = Pt(4),
    name_space_after: Any = Pt(1.5),
) -> None:
    """Render the name/tagline/contact-lines header used on resume + cover letter.

    ``contact`` is a typed ``jobomatic.profile.model.Contact``. The function tolerates
    empty strings so older data without every field still render.
    """
    name = (contact.name or DEFAULT_SIGNATURE_NAME).upper()
    email = contact.email or ""
    phone = contact.phone or ""
    location = contact.location or ""
    linkedin = contact.linkedin or ""
    github = contact.github or ""
    pluralsight = contact.pluralsight or ""

    add_paragraph(
        doc,
        name,
        bold=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        size=NAME_SIZE,
        space_after=name_space_after,
    )
    tagline = tagline.replace("**", "")  # the tagline is plain text, never bold
    if tagline:
        add_paragraph(
            doc,
            tagline,
            align=WD_ALIGN_PARAGRAPH.CENTER,
            size=TAGLINE_SIZE,
            space_after=Pt(1.5),
        )
    lines = [
        line
        for line in (
            "  |  ".join(p for p in [email, phone, location] if p),
            "  |  ".join(p for p in [linkedin, github, pluralsight] if p),
        )
        if line
    ]
    for index, line in enumerate(lines):
        last = index == len(lines) - 1
        para = add_paragraph(
            doc,
            line,
            align=WD_ALIGN_PARAGRAPH.CENTER,
            size=CONTACT_SIZE,
            space_after=space_after if last else Pt(0),
        )
        if last:  # the rule hangs on the last contact line, so there is no empty paragraph
            add_bottom_border(para, RULE_HEX, eighths_pt=4, space_pt=2)


def slugify(name: str) -> str:
    """Lowercase, collapse non-alnum runs to single underscores, strip edges.

    Centralized so output filenames stay consistent across all generators.
    """
    return _SLUGIFY_RE.sub("_", name.lower()).strip("_")


def clean_stack(stack: list[str], *, limit: int | None = None) -> str:
    """Return a comma-joined stack string with whitespace-stripped tokens.

    Profiles occasionally serialize stack items with leading/trailing spaces;
    joining without ``.strip()`` produces ``"Angular ,  ASP.NET Core Web API"``.
    Empty entries are dropped so callers don't see dangling commas.
    """
    items = [s.strip() for s in stack if s and s.strip()]
    if limit is not None:
        items = items[:limit]
    return ", ".join(items)


def letter_header(
    doc: Document,
    contact: Contact,
    *,
    company: str,
    tagline: str,
    salutation: str = "Dear {company} Hiring Team,",
    re_line: str | None = None,
    contact_space_after: Any = Pt(8),
    salutation_space_after: Any = Pt(4),
) -> None:
    """Render the canonical top-of-letter block.

    Sets page margins, then emits: contact block, today's date, optional
    ``Re: <title> — <company>`` line, and the salutation.

    Use :func:`letter_footer` to emit the matching closing block.
    """
    apply_base_font(doc)
    set_margins(doc.sections[0])
    centered_contact_block(doc, contact, tagline=tagline, space_after=contact_space_after)
    add_paragraph(
        doc,
        long_date(),
        size=BODY_SIZE,
        space_before=Pt(8),
    )
    if re_line:
        add_paragraph(doc, re_line, bold=True, size=BODY_SIZE, space_before=Pt(8))
    add_paragraph(
        doc,
        salutation.format(company=company),
        size=BODY_SIZE,
        space_after=salutation_space_after,
    )


def letter_footer(
    doc: Document,
    contact: Contact,
    *,
    close_phrase: str = "Sincerely,",
    close_space_before: Any = Pt(12),
    name_space_before: Any = Pt(18),
) -> None:
    """Render the canonical closing block: ``Sincerely,`` + uppercase name."""
    add_paragraph(doc, close_phrase, size=BODY_SIZE, space_before=close_space_before)
    add_paragraph(
        doc,
        (contact.name or DEFAULT_SIGNATURE_NAME).upper(),
        size=BODY_SIZE,
        space_before=name_space_before,
    )


def bullet_label_para(
    doc: Document,
    label: str,
    body: str,
    *,
    indent: Any = Inches(0.25),
    hanging: Any = Inches(-0.15),
    space_after: Any = Pt(6),
    size: Any = BODY_SIZE,
) -> Any:
    """Render a hanging-indent bullet: ``•  **Label:** body``.

    Used by the cover-letter and cold-call "what I bring" / "why I'm a fit"
    sections. The label is bold; the body is regular weight.
    """
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = indent
    p.paragraph_format.first_line_indent = hanging
    p.paragraph_format.space_after = space_after
    bullet = p.add_run("\u2022  ")
    bullet.font.name = FONT_NAME
    bullet.font.size = size
    label_run = p.add_run(f"{label}: ")
    label_run.font.name = FONT_NAME
    label_run.font.size = size
    label_run.bold = True
    for chunk, chunk_bold in _split_bold(body):
        body_run = p.add_run(chunk)
        body_run.font.name = FONT_NAME
        body_run.font.size = size
        body_run.font.bold = chunk_bold or None
    return p


def split_label_body(text: str) -> tuple[str, str]:
    """Split a differentiator string into ``(label, body)``.

    Accepts colon, semicolon, en dash, em dash, or a *spaced* hyphen as the
    separator. A hyphen embedded in a word like ``"Full-stack"`` is *not* a
    separator — we only break on ``-`` when it's surrounded by whitespace.
    If no separator is present the full string is returned as both label
    and body so callers always get a non-empty label.
    """
    sep = re.search(r"\s*[:;\u2013\u2014]|\s+-\s+", text)
    if not sep:
        return text.strip(), text.strip()
    label = text[: sep.start()].strip()
    body = text[sep.end() :].strip()
    return (label or text.strip()), (body or text.strip())
