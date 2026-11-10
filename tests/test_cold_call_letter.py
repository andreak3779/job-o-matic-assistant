"""Unit tests for the cold-call letter generator's evidence grounding."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from docx import Document

REPO_ROOT = Path(__file__).resolve().parents[1]

from jobomatic.commands.cold_call import (
    _empty_fit_result,
    _read_target_description,
    _select_evidence,
    generate_cold_call_letter,
)
from tests.profile_fixtures import Contact, Project, SkillCategory, make_profile


def _make_profile(
    *,
    differentiators: list[str] | None = None,
    technical_skills: list[tuple[str, list[str]]] | None = None,
    portfolio_projects: list[dict[str, Any]] | None = None,
) -> Any:
    """A minimal profile for testing."""
    return make_profile(
        contact=Contact(name="Sarah Ashford", email="jordan@example.com"),
        headline="Full-Stack Engineer",
        differentiators=differentiators,
        technical_skills=[SkillCategory(category=c, skills=sk) for c, sk in technical_skills or []],
        portfolio_projects=[
            Project(
                name=p.get("name", ""),
                description=p.get("description", ""),
                stack=p.get("stack", []),
                url="https://example.com/p",
            )
            for p in portfolio_projects or []
        ],
        experience=[],
        ats_keywords={},
    )


def test_select_evidence_uses_differentiators_and_portfolio() -> None:
    profile = _make_profile(
        differentiators=[
            "Full-stack depth: built SPAs and APIs end to end",
            "Cloud-native with Azure",
        ],
        portfolio_projects=[
            {"name": "MoviesApp", "description": "A movie catalog", "stack": ["React", "Node"]}
        ],
    )
    evidence = _select_evidence(profile, "Acme")

    assert "Acme" in evidence["hook"]
    assert "Full-stack depth" in evidence["hook"]
    assert len(evidence["bring"]) == 2
    assert evidence["bring"][0]["label"] == "Full-stack depth"
    assert "MoviesApp" in evidence["portfolio_highlight"]
    assert "evidence_sources" in evidence
    assert "MoviesApp" in evidence["evidence_sources"]
    assert not evidence["low_confidence"]


def test_select_evidence_falls_back_when_sparse() -> None:
    profile = _make_profile(
        technical_skills=[("Languages", ["Python", "TypeScript"])],
    )
    evidence = _select_evidence(profile, "Acme")

    assert "interested in" in evidence["hook"] or "could fit" in evidence["hook"]
    assert len(evidence["bring"]) == 1
    assert "Background includes" in evidence["bring"][0]["body"]
    assert "Hands-on with" not in evidence["bring"][0]["body"]
    assert evidence["low_confidence"]


def test_empty_fit_result_is_stretch_with_no_matches() -> None:
    result = _empty_fit_result()
    assert result.rating == "Stretch"
    assert result.required == []
    assert result.nice_to_have == []


def test_generate_cold_call_letter_writes_sidecar(tmp_path: Path) -> None:
    profile = _make_profile(
        differentiators=["Full-stack depth: built SPAs and APIs end to end"],
        portfolio_projects=[
            {"name": "MoviesApp", "description": "A movie catalog", "stack": ["React", "Node"]}
        ],
    )
    jd_path = tmp_path / "target.md"
    jd_path.write_text("# About Acme\n\nAcme builds cloud software.", encoding="utf-8")

    out_path, sidecar_path, result = generate_cold_call_letter(
        jd_path,
        profile=profile,
        company="Acme",
        out_path=tmp_path / "cold.docx",
        root=tmp_path,
    )

    assert out_path.exists()
    assert sidecar_path.exists()
    meta = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert meta["script"] == "generate_cold_call_letter.py"
    assert "MoviesApp" in meta["evidence_sources"]
    assert meta["warnings"] == []


def test_generate_cold_call_letter_warns_when_low_confidence(capsys, tmp_path: Path) -> None:
    profile = _make_profile(technical_skills=[("Languages", ["Python"])])
    jd_path = tmp_path / "target.md"
    jd_path.write_text("# About Acme\n\nAcme builds cloud software.", encoding="utf-8")

    generate_cold_call_letter(
        jd_path,
        profile=profile,
        company="Acme",
        out_path=tmp_path / "cold.docx",
        root=tmp_path,
    )

    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "low evidence" in captured.err.lower() or "manually review" in captured.err.lower()


# ── No-JD conversational flow (Phase 3: input-model fix) ────────────────────


def test_read_target_description_with_no_path_defaults_gracefully() -> None:
    company, description = _read_target_description(None)
    assert company == "Your Company"
    assert description == ""


def test_select_evidence_includes_role_type_in_hook() -> None:
    profile = _make_profile(
        differentiators=["Full-stack depth: built SPAs and APIs end to end"],
    )
    evidence = _select_evidence(profile, "Acme", role_type="Senior .NET Developer roles")
    assert "Senior .NET Developer roles" in evidence["hook"]


def test_select_evidence_omits_role_clause_when_not_given() -> None:
    profile = _make_profile(differentiators=["Full-stack depth"])
    evidence = _select_evidence(profile, "Acme")
    assert "roles" not in evidence["hook"].lower()


def _docx_text(path: Path) -> str:
    return "\n".join(p.text for p in Document(str(path)).paragraphs)


def test_generate_cold_call_letter_without_jd_uses_recruiter_and_role_type(
    tmp_path: Path,
) -> None:
    """The core Phase 3 fix: no JD file needed — recruiter_name/role_type
    drive the salutation, Re: line, and hook directly."""
    profile = _make_profile(
        differentiators=["Full-stack depth: built SPAs and APIs end to end"],
    )

    out_path, sidecar_path, result = generate_cold_call_letter(
        None,
        profile=profile,
        company="Acme",
        recruiter_name="Jane Doe",
        role_type="Senior .NET Developer roles",
        out_path=tmp_path / "cold.docx",
        root=tmp_path,
    )

    assert out_path.exists()
    text = _docx_text(out_path)
    assert "Dear Jane Doe," in text
    assert "Re: Senior .NET Developer roles Opportunities" in text
    assert "Senior .NET Developer roles" in text
    # No JD parsed -> no required skills -> the honest "Stretch, not assessed" default.
    assert result.rationale == "No JD provided — fit not assessed."


def test_generate_cold_call_letter_without_recruiter_name_defaults_to_hiring_team(
    tmp_path: Path,
) -> None:
    profile = _make_profile(differentiators=["Full-stack depth"])
    out_path, _, _ = generate_cold_call_letter(
        None,
        profile=profile,
        company="Acme",
        out_path=tmp_path / "cold.docx",
        root=tmp_path,
    )
    text = _docx_text(out_path)
    assert "Dear Hiring Team," in text


def _job_site_text(projects: list[Project]) -> str:
    from jobomatic.commands.job_site_letter import _build_plain_text

    profile = make_profile(
        contact=Contact(name="Sarah Ashford", email="jordan@example.com"),
        headline="Full-Stack Engineer",
        technical_skills=[],
        portfolio_projects=projects,
        experience=[],
        ats_keywords={},
    )
    return _build_plain_text("SampleCo", "Developer", _empty_fit_result(), profile)


def _project(name: str, *, private: bool) -> Project:
    return Project(
        name=name,
        description="A demo.",
        stack=["C#"],
        url="https://example.com/p",
        repo_private=private,
    )


def test_job_site_letter_skips_a_private_repo_and_names_the_next_project() -> None:
    text = _job_site_text([_project("Hidden", private=True), _project("Open", private=False)])
    assert "recent example in Open" in text
    assert "Hidden" not in text


def test_job_site_letter_drops_the_example_when_every_repo_is_private() -> None:
    text = _job_site_text([_project("Hidden", private=True)])
    assert "recent example" not in text
    assert "Hidden" not in text
