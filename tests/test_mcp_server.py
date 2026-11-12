"""Smoke tests for the MCP server tool wrappers.

Calls each tool function directly (the ``@mcp.tool()`` decorator leaves the
underlying function callable) rather than over a live MCP transport, mirroring
the pattern in ``tests/test_cli_commands.py``.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ContentBlock, EmbeddedResource, TextContent

from jobomatic.interfaces.mcp.server import (
    _attachment_blocks,
    fit_check,
    gap_analysis,
    generate_application_documents,
    generate_cold_call,
    generate_cover_letter,
    generate_github,
    generate_job_board,
    generate_job_site_letter,
    generate_jobgether,
    generate_learning_plan,
    generate_linkedin,
    generate_pluralsight,
    generate_resume,
    generate_thank_you,
    interview_prep,
    validate_profile,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

# The server may write to the system temp directory, so a checkout under it makes the
# "outside the allowed directories" cases legal and the first one would overwrite a source file.
_repo_in_temp = pytest.mark.skipif(
    Path(tempfile.gettempdir()).resolve() in REPO_ROOT.parents,
    reason="the code repository is under the temp directory, which the server may write to",
)
FIXTURE_JD = REPO_ROOT / "tests" / "fixtures" / "sample-jd.md"
# sample-jd.md rates Stretch against the real profile — used throughout this
# file for the many tools that don't gate on fit (unchanged from before).
# strong-fit-jd.md rates Strong — required for generate_resume /
# generate_cover_letter / generate_application_documents, which now refuse
# to generate below Good.
STRONG_FIXTURE_JD = REPO_ROOT / "tests" / "fixtures" / "strong-fit-jd.md"
# Rates Pass: used to prove the fit gate refuses below-Good roles.
WEAK_FIXTURE_JD = REPO_ROOT / "tests" / "fixtures" / "data-engineer-jd.md"


def _embedded_resources(blocks: list[ContentBlock]) -> list[EmbeddedResource]:
    return [b for b in blocks if isinstance(b, EmbeddedResource)]


def _text_blocks(blocks: list[ContentBlock]) -> list[TextContent]:
    return [b for b in blocks if isinstance(b, TextContent)]


def test_fit_check_returns_rating() -> None:
    out = fit_check(str(FIXTURE_JD))
    assert "Fit Check" in out
    assert "Fit Rating:" in out


def test_fit_check_missing_file_raises_tool_error() -> None:
    with pytest.raises(ToolError):
        fit_check(str(REPO_ROOT / "tests" / "fixtures" / "does-not-exist.md"))


def test_fit_check_accepts_inline_jd_text() -> None:
    """A client that pastes/attaches JD text in chat (rather than writing it
    to a file first) passes it straight through as the ``jd`` string — this
    must work the same as passing a file path."""
    jd_text = FIXTURE_JD.read_text(encoding="utf-8")
    out = fit_check(jd_text)
    assert "Fit Check" in out
    assert "Fit Rating:" in out


def test_validate_profile_runs() -> None:
    out = validate_profile()
    assert "Profile valid" in out


def test_gap_analysis_writes_markdown_report(tmp_path: Path) -> None:
    out_file = tmp_path / "GapAnalysis.md"
    blocks = gap_analysis(str(FIXTURE_JD), out=str(out_file))
    assert out_file.exists()
    assert "# Gap Analysis:" in out_file.read_text(encoding="utf-8")
    # The report content itself must come back inline through MCP, not just
    # a "Wrote <path>" status string the client can't do anything with.
    text_blocks = _text_blocks(blocks)
    assert any("# Gap Analysis:" in b.text for b in text_blocks)


def test_generate_linkedin_writes_copy(tmp_path: Path) -> None:
    out_file = tmp_path / "LinkedIn.md"
    blocks = generate_linkedin(out=str(out_file))
    assert out_file.exists()
    assert "# LinkedIn Profile Update Draft" in out_file.read_text(encoding="utf-8")
    # Profile-update tools attach their markdown as a text EmbeddedResource
    # (so MCP clients like Claude Desktop show it as a document rather than
    # dumping it into the chat transcript), not as a plain TextContent block.
    resources = _embedded_resources(blocks)
    assert any(
        r.resource.mime_type == "text/markdown"
        and "# LinkedIn Profile Update Draft" in r.resource.text
        for r in resources
    )
    assert not any("# LinkedIn Profile Update Draft" in b.text for b in _text_blocks(blocks))


def test_generate_github_writes_readme(tmp_path: Path) -> None:
    out_file = tmp_path / "GitHub.md"
    blocks = generate_github(out=str(out_file))
    assert out_file.exists()
    assert "# GitHub Profile Update Draft" in out_file.read_text(encoding="utf-8")
    resources = _embedded_resources(blocks)
    assert any(
        r.resource.mime_type == "text/markdown"
        and "# GitHub Profile Update Draft" in r.resource.text
        for r in resources
    )


def test_generate_jobgether_writes_copy(tmp_path: Path) -> None:
    out_file = tmp_path / "Jobgether.md"
    blocks = generate_jobgether(out=str(out_file))
    assert out_file.exists()
    assert "# Jobgether Profile Update Draft" in out_file.read_text(encoding="utf-8")
    resources = _embedded_resources(blocks)
    assert any(
        r.resource.mime_type == "text/markdown"
        and "# Jobgether Profile Update Draft" in r.resource.text
        for r in resources
    )
    assert not any("# Jobgether Profile Update Draft" in b.text for b in _text_blocks(blocks))


def test_generate_job_board_writes_copy(tmp_path: Path) -> None:
    out_file = tmp_path / "JobBoard.md"
    blocks = generate_job_board(out=str(out_file))
    assert out_file.exists()
    assert "# Indeed & ZipRecruiter Profile Update Draft" in out_file.read_text(encoding="utf-8")
    resources = _embedded_resources(blocks)
    assert any(
        r.resource.mime_type == "text/markdown"
        and "# Indeed & ZipRecruiter Profile Update Draft" in r.resource.text
        for r in resources
    )


def test_generate_pluralsight_writes_copy(tmp_path: Path) -> None:
    out_file = tmp_path / "Pluralsight.md"
    blocks = generate_pluralsight(out=str(out_file))
    assert out_file.exists()
    assert "# Pluralsight Profile Update Draft" in out_file.read_text(encoding="utf-8")
    resources = _embedded_resources(blocks)
    assert any(
        r.resource.mime_type == "text/markdown"
        and "# Pluralsight Profile Update Draft" in r.resource.text
        for r in resources
    )


def test_generate_resume_writes_docx(tmp_path: Path) -> None:
    out_file = tmp_path / "resume.docx"
    blocks = generate_resume(str(STRONG_FIXTURE_JD), company="SampleCo", out=str(out_file))
    assert out_file.exists() and out_file.stat().st_size > 0
    resources = _embedded_resources(blocks)
    assert len(resources) == 1
    assert resources[0].resource.mime_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert base64.b64decode(resources[0].resource.blob) == out_file.read_bytes()


def test_generate_resume_accepts_inline_jd_text(tmp_path: Path) -> None:
    out_file = tmp_path / "resume.docx"
    jd_text = STRONG_FIXTURE_JD.read_text(encoding="utf-8")
    blocks = generate_resume(jd_text, company="SampleCo", out=str(out_file))
    assert out_file.exists() and out_file.stat().st_size > 0
    assert len(_embedded_resources(blocks)) == 1


def test_generate_cover_letter_writes_docx(tmp_path: Path) -> None:
    out_file = tmp_path / "cover.docx"
    blocks = generate_cover_letter(str(STRONG_FIXTURE_JD), company="SampleCo", out=str(out_file))
    assert out_file.exists() and out_file.stat().st_size > 0
    resources = _embedded_resources(blocks)
    assert len(resources) == 1
    assert base64.b64decode(resources[0].resource.blob) == out_file.read_bytes()


def test_generate_resume_below_good_fit_raises_tool_error(tmp_path: Path) -> None:
    out_file = tmp_path / "resume_fail.docx"
    with pytest.raises(ToolError):
        generate_resume(str(WEAK_FIXTURE_JD), company="SampleCo", out=str(out_file))
    assert not out_file.exists()


def test_generate_resume_missing_jd_file_raises_tool_error(tmp_path: Path) -> None:
    """`_require_good_fit`'s missing-file branch, distinct from the
    below-Good-fit refusal above — exercised here directly since no existing
    test called any gated tool with a nonexistent jd path."""
    out_file = tmp_path / "resume_fail.docx"
    with pytest.raises(ToolError, match="job description file not found"):
        generate_resume(
            str(REPO_ROOT / "tests" / "fixtures" / "does-not-exist.md"),
            company="SampleCo",
            out=str(out_file),
        )
    assert not out_file.exists()


def test_generate_cover_letter_below_good_fit_raises_tool_error(tmp_path: Path) -> None:
    out_file = tmp_path / "cover_fail.docx"
    with pytest.raises(ToolError):
        generate_cover_letter(str(WEAK_FIXTURE_JD), company="SampleCo", out=str(out_file))
    assert not out_file.exists()


QUEBEC_STRONG_SKILLS_JD = REPO_ROOT / "tests" / "fixtures" / "strong-skills-quebec-jd.md"
TORONTO_HYBRID_STRONG_SKILLS_JD = (
    REPO_ROOT / "tests" / "fixtures" / "strong-skills-hybrid-toronto-jd.md"
)


def test_fit_check_reports_location_pass_for_strong_skills_in_quebec() -> None:
    out = fit_check(str(QUEBEC_STRONG_SKILLS_JD))
    assert "Fit Rating: Pass" in out
    assert "Quebec-based role" in out


@pytest.mark.parametrize("jd", [QUEBEC_STRONG_SKILLS_JD, TORONTO_HYBRID_STRONG_SKILLS_JD])
def test_generate_resume_refuses_location_pass_even_with_strong_skills(
    tmp_path: Path, jd: Path
) -> None:
    out_file = tmp_path / "resume_location.docx"
    with pytest.raises(ToolError, match="job-search location rules"):
        generate_resume(str(jd), company="SampleCo", out=str(out_file))
    assert not out_file.exists()


@pytest.mark.parametrize("jd", [QUEBEC_STRONG_SKILLS_JD, TORONTO_HYBRID_STRONG_SKILLS_JD])
def test_generate_cover_letter_and_application_documents_refuse_location_pass(
    tmp_path: Path, jd: Path
) -> None:
    out_file = tmp_path / "cover_location.docx"
    with pytest.raises(ToolError, match="job-search location rules"):
        generate_cover_letter(str(jd), company="SampleCo", out=str(out_file))
    assert not out_file.exists()
    with pytest.raises(ToolError, match="job-search location rules"):
        generate_application_documents(str(jd), company="SampleCo")


def test_generate_application_documents_returns_both_docs() -> None:
    blocks = generate_application_documents(str(STRONG_FIXTURE_JD), company="SampleCo")
    resources = _embedded_resources(blocks)
    assert len(resources) == 2
    for resource in resources:
        assert resource.resource.mime_type == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert len(resource.resource.blob) > 0
    text_blocks = _text_blocks(blocks)
    assert any(b.text.startswith("Fit Rating: Strong") for b in text_blocks)


def test_generate_application_documents_below_good_fit_raises_tool_error() -> None:
    with pytest.raises(ToolError):
        generate_application_documents(str(WEAK_FIXTURE_JD), company="SampleCo")


def test_generate_cold_call_writes_docx(tmp_path: Path) -> None:
    out_file = tmp_path / "cold_call.docx"
    generate_cold_call(str(FIXTURE_JD), company="SampleCo", out=str(out_file))
    assert out_file.exists() and out_file.stat().st_size > 0


def test_generate_cold_call_without_jd_uses_recruiter_and_role_type(tmp_path: Path) -> None:
    """The Phase 3 fix: no JD needed via MCP either."""
    out_file = tmp_path / "cold_call_no_jd.docx"
    generate_cold_call(
        recruiter_name="Jane Doe",
        role_type="Senior .NET Developer roles",
        out=str(out_file),
    )
    assert out_file.exists() and out_file.stat().st_size > 0


def test_generate_job_site_letter_writes_txt(tmp_path: Path) -> None:
    out_file = tmp_path / "job_site.txt"
    generate_job_site_letter(str(FIXTURE_JD), company="SampleCo", out=str(out_file))
    assert out_file.exists() and len(out_file.read_text(encoding="utf-8")) > 0


def test_generate_thank_you_writes_docx(tmp_path: Path) -> None:
    out_file = tmp_path / "thank_you.docx"
    generate_thank_you(
        str(FIXTURE_JD),
        company="SampleCo",
        discussion_points=["We discussed the team's roadmap."],
        out=str(out_file),
    )
    assert out_file.exists() and out_file.stat().st_size > 0


def test_generate_thank_you_without_discussion_points_raises_tool_error(tmp_path: Path) -> None:
    out_file = tmp_path / "thank_you_fail.docx"
    with pytest.raises(ToolError):
        generate_thank_you(str(FIXTURE_JD), company="SampleCo", out=str(out_file))
    assert not out_file.exists()


def test_generate_thank_you_without_jd_uses_recruiter_style_inputs(tmp_path: Path) -> None:
    out_file = tmp_path / "thank_you_no_jd.docx"
    generate_thank_you(
        company="SampleCo",
        role="Senior .NET Developer",
        interviewers=["Jane Doe"],
        date="August 25, 2026",
        discussion_points=["We discussed the team's roadmap."],
        out=str(out_file),
    )
    assert out_file.exists() and out_file.stat().st_size > 0


def test_interview_prep_writes_docx(tmp_path: Path) -> None:
    out_file = tmp_path / "InterviewPrep.docx"
    interview_prep(str(FIXTURE_JD), out=str(out_file))
    assert out_file.exists() and out_file.stat().st_size > 0


def test_interview_prep_stage_flag_accepted(tmp_path: Path) -> None:
    out_file = tmp_path / "InterviewPrep.docx"
    interview_prep(str(FIXTURE_JD), stage="phone_screen", out=str(out_file))
    assert out_file.exists() and out_file.stat().st_size > 0


def test_interview_prep_invalid_stage_raises_tool_error(tmp_path: Path) -> None:
    """An unknown stage is an error result from the command, which the tool reports as a
    client-facing ToolError (there is no ``argparse`` to exit and crash the long-running server)."""
    out_file = tmp_path / "InterviewPrep.docx"
    with pytest.raises(ToolError):
        interview_prep(str(FIXTURE_JD), stage="not-a-real-stage", out=str(out_file))
    assert not out_file.exists()


def test_interview_prep_update_star_bank_flag_accepted(tmp_path: Path) -> None:
    """Runs against the throwaway demo vault, never a real one."""
    out_file = tmp_path / "InterviewPrep.docx"

    interview_prep(str(FIXTURE_JD), out=str(out_file), update_star_bank=True)
    assert out_file.exists() and out_file.stat().st_size > 0


def test_interview_prep_hybrid_content_flags_accepted(tmp_path: Path) -> None:
    company_research_file = tmp_path / "company-research.md"
    company_research_file.write_text("SampleCo just closed a Series B.", encoding="utf-8")
    recruiter_briefing_file = tmp_path / "recruiter-briefing.md"
    recruiter_briefing_file.write_text("Two rounds, technical then panel.", encoding="utf-8")
    qa_cards_file = tmp_path / "qa-cards.json"
    qa_cards_file.write_text(
        json.dumps([{"question": "Walk me through your resume.", "answer": "..."}]),
        encoding="utf-8",
    )
    salary_section_file = tmp_path / "salary.md"
    salary_section_file.write_text("Target range: $120K-$140K CAD.", encoding="utf-8")
    out_file = tmp_path / "InterviewPrep.docx"

    interview_prep(
        str(FIXTURE_JD),
        out=str(out_file),
        stage="final_round",
        company_research_path=str(company_research_file),
        recruiter_briefing_path=str(recruiter_briefing_file),
        qa_cards_path=str(qa_cards_file),
        salary_section_path=str(salary_section_file),
    )
    assert out_file.exists() and out_file.stat().st_size > 0


def test_interview_prep_malformed_qa_cards_json_raises_tool_error(tmp_path: Path) -> None:
    qa_cards_file = tmp_path / "qa-cards.json"
    qa_cards_file.write_text("{not valid json", encoding="utf-8")
    out_file = tmp_path / "InterviewPrep.docx"

    with pytest.raises(ToolError):
        interview_prep(str(FIXTURE_JD), out=str(out_file), qa_cards_path=str(qa_cards_file))
    assert not out_file.exists()


def test_generate_learning_plan_returns_pdf_bytes(tmp_path: Path) -> None:
    example = REPO_ROOT / "templates" / "roles" / "_example.json"
    cfg = json.loads(example.read_text(encoding="utf-8"))
    cfg["output"] = str(tmp_path / "smoke.pdf")
    cfg_path = tmp_path / "smoke.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    blocks = generate_learning_plan(str(cfg_path))
    out_file = tmp_path / "smoke.pdf"
    assert out_file.exists() and out_file.stat().st_size > 0

    resources = _embedded_resources(blocks)
    assert len(resources) == 1
    assert resources[0].resource.mime_type == "application/pdf"
    assert base64.b64decode(resources[0].resource.blob).startswith(b"%PDF")


def test_attachment_blocks_skips_a_listed_file_that_is_not_there(tmp_path: Path) -> None:
    """A "Wrote <path>" line whose path doesn't resolve to a real file (e.g.
    a status trailer like `build`'s "Wrote outputs/the profile (v29)"
    that isn't itself a "Wrote <artifact>" convention line) must be skipped,
    not raise."""
    missing = tmp_path / "does-not-exist.docx"
    blocks = _attachment_blocks([missing])
    assert _embedded_resources(blocks) == []


def test_attachment_blocks_handles_unreadable_file_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An OSError while reading back a just-written artifact (permissions,
    race, odd encoding) must degrade to an inline text note, not propagate
    and take down attachments that already succeeded."""
    doc = tmp_path / "resume.docx"
    doc.write_bytes(b"not a real docx, just needs to exist")

    def _raise_oserror(self: Path) -> bytes:
        raise OSError("simulated read failure")

    monkeypatch.setattr(Path, "read_bytes", _raise_oserror)
    blocks = _attachment_blocks([doc])
    assert _embedded_resources(blocks) == []
    assert any("could not attach" in b.text for b in _text_blocks(blocks))


