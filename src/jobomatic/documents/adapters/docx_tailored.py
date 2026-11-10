"""DOCX renderers for the tailored resume and cover letter (python-docx).

The document layout lives here; choosing what goes in it does not. The generators that read the
profile and a posting build the content, and ``render resume`` / ``render cover-letter`` lay out
content written by hand or by Claude, so both give the same document.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Inches, Pt

from jobomatic.documents.adapters.docx_layout import (
    BODY_SIZE,
    SUMMARY_SIZE,
    add_paragraph,
    bullet_label_para,
    centered_contact_block,
    section_heading,
    set_margins,
)
from jobomatic.documents.model import ResumeContact, TailoredCoverLetter, TailoredResume

_PAGE2_HEADER_SIZE = Pt(9)


def _add_page2_header(doc: Any, contact: ResumeContact) -> None:
    """Page 1 keeps an empty header (its contact block covers it); later pages carry a compact
    one-line "Name | email | phone | location | links" header, so a second page is still
    identifiable. Uses Word's odd/even header split, the same mechanism the old Node template
    used.
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
        p.text = ""
        run = p.add_run(line)
        run.font.name = "Carlito"
        run.font.size = _PAGE2_HEADER_SIZE

    section.first_page_header.is_linked_to_previous = False
    for p in list(section.first_page_header.paragraphs):
        p.text = ""


def _bullet(doc: Any, text: str, *, indent: bool = False) -> None:
    p = add_paragraph(doc, f"•  {text}", size=BODY_SIZE, space_after=Pt(2) if indent else Pt(0))
    if indent:
        p.paragraph_format.left_indent = Inches(0.25)
        p.paragraph_format.first_line_indent = Inches(-0.15)


class DocxTailoredResume:
    """``DocumentRenderer`` for ``TailoredResume``."""

    def render(self, content: TailoredResume, out_path: Path) -> Path:
        doc = Document()
        set_margins(doc.sections[0])
        _add_page2_header(doc, content.contact)
        centered_contact_block(doc, content.contact, tagline=content.tagline)

        section_heading(doc, "Professional Summary")
        for line in content.summary[:2]:
            add_paragraph(doc, line.strip(), size=SUMMARY_SIZE, space_after=Pt(2))

        section_heading(doc, "Technical Skills")
        for skill_line in content.skills:
            p = add_paragraph(
                doc, f"{skill_line.label}: ", bold=True, size=BODY_SIZE, space_after=Pt(2)
            )
            p.add_run(skill_line.skills).font.size = BODY_SIZE

        section_heading(doc, "Professional Experience")
        for job in content.experience:
            left = job.title
            if job.company:
                left += f" | {job.company}"
            if job.location:
                left += f", {job.location}"
            p = add_paragraph(
                doc, left, bold=True, size=SUMMARY_SIZE, space_before=Pt(6), keep_next=True
            )
            if job.dates:
                p.add_run(f"\t{job.dates}").font.italic = True
                # Right-align dates at the page edge (page width minus side margins).
                p.paragraph_format.tab_stops.add_tab_stop(Inches(8.5 - 0.75 - 0.5), 2)
            for text in job.bullets:
                _bullet(doc, text, indent=True)
        if content.additional_experience.strip():
            p = add_paragraph(
                doc,
                "Additional Experience: ",
                bold=True,
                size=BODY_SIZE,
                space_before=Pt(6),
                space_after=Pt(2),
            )
            p.add_run(content.additional_experience.strip()).font.size = BODY_SIZE

        if content.education:
            section_heading(doc, "Education")
            for line in content.education:
                _bullet(doc, line)

        section_heading(doc, "Certifications")
        for line in content.certifications:
            _bullet(doc, line)
        doc.save(str(out_path))
        return out_path


def _bullet_item(doc: Any, label: str, body: str) -> None:
    bullet_label_para(doc, label, body)


class DocxTailoredCoverLetter:
    """``DocumentRenderer`` for ``TailoredCoverLetter``."""

    def render(self, content: TailoredCoverLetter, out_path: Path) -> Path:
        doc = self.build(content)
        doc.save(str(out_path))
        return out_path

    def build(self, content: TailoredCoverLetter) -> Any:
        doc = Document()
        set_margins(doc.sections[0])
        centered_contact_block(doc, content.contact, tagline=content.tagline, space_after=Pt(8))
        add_paragraph(
            doc,
            content.date or date.today().strftime("%B %d, %Y"),
            size=BODY_SIZE,
            space_before=Pt(8),
        )
        add_paragraph(
            doc,
            f"Re: {content.role_title} — {content.company}",
            bold=True,
            size=BODY_SIZE,
            space_before=Pt(8),
        )
        add_paragraph(
            doc, f"Dear {content.company} Hiring Team,", size=BODY_SIZE, space_after=Pt(4)
        )
        add_paragraph(doc, content.hook, size=BODY_SIZE, space_before=Pt(8))

        section_heading(doc, "What I Bring")
        for item in content.bring:
            _bullet_item(doc, item.label, item.body)

        if content.highlights:  # no highlights, no heading; one highlight is not "two"
            section_heading(
                doc,
                "Two Relevant Highlights" if len(content.highlights) == 2 else "Relevant Highlight",
            )
            for item in content.highlights:
                _bullet_item(doc, item.label, item.body)

        add_paragraph(doc, content.closing, size=BODY_SIZE, space_before=Pt(8))
        add_paragraph(doc, "Sincerely,", size=BODY_SIZE, space_before=Pt(12))
        add_paragraph(doc, content.contact.name.upper(), size=BODY_SIZE, space_before=Pt(18))
        return doc
