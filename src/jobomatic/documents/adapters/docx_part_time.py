"""DOCX renderers for the part-time resume and cover letter (python-docx).

Reproduces the layout of the Node templates these replace (fonts, sizes, spacing, hanging
indents, tab-aligned dates, blue section rules), so a document looks the same. Sizes are written
in the original's units: half-points for text and twentieths of a point (twips) for spacing.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.shared import Pt, RGBColor, Twips

from jobomatic.documents.adapters.docx_layout import add_bottom_border
from jobomatic.documents.humanize import find_ai_tells
from jobomatic.documents.model import PartTimeCoverLetter, PartTimeJob, PartTimeResume, Strength

FONT = "Carlito"
BLUE = "2E6DA4"
PAGE_WIDTH, PAGE_HEIGHT = 12240, 15840  # US Letter, in twips
MARGIN_TOP_BOT = 720  # 0.5"
MARGIN_SIDES = 1080  # 0.75"
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN_SIDES
_BULLET_INDENT = (360, 200)  # left, hanging


def _new_document(top_bottom: int) -> Any:
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Twips(PAGE_WIDTH), Twips(PAGE_HEIGHT)
    section.top_margin = section.bottom_margin = Twips(top_bottom)
    section.left_margin = section.right_margin = Twips(MARGIN_SIDES)
    return doc


def _paragraph(
    doc: Any,
    *,
    before: int = 0,
    after: int = 0,
    center: bool = False,
    keep_next: bool = False,
    indent: tuple[int, int] | None = None,
) -> Any:
    p = doc.add_paragraph()
    fmt = p.paragraph_format
    fmt.space_before, fmt.space_after = Twips(before), Twips(after)
    fmt.line_spacing = 1.0
    fmt.keep_with_next = keep_next
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if indent:
        fmt.left_indent, fmt.first_line_indent = Twips(indent[0]), Twips(-indent[1])
    return p


def _run(
    p: Any, text: str, size: int, *, bold: bool = False, italic: bool = False, color: str = "000000"
) -> None:
    run = p.add_run(text)
    run.font.name = FONT
    run.font.size = Pt(size / 2)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = RGBColor.from_string(color)


def _bottom_rule(p: Any, space: int) -> None:
    """A single blue line under the paragraph (the template's section rule).

    Written in the schema's order (``pBdr`` before ``spacing`` and ``jc``), which Word expects.
    """
    add_bottom_border(p, BLUE, eighths_pt=6, space_pt=space)


def _section_heading(doc: Any, text: str) -> None:
    p = _paragraph(doc, before=140, after=60, keep_next=True)
    _bottom_rule(p, 1)
    _run(p, text, 22, bold=True, color=BLUE)


def _name_and_contact(doc: Any, contact: Any, *, after_contact: int, rule: bool) -> None:
    name = _paragraph(doc, after=40, center=True)
    _run(name, contact.name, 32, bold=True)
    line = _paragraph(doc, after=after_contact, center=True)
    if rule:
        _bottom_rule(line, 4)
    _run(line, f"{contact.location}  |  {contact.email}  |  {contact.phone}", 20)


def _labelled_bullet(doc: Any, strength: Strength, size: int, after: int) -> None:
    p = _paragraph(doc, after=after, indent=_BULLET_INDENT)
    _run(p, "•  ", size)
    _run(p, strength.label + ": ", size, bold=True)
    _run(p, strength.body, size)


def _plain_bullet(doc: Any, text: str, *, keep_next: bool = False) -> None:
    p = _paragraph(doc, after=20, keep_next=keep_next, indent=_BULLET_INDENT)
    _run(p, "•  " + text, 21)


def _job_header(doc: Any, job: PartTimeJob) -> None:
    """Dates sit in three fixed tab stops so every start date, dash and end date lines up:
    start left-aligned, dash centred, end right-aligned at the margin."""
    p = _paragraph(doc, before=80, keep_next=True)
    stops = p.paragraph_format.tab_stops
    stops.add_tab_stop(Twips(CONTENT_WIDTH - 2000), WD_TAB_ALIGNMENT.LEFT)
    stops.add_tab_stop(Twips(CONTENT_WIDTH - 1000), WD_TAB_ALIGNMENT.CENTER)
    stops.add_tab_stop(Twips(CONTENT_WIDTH), WD_TAB_ALIGNMENT.RIGHT)
    _run(p, f"{job.title} · {job.company}", 21, bold=True)
    parts = job.dates.split(" – ")
    dates = f"\t{parts[0]}\t–\t{parts[1]}" if len(parts) == 2 else f"\t\t\t{job.dates}"
    _run(p, dates, 20, italic=True)


def _warn_about_stock_phrasing(*texts: str) -> None:
    tells = find_ai_tells("\n".join(texts))
    if tells:
        print(f"WARNING: AI-sounding wording in document: {', '.join(tells)}", file=sys.stderr)


class DocxPartTimeResume:
    """``DocumentRenderer`` for ``PartTimeResume``: one page, no tables or columns."""

    def render(self, content: PartTimeResume, out_path: Path) -> Path:
        _warn_about_stock_phrasing(
            content.summary,
            *(s.body for s in content.strengths),
            *(b for j in content.experience for b in j.bullets),
        )
        doc = _new_document(MARGIN_TOP_BOT)
        _name_and_contact(doc, content.contact, after_contact=60, rule=False)
        availability = _paragraph(doc, center=True)
        _run(availability, "Availability: ", 21, bold=True)
        _run(availability, content.availability, 21)

        _section_heading(doc, "SUMMARY")
        _body(doc, content.summary)
        _section_heading(doc, "KEY STRENGTHS")
        for strength in content.strengths:
            _labelled_bullet(doc, strength, 21, after=30)
        _section_heading(doc, "EXPERIENCE")
        for job in content.experience:
            _job_header(doc, job)
            for i, bullet in enumerate(job.bullets):
                _plain_bullet(doc, bullet, keep_next=i < len(job.bullets) - 1)
        for label, text in (
            ("Previous retail experience: ", content.previous_retail),
            ("Computer skills: ", content.software),
        ):
            if text:
                p = _paragraph(doc, before=80)
                _run(p, label, 21, bold=True)
                _run(p, text, 21)
        _section_heading(doc, "EDUCATION AND TRAINING")
        for line in content.education:
            _plain_bullet(doc, line)
        doc.save(str(out_path))
        return out_path


def _body(doc: Any, text: str) -> None:
    _run(_paragraph(doc, after=40), text, 21)


class DocxPartTimeCoverLetter:
    """``DocumentRenderer`` for ``PartTimeCoverLetter``: a short letter, strictly one page."""

    def render(self, content: PartTimeCoverLetter, out_path: Path) -> Path:
        _warn_about_stock_phrasing(
            content.hook,
            content.fit_paragraph,
            content.closing,
            *(s.body for s in content.strengths),
        )
        doc = _new_document(MARGIN_TOP_BOT * 3 // 2)
        _name_and_contact(doc, content.contact, after_contact=240, rule=True)

        def para(text: str, after: int = 140) -> None:
            _run(_paragraph(doc, after=after), text, 22)

        def line(text: str, *, bold: bool = False) -> None:
            _run(_paragraph(doc), text, 22, bold=bold)

        para(content.date, 200)
        for row in content.recipient:
            line(row)
        _run(_paragraph(doc, before=200, after=200), content.re_line, 22, bold=True)
        para(content.salutation)
        para(content.hook)
        para(content.strengths_intro, 60)
        for strength in content.strengths:
            _labelled_bullet(doc, strength, 22, after=50)
        _paragraph(doc, before=100)
        para(content.fit_paragraph)
        para(content.closing, 200)
        line("Sincerely,")
        _run(_paragraph(doc, before=360), content.contact.name, 22)
        doc.save(str(out_path))
        return out_path