# ── Location-only gate on the skill-ungated letter tools (ADR 0008) ──────────


def test_generate_job_site_letter_refuses_location_pass(tmp_path: Path) -> None:
    out_file = tmp_path / "job_site_location.txt"
    with pytest.raises(ToolError, match="outside the job-search location rules"):
        generate_job_site_letter(
            str(QUEBEC_STRONG_SKILLS_JD), company="SampleCo", out=str(out_file)
        )
    assert not out_file.exists()


def test_generate_job_site_letter_still_ignores_skill_fit(tmp_path: Path) -> None:
    """The location gate must not turn into a skill gate: sample-jd.md rates
    Stretch on skills but its location is fine, so the letter is still written."""
    out_file = tmp_path / "job_site_stretch.txt"
    generate_job_site_letter(str(FIXTURE_JD), company="SampleCo", out=str(out_file))
    assert out_file.exists()


def test_generate_cold_call_with_jd_refuses_location_pass(tmp_path: Path) -> None:
    out_file = tmp_path / "cold_call_location.docx"
    with pytest.raises(ToolError, match="outside the job-search location rules"):
        generate_cold_call(
            str(TORONTO_HYBRID_STRONG_SKILLS_JD), company="SampleCo", out=str(out_file)
        )
    assert not out_file.exists()


