"""The resume and cover letter follow the candidate's template: fonts, sizes, rules and gaps.

The numbers come from the template's own XML (Letter, 0.5" and 0.75" margins, Carlito, 9.5 pt
resume text, 10.5 pt letter text, a blue rule under each heading, a gray rule under the contact
block and under the compact header on later pages, dates at the right margin).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

from jobomatic.documents import service
from jobomatic.documents.adapters.docx_tailored import (
    DocxTailoredCoverLetter,
    DocxTailoredResume,
)

FIXTURES = Path(__file__).parent / "fixtures" / "documents"


def _render(kind: str, renderer: object, tmp_path: Path) -> Document:
    content = service.parse_content(kind, (FIXTURES / f"{kind}.json").read_text(encoding="utf-8"))
    return Document(str(service.render_document(content, renderer, tmp_path / "out.docx")))


@pytest.fixture
def resume(tmp_path: Path) -> Document:
    return _render("resume", DocxTailoredResume(), tmp_path)


@pytest.fixture
def letter(tmp_path: Path) -> Document:
    return _render("cover-letter", DocxTailoredCoverLetter(), tmp_path)


def _border(paragraph: object) -> tuple[str, str] | None:
    bottom = paragraph._p.pPr.find(qn("w:pBdr") + "/" + qn("w:bottom"))  # type: ignore[attr-defined]
    if bottom is None:
        return None
    return bottom.get(qn("w:color")), bottom.get(qn("w:sz"))


def _find(doc: Document, text: str):
    return next(p for p in doc.paragraphs if p.text == text)


def test_the_default_font_is_carlito_so_unnamed_runs_never_fall_back_to_a_serif(
    resume: Document,
) -> None:
    fonts = resume.styles["Normal"].element.rPr.rFonts
    assert {fonts.get(qn(a)) for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs")} == {"Carlito"}


def test_the_page_is_letter_with_the_template_margins(resume: Document) -> None:
    section = resume.sections[0]
    assert (section.page_width, section.page_height) == (Inches(8.5), Inches(11))
    assert (section.top_margin, section.bottom_margin) == (Inches(0.5), Inches(0.5))
    assert (section.left_margin, section.right_margin) == (Inches(0.75), Inches(0.75))


def test_every_section_heading_has_a_blue_rule(resume: Document, letter: Document) -> None:
    for doc, names in (
        (resume, ["PROFESSIONAL SUMMARY", "TECHNICAL SKILLS", "PROFESSIONAL EXPERIENCE"]),
        (letter, ["WHAT I BRING"]),
    ):
        for name in names:
            heading = _find(doc, name)
            assert _border(heading) == ("2E6DA4", "6"), name
            assert heading.runs[0].font.size == Pt(11) and heading.runs[0].bold


def test_the_contact_block_ends_in_a_gray_rule_and_the_tagline_is_plain(
    resume: Document, letter: Document
) -> None:
    for doc in (resume, letter):
        name, tagline, contact = doc.paragraphs[:3]
        assert name.runs[0].font.size == Pt(16) and name.runs[0].bold
        assert tagline.runs[0].font.size == Pt(10) and not tagline.runs[0].bold
        assert contact.runs[0].font.size == Pt(9.5)
        # One gray rule, on the last contact line (no empty paragraph carries it).
        ruled = [p for p in doc.paragraphs[:4] if _border(p)]
        assert len(ruled) == 1 and _border(ruled[0]) == ("888888", "4")
        assert ruled[0].text and ruled[0].runs[0].font.size == Pt(9.5)


def test_with_links_the_rule_hangs_on_the_links_line_and_the_first_line_has_none() -> None:
    from jobomatic.documents.model import ResumeContact, TailoredCoverLetter

    letter = TailoredCoverLetter(
        contact=ResumeContact(
            name="A B",
            email="a@b.c",
            phone="555",
            location="Town, ST",
            linkedin="linkedin.com/in/ab",
            github="github.com/ab",
        ),
        tagline="Developer",
        role_title="Dev",
        company="Co",
        hook="Hello there.",
        bring=[{"label": "Skill", "body": "evidence"}],
        closing="Call me.",
    )
    doc = DocxTailoredCoverLetter().build(letter)
    _, _, contact, links = doc.paragraphs[:4]
    assert contact.text == "a@b.c  |  555  |  Town, ST"
    assert _border(contact) is None
    assert links.text == "linkedin.com/in/ab  |  github.com/ab"
    assert _border(links) == ("888888", "4")
    assert all(p.text.strip() for p in doc.paragraphs)


def test_a_bold_marker_in_the_tagline_never_makes_it_bold(tmp_path: Path) -> None:
    from jobomatic.documents.model import ResumeContact, TailoredCoverLetter

    letter = TailoredCoverLetter(
        contact=ResumeContact(name="A B", email="a@b.c"),
        tagline="**Developer | C#**",
        role_title="Dev",
        company="Co",
        hook="Hello there.",
        bring=[{"label": "Skill", "body": "evidence"}],
        closing="Call me.",
    )
    doc = DocxTailoredCoverLetter().build(letter)
    assert doc.paragraphs[1].text == "Developer | C#"
    assert not doc.paragraphs[1].runs[0].bold


def test_resume_text_is_9_5_pt_and_role_lines_are_10_pt_bold(resume: Document) -> None:
    bullet = next(p for p in resume.paragraphs if p.text.startswith("•  Raised test coverage"))
    assert bullet.runs[0].font.size == Pt(9.5)
    role = next(p for p in resume.paragraphs if p.text.startswith("Software Developer | "))
    assert role.runs[0].font.size == Pt(10) and role.runs[0].bold
    assert role.paragraph_format.keep_with_next


def test_dates_sit_at_the_right_margin_in_italics(resume: Document) -> None:
    role = next(p for p in resume.paragraphs if p.text.startswith("Software Developer | "))
    [stop] = role.paragraph_format.tab_stops
    assert stop.alignment == WD_TAB_ALIGNMENT.RIGHT
    assert stop.position == Inches(7.0)  # page width minus both side margins
    dates = role.runs[-1]
    assert dates.italic and dates.font.name == "Carlito" and dates.font.size == Pt(9.5)


def test_bullets_hang_at_a_quarter_inch(resume: Document, letter: Document) -> None:
    bullet = next(p for p in resume.paragraphs if p.text.startswith("•  "))
    assert bullet.paragraph_format.left_indent == Inches(0.25)
    assert bullet.paragraph_format.first_line_indent < 0
    item = next(p for p in letter.paragraphs if p.text.startswith("•  "))
    assert item.paragraph_format.left_indent == Inches(0.25)
    assert item.runs[0].font.size == Pt(10.5)


def test_later_pages_get_a_compact_header_over_a_gray_rule_and_the_first_page_none(
    resume: Document,
) -> None:
    section = resume.sections[0]
    assert section.different_first_page_header_footer
    for header in (section.header, section.even_page_header):
        [line] = header.paragraphs
        assert line.text.startswith("SARAH ASHFORD  |  ")
        assert line.runs[0].font.size == Pt(8.5)
        assert _border(line) == ("888888", "4")
    assert not section.first_page_header.paragraphs[0].text
    assert section.header_distance == Inches(0.25)


def test_the_later_page_header_leaves_a_gap_before_the_body(resume: Document) -> None:
    """Like the gap under the contact block on page 1, not text jammed against the rule."""
    section = resume.sections[0]
    for header in (section.header, section.even_page_header):
        assert header.paragraphs[0].paragraph_format.space_after >= Pt(16)


def test_the_letter_has_a_bold_re_line_and_no_empty_paragraphs(letter: Document) -> None:
    re_line = next(p for p in letter.paragraphs if p.text.startswith("Re: "))
    assert re_line.runs[0].bold and re_line.runs[0].font.size == Pt(10.5)
    assert all(p.text.strip() for p in letter.paragraphs)


def test_gaps_are_set_on_one_side_only_so_word_and_libreoffice_agree(
    resume: Document, letter: Document
) -> None:
    """Word adds "after" to the next "before"; LibreOffice keeps the larger. Never set both."""
    for doc in (resume, letter):
        paragraphs = doc.paragraphs
        for above, below in zip(paragraphs, paragraphs[1:], strict=False):
            after = above.paragraph_format.space_after or 0
            before = below.paragraph_format.space_before or 0
            both_set = after > Pt(3) and before > 0
            # name -> tagline (1.5 pt, 6 pt on the resume) are the only small "after" gaps allowed
            assert not both_set, (above.text[:30], below.text[:30])


def test_a_letter_date_has_no_zero_padded_day() -> None:
    from datetime import date

    from jobomatic.documents.adapters.docx_layout import long_date

    assert long_date(date(2026, 11, 5)) == "November 5, 2026"
    assert long_date(date(2026, 11, 15)) == "November 15, 2026"
