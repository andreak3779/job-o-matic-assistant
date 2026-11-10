"""Unit tests for the thank-you letter generator's evidence grounding."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from docx import Document

REPO_ROOT = Path(__file__).resolve().parents[1]

from jobomatic.commands.thank_you import (
    _build_letter,
    _select_star_story,
    generate_thank_you_letter,
)
from jobomatic.commands.thank_you import (
    main as thank_you_main,
)
from jobomatic.fit.engine import FitResult, SkillMatch
from tests.profile_fixtures import (
    Contact,
    SkillCategory,
    StarStory,
    WorkExperience,
    make_profile,
)


def _make_profile(
    *,
    star_stories: list[dict[str, Any]] | None = None,
    technical_skills: list[tuple[str, list[str]]] | None = None,
    legacy_companies: list[str] | None = None,
) -> Any:
    """A minimal profile for testing."""
    return make_profile(
        contact=Contact(name="Sarah Ashford", email="jordan@example.com"),
        headline="Full-Stack Engineer",
        technical_skills=[SkillCategory(category=c, skills=sk) for c, sk in technical_skills or []],
        star_stories=[StarStory(**s) for s in star_stories or []],
        legacy_experience=[
            WorkExperience(title="Programmer", company=name) for name in legacy_companies or []
        ],
    )


def _make_fit_result(matches: list[tuple[str, str, str]]) -> FitResult:
    """Create a FitResult with required matches.

    Each tuple is (skill, status, evidence).
    """
    return FitResult(
        rating="Pass",
        required=[SkillMatch(skill=s, status=status, evidence=e) for s, status, e in matches],
        nice_to_have=[],
        rationale="",
    )


def test_build_letter_key_takeaways_are_the_supplied_discussion_points() -> None:
    """The core Phase 4 fix: KEY TAKEAWAYS must be the real discussion points
    verbatim, not derived from JD/profile evidence."""
    result = _make_fit_result([("Python", "match", "Acme Corp 2023-Present")])
    profile = _make_profile()
    parsed = SimpleNamespace(required=["Python"], nice_to_have=[])
    points = ["We discussed the team's Q3 roadmap.", "They asked about my CI/CD experience."]
    letter = _build_letter("Acme", "Engineer", [], None, points, result, profile, parsed)

    assert letter["key_takeaways"] == points


def test_build_letter_opening_names_interviewer_and_date_when_given() -> None:
    result = _make_fit_result([])
    profile = _make_profile()
    parsed = SimpleNamespace(required=[], nice_to_have=[])
    letter = _build_letter(
        "Acme",
        "Engineer",
        ["Jane Doe"],
        "August 25, 2026",
        ["A discussion point."],
        result,
        profile,
        parsed,
    )
    assert "Jane Doe" in letter["opening"]
    assert "August 25, 2026" in letter["opening"]


def test_build_letter_opening_omits_interviewer_and_date_when_absent() -> None:
    result = _make_fit_result([])
    profile = _make_profile()
    parsed = SimpleNamespace(required=[], nice_to_have=[])
    letter = _build_letter(
        "Acme", "Engineer", [], None, ["A discussion point."], result, profile, parsed
    )
    assert "today" in letter["opening"]


def test_build_letter_opening_includes_reinforcing_clause_for_grounded_skills() -> None:
    result = _make_fit_result(
        [
            ("Python", "match", "Acme Corp 2023-Present"),
            ("Azure", "course", "Pluralsight AZ-204"),
            ("React", "match", "Widget Co 2022-2023"),
        ]
    )
    profile = _make_profile()
    parsed = SimpleNamespace(required=["Python", "Azure", "React"], nice_to_have=[])
    letter = _build_letter(
        "Acme", "Engineer", [], None, ["A discussion point."], result, profile, parsed
    )

    assert "Python" in letter["opening"]
    assert "React" in letter["opening"]
    assert "Acme Corp 2023-Present" not in letter["opening"]
    assert "Pluralsight AZ-204" not in letter["opening"]


def test_build_letter_opening_has_no_reinforcing_clause_when_no_grounded_skills() -> None:
    result = _make_fit_result([("Quantum ML", "gap", "not in resume")])
    profile = _make_profile()
    parsed = SimpleNamespace(required=["Quantum ML"], nice_to_have=[])
    letter = _build_letter(
        "Acme", "Engineer", [], None, ["A discussion point."], result, profile, parsed
    )

    assert "Quantum ML" not in letter["opening"]
    # The letter still stands on its own via the (required) discussion points.
    assert letter["key_takeaways"] == ["A discussion point."]


def test_select_star_story_prefers_jd_tag_overlap() -> None:
    profile = _make_profile(
        star_stories=[
            {
                "title": "Matching Story",
                "situation": "We needed Python.",
                "task": "Build API",
                "action": "Wrote Python.",
                "result": "Shipped.",
                "jd_tags": ["python"],
            },
            {
                "title": "Unrelated Story",
                "situation": "We needed design.",
                "task": "Redesign UI",
                "action": "Sketched.",
                "result": "Approved.",
                "jd_tags": ["ux"],
            },
        ]
    )
    star = _select_star_story(profile, ["python"], [])
    assert star is not None
    assert star.title == "Matching Story"


def test_generate_thank_you_letter_writes_sidecar(tmp_path: Path) -> None:
    profile = _make_profile()
    jd_path = tmp_path / "jd.md"
    jd_path.write_text(
        "# Senior Engineer\n\n**Company:** Acme\n\nRequired: Python\n", encoding="utf-8"
    )

    out_path, sidecar_path, _ = generate_thank_you_letter(
        jd_path,
        profile=profile,
        company="Acme",
        discussion_points=["We discussed the team's roadmap."],
        out_path=tmp_path / "thanks.docx",
        root=tmp_path,
    )

    assert out_path.exists()
    assert sidecar_path.exists()
    meta = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert meta["script"] == "generate_thank_you_letter.py"
    assert "warnings" in meta


# ── discussion_points is required — fails closed (Phase 4 fix) ─────────────


def test_generate_thank_you_letter_raises_without_discussion_points(tmp_path: Path) -> None:
    profile = _make_profile()
    with pytest.raises(ValueError, match="discussion_points"):
        generate_thank_you_letter(
            None,
            profile=profile,
            company="Acme",
            discussion_points=None,
            out_path=tmp_path / "thanks.docx",
            root=tmp_path,
        )


def test_generate_thank_you_letter_raises_with_empty_discussion_points_list(tmp_path: Path) -> None:
    profile = _make_profile()
    with pytest.raises(ValueError, match="discussion_points"):
        generate_thank_you_letter(
            None,
            profile=profile,
            company="Acme",
            discussion_points=[],
            out_path=tmp_path / "thanks.docx",
            root=tmp_path,
        )


def test_main_fails_closed_without_discussion_point_flag(tmp_path: Path, capsys) -> None:
    rc = thank_you_main(["--company", "Acme", "--out", str(tmp_path / "thanks.docx")])
    assert rc == 1
    assert "discussion_points" in capsys.readouterr().err
    assert not (tmp_path / "thanks.docx").exists()


# ── End-to-end: no JD needed, discussion points + interviewer land in the DOCX ──


def _docx_text(path: Path) -> str:
    return "\n".join(p.text for p in Document(str(path)).paragraphs)


def test_generate_thank_you_letter_without_jd_uses_real_inputs(tmp_path: Path) -> None:
    profile = _make_profile()
    out_path, _, result = generate_thank_you_letter(
        None,
        profile=profile,
        company="Acme",
        role="Senior Engineer",
        interviewer_names=["Jane Doe"],
        interview_date="August 25, 2026",
        discussion_points=[
            "We discussed the team's Q3 roadmap.",
            "They asked about my CI/CD experience.",
        ],
        out_path=tmp_path / "thanks.docx",
        root=tmp_path,
    )

    text = _docx_text(out_path)
    assert "Jane Doe" in text
    assert "August 25, 2026" in text
    assert "We discussed the team's Q3 roadmap." in text
    assert "They asked about my CI/CD experience." in text
    assert "Re: Thank You — Senior Engineer Interview, Acme" in text
    # No JD parsed -> no required skills -> the honest "not assessed" default.
    assert result.rationale == "No JD provided — fit not assessed."


def test_salutation_uses_interviewer_names_not_generic_hiring_team(tmp_path: Path) -> None:
    profile = _make_profile()
    out_path, _, _ = generate_thank_you_letter(
        None,
        profile=profile,
        company="Acme",
        interviewer_names=["Jane Doe", "Bob Smith"],
        discussion_points=["A discussion point."],
        out_path=tmp_path / "thanks.docx",
        root=tmp_path,
    )
    text = _docx_text(out_path)
    assert "Dear Jane Doe, Bob Smith," in text
    assert "Hiring Team" not in text


def test_salutation_defaults_to_hiring_team_without_interviewer_names(tmp_path: Path) -> None:
    profile = _make_profile()
    out_path, _, _ = generate_thank_you_letter(
        None,
        profile=profile,
        company="Acme",
        discussion_points=["A discussion point."],
        out_path=tmp_path / "thanks.docx",
        root=tmp_path,
    )
    text = _docx_text(out_path)
    assert "Dear Acme Hiring Team," in text


def test_main_cli_end_to_end_without_jd(tmp_path: Path) -> None:
    out_file = tmp_path / "thanks.docx"
    rc = thank_you_main(
        [
            "--company",
            "Acme",
            "--role",
            "Senior Engineer",
            "--interviewer",
            "Jane Doe",
            "--date",
            "August 25, 2026",
            "--discussion-point",
            "We discussed the team's Q3 roadmap.",
            "--out",
            str(out_file),
        ]
    )
    assert rc == 0
    assert out_file.exists()
    text = _docx_text(out_file)
    assert "Jane Doe" in text
    assert "We discussed the team's Q3 roadmap." in text


def test_select_star_story_skips_stories_naming_a_legacy_employer() -> None:
    """The letter goes to an employer; legacy history must never surface automatically."""
    profile = _make_profile(
        star_stories=[
            {
                "title": "T-SQL Automation (Contoso Systems)",
                "situation": "At Contoso Systems, sql patching was manual.",
                "jd_tags": ["sql", "automation", "t-sql"],
            },
            {"title": "SSIS Pipeline", "situation": "sql import job", "jd_tags": ["sql"]},
        ],
        legacy_companies=["Contoso Systems (formerly Fabrikam Systems Inc.)"],
    )
    story = _select_star_story(profile, ["sql", "automation", "t-sql"], [])
    assert story is not None
    assert story.title == "SSIS Pipeline"


def test_select_star_story_unaffected_without_legacy_experience() -> None:
    profile = _make_profile(
        star_stories=[{"title": "Contoso Story", "situation": "Contoso Systems sql", "jd_tags": []}]
    )
    story = _select_star_story(profile, ["sql"], [])
    assert story is not None and story.title == "Contoso Story"