def test_generate_cold_call_without_jd_is_unaffected(tmp_path: Path) -> None:
    out_file = tmp_path / "cold_call_no_jd.docx"
    generate_cold_call(recruiter_name="Jane Doe", role_type="Senior .NET roles", out=str(out_file))
    assert out_file.exists() and out_file.stat().st_size > 0


def test_location_gate_error_names_the_reason(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="Quebec-based role") as excinfo:
        generate_job_site_letter(str(QUEBEC_STRONG_SKILLS_JD), out=str(tmp_path / "x.txt"))
    assert "Skills are not the blocker" in str(excinfo.value)


def test_thank_you_and_interview_prep_are_deliberately_not_location_gated(tmp_path: Path) -> None:
    """Both only make sense once an interview is already underway — a location
    heuristic must never block a thank-you note or interview preparation."""
    thank_you = tmp_path / "thank_you.docx"
    generate_thank_you(
        str(QUEBEC_STRONG_SKILLS_JD),
        company="SampleCo",
        discussion_points=["We discussed the team's roadmap."],
        out=str(thank_you),
    )
    assert thank_you.exists()
    prep = tmp_path / "prep.docx"
    interview_prep(str(QUEBEC_STRONG_SKILLS_JD), out=str(prep))
    assert prep.exists()


