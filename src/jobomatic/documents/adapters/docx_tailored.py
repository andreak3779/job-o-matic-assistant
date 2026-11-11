"""DOCX renderers for the tailored resume and cover letter (python-docx).

The document layout lives here; choosing what goes in it does not. The generators that read the
profile and a posting build the content, and ``render resume`` / ``render cover-letter`` lay out
content written by hand or by Claude, so both give the same document.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.shared import Inches, Pt

from jobomatic.documents.adapters.docx_layout import (
    FONT_NAME,
    LETTER_BODY_SIZE,
    PAGE2_HEADER_SIZE,
    RESUME_BODY_SIZE,
    RESUME_TITLE_SIZE,
    RULE_HEX,
    add_bottom_border,
    add_paragraph,
    apply_base_font,
    bullet_label_para,
    centered_contact_block,
    long_date,
    section_heading,
    set_margins,
)
from jobomatic.documents.model import ResumeContact, TailoredCoverLetter, TailoredResume

# The reference layout spaced blocks with empty paragraphs. These are the same gaps as real
# spacing, so the file has no empty paragraphs for an ATS to trip over. Every gap is set on one
# side only (before the item, never after the one above): Word adds "after" and "before" and
# LibreOffice keeps the larger, so a gap set on both sides would differ between the two.
_HEADING_BEFORE = 19.5  # pt; plus the gap the item above would have had after it
_HEADING_AFTER = Pt(14.6)
_NEXT_JOB_BEFORE = Pt(16)
# Space under the later-page header: the body starts below the header when the header is taller
# than the top margin, so this keeps a gap like the one under the contact block on page 1.
_PAGE2_HEADER_GAP = Pt(20)
_TEXT_WIDTH = Inches(7.0)  # US Letter minus 0.75" side margins: the right edge for dates
_BULLET_INDENT = Inches(0.25)
_BULLET_HANGING = Inches(-0.139)


def _add_page2_header(doc: Any, contact: ResumeContact) -> None:
    """Page 1 keeps an empty header (its contact block covers it); later pages carry a compact
    "Name | email | phone | location | links" line over a gray rule, so a second page is still
    identifiable. Uses Word's odd/even header split with a different first page.
    """
    doc.settings.odd_and_even_pages_header_footer = True

    section = doc.sections[0]
    section.different_first_page_header_footer = True

    parts = [
        contact.name.upper(),
        contact.email,
        contact.phone,
        contact.location,
        contact.linkedin,
        contact.github,
        contact.pluralsight,
    ]
    line = "  |  ".join(p for p in parts if p)

    for header in (section.header, section.even_page_header):
        header.is_linked_to_previous = False
        p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
        p.clear()
        p.paragraph_format.space_after = _PAGE2_HEADER_GAP
        run = p.add_run(line)
        run.font.name = FONT_NAME
        run.font.size = PAGE2_HEADER_SIZE
        add_bottom_border(p, RULE_HEX, eighths_pt=4, space_pt=2)

    section.first_page_header.is_linked_to_previous = False
    for p in list(section.first_page_header.paragraphs):
        p.clear()


def _bullet(doc: Any, text: str, *, first: bool) -> None:
    p = add_paragraph(
        doc, f"•  {text}", size=RESUME_BODY_SIZE, space_before=Pt(0) if first else Pt(1)
    )
    p.paragraph_format.left_indent = _BULLET_INDENT
    p.paragraph_format.first_line_indent = _BULLET_HANGING


def _job_line(doc: Any, left: str, dates: str, *, first: bool) -> None:
    """Bold ``Title | Company, Location`` with the dates in italics at the right margin."""
    p = add_paragraph(
        doc,
        left,
        bold=True,
        size=RESUME_TITLE_SIZE,
        space_before=Pt(0) if first else _NEXT_JOB_BEFORE,
        keep_next=True,
    )
    if dates:
        p.paragraph_format.tab_stops.add_tab_stop(_TEXT_WIDTH, WD_TAB_ALIGNMENT.RIGHT)
        run = p.add_run(f"\t{dates}")
        run.font.name = FONT_NAME
        run.font.size = RESUME_BODY_SIZE
        run.font.italic = True


class DocxTailoredResume:
    """``DocumentRenderer`` for ``TailoredResume``."""

    def render(self, content: TailoredResume, out_path: Path) -> Path:
        doc = Document()
        apply_base_font(doc)
        set_margins(doc.sections[0])
        _add_page2_header(doc, content.contact)
        centered_contact_block(
            doc, content.contact, tagline=content.tagline, space_after=Pt(0), name_space_after=Pt(6)
        )

        def heading(text: str, above: float = 0) -> None:
            section_heading(
                doc, text, space_before=Pt(_HEADING_BEFORE + above), space_after=_HEADING_AFTER
            )

        heading("Professional Summary")
        for index, line in enumerate(content.summary[:2]):
            add_paragraph(
                doc,
                line.strip(),
                size=RESUME_BODY_SIZE,
                space_before=Pt(2) if index else Pt(0),
            )

        heading("Technical Skills", above=2)
        for index, skill_line in enumerate(content.skills):
            p = add_paragraph(
                doc,
                f"{skill_line.label}: ",
                bold=True,
                size=RESUME_BODY_SIZE,
                space_before=Pt(1.75) if index else Pt(0),
            )
            run = p.add_run(skill_line.skills)
            run.font.name = FONT_NAME
            run.font.size = RESUME_BODY_SIZE

        heading("Professional Experience", above=1.75)
        for index, job in enumerate(content.experience):
            left = job.title
            if job.company:
                left += f" | {job.company}"
            if job.location:
                left += f", {job.location}"
            _job_line(doc, left, job.dates, first=index == 0)
            for position, text in enumerate(job.bullets):
                _bullet(doc, text, first=position == 0)
        if content.additional_experience.strip():
            _job_line(doc, "Additional Experience", "", first=not content.experience)
            _bullet(doc, content.additional_experience.strip(), first=True)

        if content.education:
            heading("Education", above=1)
            for position, line in enumerate(content.education):
                _bullet(doc, line, first=position == 0)

        heading("Certifications", above=1)
        for position, line in enumerate(content.certifications):
            _bullet(doc, line, first=position == 0)
        doc.save(str(out_path))
        return out_path


def _bullet_item(doc: Any, label: str, body: str, *, first: bool) -> None:
    p = bullet_label_para(
        doc,
        label,
        body,
        indent=_BULLET_INDENT,
        hanging=_BULLET_HANGING,
        space_after=Pt(0),
        size=LETTER_BODY_SIZE,
    )
    p.paragraph_format.space_before = Pt(0) if first else Pt(2.5)


class DocxTailoredCoverLetter:
    """``DocumentRenderer`` for ``TailoredCoverLetter``.

    Date, a bold "Re:" line, then the body: there is no "Dear ..." line, as in the candidate's
    own template.
    """

    def render(self, content: TailoredCoverLetter, out_path: Path) -> Path:
        doc = self.build(content)
        doc.save(str(out_path))
        return out_path

    def build(self, content: TailoredCoverLetter) -> Any:
        doc = Document()
        apply_base_font(doc)
        set_margins(doc.sections[0])
        centered_contact_block(doc, content.contact, tagline=content.tagline, space_after=Pt(0))
        add_paragraph(doc, content.date or long_date(), size=LETTER_BODY_SIZE, space_before=Pt(8))
        add_paragraph(
            doc,
            f"Re: {content.role_title} — {content.company}",
            bold=True,
            size=LETTER_BODY_SIZE,
            space_before=Pt(16.5),
        )
        add_paragraph(doc, content.hook, size=LETTER_BODY_SIZE, space_before=Pt(20.5))

        def heading(text: str, above: float = 0) -> None:
            section_heading(
                doc, text, space_before=Pt(_HEADING_BEFORE + above), space_after=_HEADING_AFTER
            )

        heading("What I Bring")
        for position, item in enumerate(content.bring):
            _bullet_item(doc, item.label, item.body, first=position == 0)

        if content.highlights:  # no highlights, no heading; one highlight is not "two"
            heading(
                "Two Relevant Highlights" if len(content.highlights) == 2 else "Relevant Highlight",
                above=2.5,
            )
            for position, item in enumerate(content.highlights):
                _bullet_item(doc, item.label, item.body, first=position == 0)

        add_paragraph(doc, content.closing, size=LETTER_BODY_SIZE, space_before=Pt(14))
        add_paragraph(doc, "Sincerely,", size=LETTER_BODY_SIZE, space_before=Pt(17.6))
        add_paragraph(doc, content.contact.name.upper(), size=LETTER_BODY_SIZE, space_before=Pt(34))
        return doc
