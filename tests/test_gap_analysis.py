"""Tests for src/jobomatic/commands/gap_analysis.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobomatic.commands import gap_analysis
from jobomatic.fit.engine import FitResult, SkillMatch


@pytest.fixture(scope="module")
def g():
    return gap_analysis


def test_format_header_meta_omits_absent_parts(g):
    assert g._format_header_meta("Contoso", None, None) == "Contoso"
    assert g._format_header_meta("Contoso", "Remote", None) == "Contoso — Remote"
    assert g._format_header_meta("Contoso", None, "REQ-1") == "Contoso — REQ-1"
    assert g._format_header_meta("Contoso", "Remote", "REQ-1") == "Contoso — Remote · REQ-1"


def test_render_report_header_includes_location_and_job_id(g):
    result = FitResult(rating="Strong", required=[], nice_to_have=[], rationale="")
    report = g._render_report("Backend Dev", "Contoso", result, "Remote", "REQ-1")
    assert "**Contoso — Remote · REQ-1**" in report


def test_render_report_header_omits_location_and_job_id_gracefully(g):
    result = FitResult(rating="Strong", required=[], nice_to_have=[], rationale="")
    report = g._render_report("Backend Dev", "Contoso", result)
    assert "**Contoso**" in report
    assert " — " not in report.splitlines()[1]


def test_how_to_frame_the_application_differs_across_skill_sets(g):
    """The old version emitted identical boilerplate for every job; this must
    now be genuinely per-application content."""
    result_a = FitResult(
        rating="Strong",
        required=[
            SkillMatch("Azure", "match", "Contoso: production"),
            SkillMatch("Kubernetes", "gap", "no evidence"),
        ],
        nice_to_have=[],
        rationale="",
    )
    result_b = FitResult(
        rating="Good",
        required=[
            SkillMatch("Python", "course", "coursework or self-study"),
            SkillMatch("React", "portfolio", "Demo: portfolio"),
        ],
        nice_to_have=[SkillMatch("GraphQL", "portfolio", "Demo: portfolio")],
        rationale="",
    )
    report_a = g._render_report("Role A", "Company A", result_a)
    report_b = g._render_report("Role B", "Company B", result_b)

    def _how_to_frame(report: str) -> str:
        return report.split("## How to Frame the Application")[1]

    frame_a = _how_to_frame(report_a)
    frame_b = _how_to_frame(report_b)
    assert frame_a != frame_b
    assert "Azure" in frame_a
    assert "Kubernetes" in frame_a
    assert "Python" in frame_b
    assert "React" in frame_b


def test_recommendations_required_portfolio_skill_gets_emphasize_bucket(g):
    """A required skill backed only by portfolio evidence used to match no
    branch at all (only gap/course/"portfolio and in nice") and silently
    got no recommendation, despite the Framing Gaps section already
    flagging it as needing attention."""
    required = [SkillMatch("Docker", "portfolio", "CookingTime: portfolio")]
    recs = g._recommendations(required, [])
    assert recs["emphasize_required_portfolio"] == ["Docker"]
    assert "Docker" not in recs["position_as_nice_to_have"]
    assert "Docker" not in recs["close_with_portfolio"]


def test_recommendations_nice_to_have_gap_not_mislabeled_as_required(g):
    """A nice-to-have "gap" skill used to land in close_with_portfolio
    alongside genuine required gaps, under report text that explicitly
    calls that bucket's contents "required skills" — mislabeling an
    optional gap as a candidacy blocker."""
    recs = g._recommendations([], [SkillMatch("Rust", "gap", "no evidence")])
    assert recs["close_with_portfolio"] == []


def test_render_report_required_portfolio_section_and_no_mislabeled_gap(g):
    result = FitResult(
        rating="Good",
        required=[
            SkillMatch("Azure", "match", "Contoso: production"),
            SkillMatch("Docker", "portfolio", "CookingTime: portfolio"),
        ],
        nice_to_have=[SkillMatch("Rust", "gap", "no evidence")],
        rationale="",
    )
    report = g._render_report("Role", "Company", result)
    recommendations = report.split("## Recommendations")[1].split("## How to Frame")[0]
    assert "Emphasize portfolio evidence for required skills" in recommendations
    assert "Docker" in recommendations
    # The nice-to-have gap ("Rust") must not appear under text that calls
    # it a required skill.
    assert "Close with portfolio evidence" not in recommendations
    assert "Rust" not in recommendations


def test_resume_tailoring_priorities_name_actual_skills_not_boilerplate(g):
    recs = {
        "close_with_portfolio": ["Kubernetes"],
        "close_with_course": ["Python"],
        "position_as_nice_to_have": ["GraphQL"],
    }
    result = FitResult(
        rating="Good",
        required=[
            SkillMatch("Azure", "match", "Contoso: production"),
            SkillMatch("Python", "course", "coursework or self-study"),
            SkillMatch("Kubernetes", "gap", "no evidence"),
        ],
        nice_to_have=[SkillMatch("GraphQL", "portfolio", "Demo: portfolio")],
        rationale="",
    )
    actions = g._resume_tailoring_priorities(result, recs)
    joined = " ".join(actions)
    assert "Azure" in joined
    assert "Python" in joined
    assert "Kubernetes" in joined
    assert "GraphQL" in joined
    # No leftover fixed boilerplate from the old version.
    assert "Lead with production evidence that maps to required skills." not in actions


def test_cover_letter_angle_uses_matched_skill_and_evidence_sources_not_fixed_template(g):
    result = FitResult(
        rating="Strong",
        required=[SkillMatch("Azure", "match", "Contoso: production")],
        nice_to_have=[],
        rationale="",
    )
    angle = g._cover_letter_angle("Contoso", result)
    assert "Azure" in angle
    assert "Contoso" in angle
    # No leftover fixed boilerplate sentence from the old version.
    assert "2–3 proof points from production or portfolio work" not in angle


def test_main_missing_profile_returns_clean_error_not_crash(
    g, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """bootstrap.load_profile(ROOT) used to run unguarded — a missing/unbuilt
    outputs/the profile (e.g. a fresh checkout before "generate profiles" has ever been run) raised an uncaught FileNotFoundError instead
    of the clean "ERROR: ..." + exit 1 every other failure path in this file
    already uses."""
    jd_path = tmp_path / "jd.md"
    jd_path.write_text("# Some Role\n", encoding="utf-8")
    monkeypatch.setattr(g, "ROOT", tmp_path / "no-such-root")

    rc = g.main([str(jd_path), "--out", str(tmp_path / "out.md")])

    assert rc == 1
    err = capsys.readouterr().err
    assert "ERROR" in err
    assert not (tmp_path / "out.md").exists()


def test_render_report_handles_legacy_status(g):
    """A legacy match must not KeyError and must get its own section + recommendation."""
    legacy = SkillMatch("powerbuilder", "legacy", "OldCo (2003 – 2005): legacy experience")
    result = FitResult(rating="Good", required=[legacy], nice_to_have=[legacy], rationale="")
    report = g._render_report("PB Dev", "Contoso", result)
    assert "| powerbuilder | 🕰️ Legacy |" in report
    assert "## 🕰️ Legacy Experience" in report
    assert "### Decide whether to surface legacy experience" in report
    legacy_section = report.split("## 🕰️ Legacy Experience")[1].split("## 🔴")[0]
    assert "**powerbuilder**" in legacy_section
    assert "Earlier Experience addendum" in report


def test_render_report_shows_location_section_when_disqualified(g):
    from jobomatic.fit.location import LocationAssessment

    result = FitResult(
        rating="Pass",
        required=[SkillMatch("c#", "match", "Acme: production")],
        nice_to_have=[],
        rationale="Outside job-search constraints",
        skill_rating="Strong",
        location_disqualifiers=("Hybrid role outside Springfield (Toronto)",),
        location_flags=("Hybrid with no stated city",),
    )
    report = g._render_report("Dev", "Contoso", result)
    assert "## Overall Fit: Pass" in report
    assert "## Location & Work Arrangement" in report
    assert "- 🚫 Hybrid role outside Springfield (Toronto)" in report
    assert "- ⚠️ Hybrid with no stated city" in report
    assert "driven by location, not skills" in report
    assert "skills alone would rate Strong" in report
    assert LocationAssessment  # imported for parity with the engine's public type


def test_render_report_omits_location_section_when_clean(g):
    result = FitResult(rating="Strong", required=[], nice_to_have=[], rationale="")
    assert "Location & Work Arrangement" not in g._render_report("Dev", "Contoso", result)


def test_render_report_flags_only_do_not_claim_location_pass(g):
    result = FitResult(
        rating="Good",
        required=[],
        nice_to_have=[],
        rationale="",
        location_flags=("Confirm Midland residents are eligible",),
    )
    report = g._render_report("Dev", "Contoso", result)
    assert "## Location & Work Arrangement" in report
    assert "driven by location" not in report


def test_render_report_lists_unscored_required_lines(g):
    result = FitResult(
        rating="Good",
        required=[SkillMatch("azure", "match", "Acme: production")],
        nice_to_have=[],
        rationale="",
        unscored_required=("Computer science degree or equivalent practical experience",),
    )
    report = g._render_report("Dev", "Contoso", result)
    assert "### Required lines not scored" in report
    assert "- Computer science degree or equivalent practical experience" in report


def test_render_report_omits_unscored_section_when_none(g):
    result = FitResult(rating="Good", required=[], nice_to_have=[], rationale="")
    assert "Required lines not scored" not in g._render_report("Dev", "Contoso", result)


def test_render_report_lists_terms_to_confirm(g):
    result = FitResult(
        rating="Good",
        required=[SkillMatch("azure", "match", "Acme: production")],
        nice_to_have=[],
        rationale="",
        terms_to_confirm=(("solid", "Solid understanding of CI/CD practices"),),
    )
    report = g._render_report("Dev", "Contoso", result)
    assert "### Terms to confirm" in report
    assert '- "solid" in: Solid understanding of CI/CD practices' in report


def test_render_report_lists_possible_typos(g):
    result = FitResult(
        rating="Good",
        required=[SkillMatch("azure", "match", "Acme: production")],
        nice_to_have=[],
        rationale="",
        possible_typos=(("Typscript", "typescript", "Experience with Typscript"),),
    )
    report = g._render_report("Dev", "Contoso", result)
    assert "### Possible typos" in report
    assert '- "Typscript" may be "typescript" in: Experience with Typscript' in report


def test_render_report_lists_names_to_check(g):
    result = FitResult(
        rating="Good",
        required=[SkillMatch("azure", "match", "Acme: production")],
        nice_to_have=[],
        rationale="",
        unknown_names=(("Frobnicator", "tools such as Frobnicator"),),
    )
    report = g._render_report("Dev", "Contoso", result)
    assert "### Names to check" in report
    assert '- "Frobnicator" in: tools such as Frobnicator' in report