def test_location_gate_missing_jd_file_raises_tool_error(tmp_path: Path) -> None:
    with pytest.raises(ToolError):
        generate_job_site_letter(
            str(REPO_ROOT / "tests" / "fixtures" / "does-not-exist.md"), out=str(tmp_path / "x.txt")
        )


# ── path allow-list (prompt-injection hardening) ─────────────────────────────


def test_out_path_outside_allowed_roots_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="outside the directories"):
        generate_linkedin(out=str(Path.home() / "pwned.md"))


@_repo_in_temp
def test_out_path_cannot_overwrite_source_files_inside_the_repo() -> None:
    with pytest.raises(ToolError, match="outside the directories"):
        generate_linkedin(out=str(REPO_ROOT / "src" / "jobomatic" / "fit" / "engine.py"))


def test_jd_path_outside_allowed_roots_is_refused() -> None:
    with pytest.raises(ToolError, match="outside the directories"):
        fit_check("/etc/passwd")


def test_optional_input_paths_outside_allowed_roots_are_refused() -> None:
    with pytest.raises(ToolError, match="outside the directories"):
        interview_prep(str(FIXTURE_JD), qa_cards_path="/etc/passwd")


def test_extra_allowed_dir_is_honoured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from jobomatic.interfaces.mcp import server

    extra = tmp_path / "extra"
    extra.mkdir()
    monkeypatch.setenv("JOBOMATIC_ALLOWED_DIRS", str(extra))
    assert server._checked_path(str(extra / "x.md"), write=True, label="out").endswith("x.md")


