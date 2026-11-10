"""Part-time documents: content checks, and renderings that match what the Node templates made.

The expected text and layout in ``tests/golden_documents/`` were captured from the Node.js
templates this module replaced, fed the same fictional content as ``tests/fixtures/documents``.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from jobomatic import bootstrap, paths
from jobomatic.documents import service
from jobomatic.documents.adapters.docx_part_time import (
    DocxPartTimeCoverLetter,
    DocxPartTimeResume,
)
from jobomatic.documents.service import DocumentError
from jobomatic.interfaces.cli.main import main
from scripts import golden_outputs
from tests.docx_layout_dump import dump_layout

FIXTURES = Path(__file__).parent / "fixtures" / "documents"
GOLDEN = Path(__file__).parent / "golden_documents"
KINDS = {
    "part-time-resume": DocxPartTimeResume,
    "part-time-cover-letter": DocxPartTimeCoverLetter,
}


def _content(kind: str):
    return service.parse_content(kind, (FIXTURES / f"{kind}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_text_matches_what_the_node_template_produced(kind: str, tmp_path: Path) -> None:
    out = service.render_document(_content(kind), KINDS[kind](), tmp_path / "out.docx")
    got = golden_outputs.normalize(golden_outputs.docx_text(out))
    assert got == (GOLDEN / f"{kind}.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_layout_matches_what_the_node_template_produced(kind: str, tmp_path: Path) -> None:
    """Page size and margins, fonts and sizes, spacing, indents, tab stops and rules."""
    out = service.render_document(_content(kind), KINDS[kind](), tmp_path / "out.docx")
    expected = json.loads((GOLDEN / f"{kind}.layout.json").read_text(encoding="utf-8"))
    assert dump_layout(out) == expected


# -- content checks ------------------------------------------------------------------------


def _fixture_json(kind: str) -> dict:
    return json.loads((FIXTURES / f"{kind}.json").read_text(encoding="utf-8"))


def test_content_errors_name_the_field() -> None:
    data = _fixture_json("part-time-resume")
    del data["contact"]["email"]
    data["experience"][0]["bullets"] = ["a", "b", "c"]
    with pytest.raises(DocumentError) as info:
        service.parse_content("part-time-resume", json.dumps(data), "mine.json")
    text = str(info.value)
    assert "mine.json: invalid part-time-resume" in text
    assert "contact.email" in text and "experience[0].bullets" in text


def test_unknown_keys_bad_json_and_unknown_kinds_are_errors() -> None:
    data = _fixture_json("part-time-cover-letter")
    data["salary"] = "x"
    with pytest.raises(DocumentError, match="salary"):
        service.parse_content("part-time-cover-letter", json.dumps(data))
    with pytest.raises(DocumentError, match="not valid JSON"):
        service.parse_content("part-time-resume", "{nope")
    with pytest.raises(DocumentError, match="unknown document kind"):
        service.parse_content("memo", "{}")
    with pytest.raises(DocumentError, match="unknown document kind"):
        bootstrap.document_renderer("memo")


def test_a_cover_letter_needs_exactly_three_strengths() -> None:
    data = _fixture_json("part-time-cover-letter")
    data["strengths"] = data["strengths"][:2]
    with pytest.raises(DocumentError, match="strengths"):
        service.parse_content("part-time-cover-letter", json.dumps(data))


def test_the_schema_is_available_for_each_kind() -> None:
    for kind in KINDS:
        assert "contact" in service.schema(kind)["properties"]


# -- the render command ----------------------------------------------------------------------


def test_render_writes_into_the_part_time_folder_named_after_the_employer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    content = FIXTURES / "part-time-cover-letter.json"
    assert main(["render", "part-time-cover-letter", str(content)]) == 0
    expected = paths.output_dir("part-time", day=date.today(), company="Corner Shop")
    assert (expected / "cover-letter.docx").is_file()
    assert str(expected / "cover-letter.docx") in capsys.readouterr().out


def test_render_resume_needs_an_employer_or_an_output_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    content = FIXTURES / "part-time-resume.json"
    assert main(["render", "part-time-resume", str(content)]) == 1
    assert "--out or --employer" in capsys.readouterr().out
    assert main(["render", "part-time-resume", str(content), "--employer", "Corner Shop"]) == 0
    folder = paths.output_dir("part-time", day=date.today(), company="Corner Shop")
    assert (folder / "resume.docx").is_file()
    assert (
        main(["render", "part-time-resume", str(content), "--out", str(tmp_path / "r.docx")]) == 0
    )
    assert (tmp_path / "r.docx").is_file()


def test_render_reports_bad_content_and_missing_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    assert main(["render", "part-time-resume", str(bad), "--out", str(tmp_path / "x.docx")]) == 1
    assert "invalid part-time-resume" in capsys.readouterr().out
    assert main(["render", "part-time-resume", str(tmp_path / "missing.json")]) == 1
    assert not (tmp_path / "x.docx").exists()


def test_render_schema_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["render", "schema", "part-time-resume"]) == 0
    assert "availability" in json.loads(capsys.readouterr().out)["properties"]


# -- the tailored resume and cover letter ---------------------------------------------------


def test_render_resume_lays_out_the_content_as_written(tmp_path: Path) -> None:
    out = tmp_path / "resume.docx"
    assert main(["render", "resume", str(FIXTURES / "resume.json"), "--out", str(out)]) == 0
    text = golden_outputs.docx_text(out)
    lines = text.splitlines()
    assert lines[0] == "SARAH ASHFORD"
    assert "Senior .NET Developer | C# · ASP.NET Core · Azure" in lines
    assert "Software Developer | Acme Health, Springfield, MD\tMarch 2021 – Present" in lines
    assert "Professional Development\t2020 – 2021" in lines  # no company: no separator
    assert "•  Raised test coverage from 20% to 75%." in lines
    assert "Additional Experience: Earlier programming roles in finance and logistics." in lines
    assert "•  Microsoft Azure Fundamentals (AZ-900) — Certified April 2026" in lines
    headings = [line for line in lines if line.isupper() and len(line) > 8][1:]  # not the name
    assert headings == [
        "PROFESSIONAL SUMMARY",
        "TECHNICAL SKILLS",
        "PROFESSIONAL EXPERIENCE",
        "EDUCATION",
        "CERTIFICATIONS",
    ]


def test_render_cover_letter_keeps_its_parts_in_order(tmp_path: Path) -> None:
    out = tmp_path / "cover.docx"
    assert (
        main(["render", "cover-letter", str(FIXTURES / "cover-letter.json"), "--out", str(out)])
        == 0
    )
    lines = golden_outputs.docx_text(out).splitlines()
    assert lines[:2] == ["SARAH ASHFORD", "Senior .NET Developer"]
    order = [
        "Re: Senior .NET Developer — Northgate Insurance Group",
        "Dear Northgate Insurance Group Hiring Team,",
        "WHAT I BRING",
        "RELEVANT HIGHLIGHT",  # the fixture has one highlight
        "Sincerely,",
        "SARAH ASHFORD",
    ]
    positions = [lines.index(item) for item in order[:-1]] + [
        len(lines) - 1 - lines[::-1].index(order[-1])
    ]
    assert positions == sorted(positions)
    assert "January 15, 2026" in lines


def test_render_files_a_tailored_document_by_posting_and_logs_a_draft() -> None:
    from jobomatic import applications

    jd = Path(__file__).parent / "fixtures" / "strong-fit-jd.md"
    assert main(["render", "resume", str(FIXTURES / "resume.json"), "--jd", str(jd)]) == 0
    [app] = applications.load_applications()
    assert app.status == "drafted" and "resume" in app.documents
    folder = paths.output_dir("application", name=applications.folder_name_for(app))
    assert (folder / "resume.docx").is_file()
    assert (
        main(["render", "cover-letter", str(FIXTURES / "cover-letter.json"), "--jd", str(jd)]) == 0
    )
    assert (folder / "cover-letter.docx").is_file()
    assert len(applications.load_applications()) == 1


def test_render_a_tailored_document_needs_out_or_jd(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["render", "resume", str(FIXTURES / "resume.json")]) == 1
    assert "--jd" in capsys.readouterr().out


def test_tailored_content_checks(capsys: pytest.CaptureFixture[str]) -> None:
    data = json.loads((FIXTURES / "resume.json").read_text(encoding="utf-8"))
    data["summary"] = ["a", "b", "c"]
    data["skills"] = []
    with pytest.raises(DocumentError) as info:
        service.parse_content("resume", json.dumps(data))
    assert "summary" in str(info.value) and "skills" in str(info.value)
    letter = json.loads((FIXTURES / "cover-letter.json").read_text(encoding="utf-8"))
    letter["bring"] = []
    with pytest.raises(DocumentError, match="bring"):
        service.parse_content("cover-letter", json.dumps(letter))


def test_a_profile_with_many_skill_groups_still_generates_a_resume(tmp_path: Path) -> None:
    """A real profile has well over seven skill groups. The content model must not reject that
    list; the generator keeps the first seven (ordered by relevance), as a resume allows."""
    from jobomatic.commands.resume import (
        generate_profile_resume,
    )
    from tests.profile_fixtures import SkillCategory, make_profile

    profile = make_profile(
        technical_skills=[SkillCategory(f"Group {n}", [f"skill {n}"]) for n in range(13)]
    )
    out, _ = generate_profile_resume(profile=profile, out_path=tmp_path / "r.docx")
    assert golden_outputs.docx_text(out).count("Group ") == 7


def _letter_lines_with_highlights(tmp_path: Path, count: int) -> list[str]:
    import json

    content = json.loads((FIXTURES / "cover-letter.json").read_text(encoding="utf-8"))
    content["highlights"] = [
        {"label": f"Highlight {n}", "body": "Something that happened."} for n in range(count)
    ]
    source = tmp_path / "letter.json"
    source.write_text(json.dumps(content), encoding="utf-8")
    out = tmp_path / "cover.docx"
    assert main(["render", "cover-letter", str(source), "--out", str(out)]) == 0
    return golden_outputs.docx_text(out).splitlines()


@pytest.mark.parametrize(
    ("count", "heading"),
    [(2, "TWO RELEVANT HIGHLIGHTS"), (1, "RELEVANT HIGHLIGHT")],
)
def test_the_highlights_heading_matches_how_many_there_are(
    tmp_path: Path, count: int, heading: str
) -> None:
    assert heading in _letter_lines_with_highlights(tmp_path, count)


def test_a_letter_without_highlights_has_no_highlights_heading(tmp_path: Path) -> None:
    lines = _letter_lines_with_highlights(tmp_path, 0)
    assert not [line for line in lines if "HIGHLIGHT" in line]
