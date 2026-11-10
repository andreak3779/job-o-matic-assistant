"""MCP gate behaviour for the applications log and the salary screen (ADR 0010, 0011)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import TextContent

from jobomatic import applications as apps
from jobomatic.interfaces.mcp.server import (
    applications_check,
    applications_list,
    applications_mark_applied,
    applications_set_status,
    fit_check,
    generate_application_documents,
    generate_cover_letter,
    generate_job_site_letter,
    generate_resume,
    generate_thank_you,
    interview_prep,
    search_constraints,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
STRONG = REPO_ROOT / "tests" / "fixtures" / "strong-fit-jd.md"


def _texts(blocks) -> str:
    return "\n".join(b.text for b in blocks if isinstance(b, TextContent))


def _set_constraints(scratch: Path) -> None:
    private = scratch / "private"
    private.mkdir(exist_ok=True)
    (private / "search-constraints.json").write_text(
        '{"min_permanent_base_cad": 85000, "min_contract_hourly_cad": 60}', encoding="utf-8"
    )


def _strong_jd_with_pay(tmp_path: Path, pay: str) -> Path:
    path = tmp_path / "strong-with-pay.md"
    path.write_text(STRONG.read_text(encoding="utf-8") + f"\n\n## Compensation\n{pay}\n")
    return path


def _applied_recently(jd: Path, days: int = 5) -> str:
    when = (date.today() - timedelta(days=days)).isoformat()
    apps.record_draft(jd.read_text(encoding="utf-8"))
    [app] = apps.load_applications()
    apps.mark_applied(app.id, when)
    return app.id


# ── duplicate gate ───────────────────────────────────────────────────────────


def test_duplicate_application_is_refused_with_guidance(tmp_path: Path) -> None:
    _applied_recently(STRONG)
    with pytest.raises(ToolError) as excinfo:
        generate_resume(str(STRONG), out=str(tmp_path / "r.docx"))
    message = str(excinfo.value)
    assert "DUPLICATE" in message and "confirm_reapply=true" in message
    assert "referral" in message
    assert not (tmp_path / "r.docx").exists()


@pytest.mark.parametrize("tool", [generate_resume, generate_cover_letter])
def test_duplicate_gate_applies_to_resume_and_cover_letter(tool, tmp_path: Path) -> None:
    _applied_recently(STRONG)
    with pytest.raises(ToolError, match="DUPLICATE"):
        tool(str(STRONG), out=str(tmp_path / "x.docx"))


def test_duplicate_gate_applies_to_application_documents_and_job_site_letter(
    tmp_path: Path,
) -> None:
    _applied_recently(STRONG)
    with pytest.raises(ToolError, match="DUPLICATE"):
        generate_application_documents(str(STRONG))
    with pytest.raises(ToolError, match="DUPLICATE"):
        generate_job_site_letter(str(STRONG), out=str(tmp_path / "j.txt"))


def test_confirm_reapply_overrides_the_duplicate_gate(tmp_path: Path) -> None:
    _applied_recently(STRONG)
    out = tmp_path / "r.docx"
    blocks = generate_resume(str(STRONG), out=str(out), confirm_reapply=True)
    assert out.exists() and "DUPLICATE" in _texts(blocks)  # still surfaced as a note


def test_a_draft_alone_does_not_block_regeneration(tmp_path: Path) -> None:
    generate_resume(str(STRONG), out=str(tmp_path / "a.docx"))
    generate_resume(str(STRONG), out=str(tmp_path / "b.docx"))  # no error: never applied
    [app] = apps.load_applications()
    assert app.status == "drafted"


def test_repeat_outside_the_window_is_a_note_not_a_refusal(tmp_path: Path) -> None:
    apps.record_draft(STRONG.read_text(encoding="utf-8"))
    [app] = apps.load_applications()
    apps.mark_applied(app.id, "2025-01-01")
    out = tmp_path / "r.docx"
    blocks = generate_resume(str(STRONG), out=str(out))
    assert out.exists() and "REPEAT" in _texts(blocks)


def test_thank_you_and_interview_prep_are_not_blocked_by_an_existing_application(
    tmp_path: Path,
) -> None:
    """You apply first and are then interviewed — these must keep working."""
    _applied_recently(STRONG)
    generate_thank_you(
        str(STRONG),
        out=str(tmp_path / "t.docx"),
        discussion_points=["We discussed sprint priorities."],
    )
    interview_prep(str(STRONG), out=str(tmp_path / "i.docx"))


def test_a_corrupt_log_stops_generation_instead_of_being_ignored(
    tmp_path: Path, _isolate_personal_data
) -> None:
    (_isolate_personal_data / "applications.jsonl").write_text("{broken\n")
    with pytest.raises(ToolError, match="applications log is unreadable"):
        generate_resume(str(STRONG), out=str(tmp_path / "r.docx"))


# ── salary gate ──────────────────────────────────────────────────────────────


def test_pay_below_minimum_is_refused_until_confirmed(
    tmp_path: Path, _isolate_personal_data
) -> None:
    _set_constraints(_isolate_personal_data)
    jd = _strong_jd_with_pay(tmp_path, "Salary: $60,000 - $72,000 per year")
    with pytest.raises(ToolError) as excinfo:
        generate_resume(str(jd), out=str(tmp_path / "r.docx"))
    assert "Ask the user whether to continue" in str(excinfo.value)
    assert "confirm_below_minimum=true" in str(excinfo.value)
    assert not (tmp_path / "r.docx").exists()

    out = tmp_path / "ok.docx"
    blocks = generate_resume(str(jd), out=str(out), confirm_below_minimum=True)
    assert out.exists() and "below your" in _texts(blocks)


def test_pay_at_or_above_minimum_generates_normally(tmp_path: Path, _isolate_personal_data) -> None:
    _set_constraints(_isolate_personal_data)
    jd = _strong_jd_with_pay(tmp_path, "Salary: $90,000 - $110,000 per year")
    out = tmp_path / "r.docx"
    generate_cover_letter(str(jd), out=str(out))
    assert out.exists()


def test_no_posted_pay_never_blocks(tmp_path: Path, _isolate_personal_data) -> None:
    _set_constraints(_isolate_personal_data)
    out = tmp_path / "r.docx"
    generate_resume(str(STRONG), out=str(out))
    assert out.exists()


def test_without_a_constraints_file_low_pay_does_not_block(tmp_path: Path) -> None:
    jd = _strong_jd_with_pay(tmp_path, "Salary: $40,000 per year")
    out = tmp_path / "r.docx"
    generate_resume(str(jd), out=str(out))
    assert out.exists()


def test_malformed_constraints_stop_generation(tmp_path: Path, _isolate_personal_data) -> None:
    private = _isolate_personal_data / "private"
    private.mkdir()
    (private / "search-constraints.json").write_text('{"min_base": 1}')
    with pytest.raises(ToolError, match="invalid"):
        generate_resume(str(STRONG), out=str(tmp_path / "r.docx"))


def test_salary_is_not_a_gate_for_the_job_site_letter(
    tmp_path: Path, _isolate_personal_data
) -> None:
    _set_constraints(_isolate_personal_data)
    jd = _strong_jd_with_pay(tmp_path, "Salary: $40,000 per year")
    out = tmp_path / "j.txt"
    generate_job_site_letter(str(jd), out=str(out))
    assert out.exists()


def test_fit_check_tool_shows_the_salary_screen(tmp_path: Path, _isolate_personal_data) -> None:
    _set_constraints(_isolate_personal_data)
    jd = _strong_jd_with_pay(tmp_path, "Salary: $60,000 per year")
    assert "Salary screen" in fit_check(str(jd))


# ── applications tools ───────────────────────────────────────────────────────


def test_applications_tools_round_trip(tmp_path: Path) -> None:
    assert "NEW" in applications_check(str(STRONG))
    generate_resume(str(STRONG), out=str(tmp_path / "r.docx"))
    assert "DRAFTED" in applications_check(str(STRONG))

    [app] = apps.load_applications()
    assert "drafted" in applications_list(status="drafted")

    out = applications_mark_applied(jd=str(STRONG), date="2026-10-01")
    assert "Marked applied on 2026-10-01" in out
    assert apps.get_application(app.id).status == "applied"

    assert "phone_screen" in applications_set_status(app.id, "phone_screen", next_step="Call Tue")
    assert "Call Tue" in applications_list(company=app.company)


def test_mark_applied_requires_exactly_one_target() -> None:
    with pytest.raises(ToolError, match="exactly one"):
        applications_mark_applied()
    with pytest.raises(ToolError, match="exactly one"):
        applications_mark_applied(application_id="a", jd="b")


def test_invalid_status_is_a_tool_error() -> None:
    apps.create_application("Acme", "Dev")
    [app] = apps.load_applications()
    with pytest.raises(ToolError):
        applications_set_status(app.id, "hired")


def test_search_constraints_tool(_isolate_personal_data) -> None:
    assert "No private/search-constraints.json" in search_constraints()
    _set_constraints(_isolate_personal_data)
    assert "$85,000" in search_constraints()


# ── private paths are not reachable through client-supplied paths ───────────


def test_private_directory_and_git_are_denied(tmp_path: Path) -> None:
    from jobomatic.interfaces.mcp import server

    for target in (
        REPO_ROOT / "private" / "search-constraints.example.json",
        REPO_ROOT / ".git" / "config",
    ):
        with pytest.raises(ToolError, match="outside the directories"):
            server._checked_path(str(target), write=False, label="x")


def test_applications_log_is_not_readable_as_a_jd_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from jobomatic.interfaces.mcp import server

    log = server.applications_log.log_path()
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("")
    with pytest.raises(ToolError, match="outside the directories"):
        fit_check(str(log))