@_repo_in_temp
def test_a_job_description_in_the_code_repository_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JOBOMATIC_ALLOWED_DIRS")  # the suite opts tests/fixtures in
    with pytest.raises(ToolError, match="outside the directories this server may read from"):
        fit_check(str(FIXTURE_JD))


def test_a_job_description_in_an_extra_allowed_dir_is_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    extra = tmp_path / "postings"
    extra.mkdir()
    (extra / "jd.md").write_text(FIXTURE_JD.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("JOBOMATIC_ALLOWED_DIRS", str(extra))
    assert "Fit Rating:" in fit_check(str(extra / "jd.md"))


@pytest.mark.parametrize("where", ["private", "applications log", "vault git"])
def test_protected_vault_locations_are_refused_even_inside_an_allowed_dir(
    monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    from jobomatic import paths

    target = {
        "private": paths.private_dir() / "search-constraints.json",
        "applications log": paths.applications_log(),
        "vault git": paths.vault_root() / ".git" / "config",
    }[where]
    # Even when the client is allowed the whole folder that holds them.
    monkeypatch.setenv("JOBOMATIC_ALLOWED_DIRS", os.pathsep.join([str(target.parent.parent)]))
    with pytest.raises(ToolError, match="outside the directories this server may read from"):
        fit_check(str(target))


def test_wrote_line_for_a_file_outside_write_roots_is_not_attached(tmp_path: Path) -> None:
    from jobomatic.interfaces.mcp import server

    secret = Path.home() / ".claude-jobs-test-secret.txt"
    # The file does not need to exist: the allow-list check runs first and must reject it.
    blocks = server._attachment_blocks([secret])
    assert blocks == []


@_repo_in_temp
def test_generate_learning_plan_rejects_output_outside_write_roots(tmp_path: Path) -> None:
    example = REPO_ROOT / "templates" / "roles" / "_example.json"
    cfg = json.loads(example.read_text(encoding="utf-8"))
    target = REPO_ROOT / "shared" / "should_not_be_written.pdf"
    cfg["output"] = str(target)
    cfg_path = tmp_path / "evil.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    with pytest.raises(ToolError, match="output"):
        generate_learning_plan(str(cfg_path))
    assert not target.exists()


def test_unknown_user_tilde_path_is_a_tool_error() -> None:
    with pytest.raises(ToolError):
        interview_prep(str(FIXTURE_JD), out="~no_such_user_xyz/out.docx")


def test_server_announces_its_title_and_icons() -> None:
    from jobomatic.interfaces.mcp.server import mcp, server_icons

    assert mcp.title == "Job-O-Matic Assistant"
    icons = server_icons()
    assert [i.mime_type for i in icons] == ["image/svg+xml", "image/png"]
    for icon in icons:
        header, _, payload = icon.src.partition(",")
        assert header == f"data:{icon.mime_type};base64"
        assert base64.b64decode(payload)  # a real, non-empty file
    assert mcp.icons == icons


def test_mcp_json_registers_the_server_under_its_own_name() -> None:
    from jobomatic.interfaces.mcp.server import mcp

    config = json.loads((Path(__file__).resolve().parents[1] / ".mcp.json").read_text("utf-8"))
    assert list(config["mcpServers"]) == [mcp.name]
