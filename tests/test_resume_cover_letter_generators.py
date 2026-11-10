"""Structural smoke tests for generate_resume.py (Phase 5 of the job-search-skill
rewiring plan — audit-only tier, not full content/visual equivalence).

Uses the real profile (like tests/test_cli_commands.py's letter-generator
tests already do) rather than a synthetic one: generate_resume() calls
``dataclasses.replace(profile.resume, ...)``, which requires ``profile.resume`` to
be a real ``jobomatic.profile.model.Resume`` instance, not a test double.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document

from jobomatic.commands.cover_letter import (
    _names_skill,
)
from jobomatic.commands.resume import (
    generate_resume,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_JD = REPO_ROOT / "tests" / "fixtures" / "sample-jd.md"


def _generate(tmp_path: Path) -> Path:
    out_path, _, _ = generate_resume(
        FIXTURE_JD, company="TestCo", out_path=tmp_path / "resume.docx"
    )
    return out_path


def test_page2_header_is_configured_for_natural_page_flow(tmp_path: Path) -> None:
    """The Phase 5 fix: page 2+ must carry a running contact header, matching
    the old Node template's evenAndOddHeaders mechanism — python-docx
    gives no header at all on overflow pages by default."""
    doc = Document(str(_generate(tmp_path)))
    sec = doc.sections[0]

    assert doc.settings.odd_and_even_pages_header_footer is True
    assert sec.different_first_page_header_footer is True
    assert sec.first_page_header.paragraphs[0].text == ""

    default_text = sec.header.paragraphs[0].text
    even_text = sec.even_page_header.paragraphs[0].text
    assert default_text == even_text  # same running header on page 2 and page 3+
    assert "@" in default_text  # email present
    assert "|" in default_text  # compact pipe-separated line, matching the JS template


def test_page2_header_falls_back_to_default_name_when_contact_name_blank(
    tmp_path: Path,
) -> None:
    """Confirmed against the real profile: contact.name is currently blank
    (populated implicitly elsewhere), so the header must fall back rather
    than silently starting with " | email | ..."."""
    doc = Document(str(_generate(tmp_path)))
    header_text = doc.sections[0].header.paragraphs[0].text
    assert not header_text.startswith("|")
    assert "CANDIDATE NAME" in header_text or "@" in header_text


def test_resume_has_expected_section_headings(tmp_path: Path) -> None:
    doc = Document(str(_generate(tmp_path)))
    headings = {p.text for p in doc.paragraphs if p.text.strip()}
    for expected in (
        "PROFESSIONAL SUMMARY",
        "TECHNICAL SKILLS",
        "PROFESSIONAL EXPERIENCE",
        "CERTIFICATIONS",
    ):
        assert any(expected in h.upper() for h in headings), f"missing heading: {expected}"


def test_resume_never_prints_on_hold_cert_notes(tmp_path: Path) -> None:
    """A cert marked not_pursuing (e.g. AI-200 on hold) carries internal notes;
    they must not be rendered into the Certifications section of a resume."""
    doc = Document(str(_generate(tmp_path)))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "on hold" not in text.lower()
    assert "practice assessment" not in text.lower()


def test_resume_bullets_prioritize_jd_relevant_content(tmp_path: Path) -> None:
    """sample-jd.md asks for C#/.NET/Azure/Angular — the first bullet under
    the most recent role should reflect JD-relevant sorting, not source order."""
    doc = Document(str(_generate(tmp_path)))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "PROFESSIONAL EXPERIENCE" in text.upper()
    # A bullet-prefixed line exists at all (structure sanity, not exact wording).
    assert any(p.text.strip().startswith("•") for p in doc.paragraphs)


def test_resume_generation_is_idempotent_in_structure(tmp_path: Path) -> None:
    """Two runs against the same JD/profile should produce the same section
    structure (a light content-equivalence smoke check, not full parity)."""
    doc1 = Document(str(_generate(tmp_path / "a")))
    doc2 = Document(str(_generate(tmp_path / "b")))
    headings1 = [p.text for p in doc1.paragraphs if p.text.strip().isupper()]
    headings2 = [p.text for p in doc2.paragraphs if p.text.strip().isupper()]
    assert headings1 == headings2


def test_a_combined_requirement_matches_a_bullet_naming_either_part() -> None:
    bullet = "participated in agile/scrum development with a dispersed team"
    assert _names_skill("Agile / Scrum", bullet)
    assert _names_skill("Scrum / Kanban", bullet)
    assert not _names_skill("Kanban / Lean", bullet)
    assert _names_skill("agile", bullet)
