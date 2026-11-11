"""The platform-ready resume and the reusable cover-letter template (no job description)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobomatic import applications, paths
from jobomatic.interfaces.cli.main import main
from scripts import golden_outputs


def _text(path: Path) -> str:
    return golden_outputs.docx_text(path)


def test_platform_resume_uses_the_profile_headline_and_logs_nothing() -> None:
    assert main(["generate-profile-resume"]) == 0
    out = paths.output_dir("templates") / "resume.docx"
    text = _text(out)
    assert "SARAH ASHFORD" in text
    assert "Senior Full-Stack .NET Developer | Enterprise Applications | 8+ Years" in text
    assert "Professional Experience" in text.title() or "PROFESSIONAL EXPERIENCE" in text
    assert applications.load_applications() == []
    assert (paths.output_dir("templates") / "resume.docx.meta.json").is_file()


def test_platform_resume_keeps_the_profile_order_of_skills() -> None:
    assert main(["generate-profile-resume"]) == 0
    text = _text(paths.output_dir("templates") / "resume.docx")
    from jobomatic import bootstrap

    categories = [g.category for g in bootstrap.load_profile().skills.groups]
    positions = [text.index(f"{c}: ") for c in categories if f"{c}: " in text]
    assert positions == sorted(positions)


def test_cover_letter_template_keeps_the_placeholders_as_literal_text() -> None:
    assert main(["generate-profile-cover-letter"]) == 0
    text = _text(paths.output_dir("templates") / "cover-letter.docx")
    assert "[Company Name]" in text and "[Role Title]" in text
    assert "Dear " not in text  # the candidate's template goes straight from "Re:" to the hook
    assert "SARAH ASHFORD" in text
    assert applications.load_applications() == []


def test_output_path_can_be_chosen(tmp_path: Path) -> None:
    out = tmp_path / "mine.docx"
    assert main(["generate-profile-resume", "--out", str(out)]) == 0
    assert out.is_file()


def test_cover_letter_without_recording_needs_an_output_path(tmp_path: Path) -> None:
    from jobomatic.commands.cover_letter import (
        generate_cover_letter,
    )

    jd = Path(__file__).parent / "fixtures" / "sample-jd.md"
    with pytest.raises(ValueError, match="out_path is required"):
        generate_cover_letter(jd, record=False)
    docx_path, _, _ = generate_cover_letter(jd, out_path=tmp_path / "c.docx", record=False)
    assert docx_path.is_file() and applications.load_applications() == []
