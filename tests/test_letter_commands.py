"""The letters and interview prep as commands that return a result (ADR 0028)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobomatic.commands import applications, cold_call, interview_prep, job_site_letter, thank_you
from jobomatic.commands.support import Confirmations, DocumentData
from tests.command_cases import QUEBEC, STRETCH_SKILLS, STRONG, Env, _jd

POSTING = STRONG.read_text(encoding="utf-8")
DISCUSSION = ["We discussed the team's roadmap."]


@pytest.fixture
def env(tmp_path: Path) -> Env:
    work, out = tmp_path / "work", tmp_path / "out"
    work.mkdir()
    out.mkdir()
    return Env(work=work, out=out)


def _assert_made(result, out: Path) -> None:
    assert result.status == "ok"
    assert isinstance(result.data, DocumentData) and result.data.path == out
    assert result.written == (out, Path(f"{out}.meta.json"))
    assert all(path.exists() for path in result.written)


# -- job-site letter ---------------------------------------------------------------------------


def test_the_job_site_letter_is_made_and_logged(
    env: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    out = env.out / "site.txt"
    result = job_site_letter.run(POSTING, out=out)
    _assert_made(result, out)
    assert result.messages[-1].text.startswith("Logged as drafted (not applied)")
    assert capsys.readouterr() == ("", "")


def test_the_job_site_letter_refuses_a_location_pass_without_an_override(env: Env) -> None:
    result = job_site_letter.run(QUEBEC.read_text(encoding="utf-8"), out=env.out / "site.txt")
    assert result.status == "refused" and result.override is None
    assert not (env.out / "site.txt").exists()


def test_the_job_site_letter_does_not_gate_on_skill_fit(env: Env) -> None:
    posting = Path(_jd(env, "stretch.md", *STRETCH_SKILLS)).read_text(encoding="utf-8")
    assert job_site_letter.run(posting, out=env.out / "site.txt").status == "ok"


def test_a_repeat_application_is_refused_until_confirmed(env: Env) -> None:
    assert applications.applied(jd_text=POSTING).status == "ok"  # the posting was applied to today
    out = env.out / "site.txt"
    refused = job_site_letter.run(POSTING, out=out)
    assert refused.status == "refused" and refused.override == "confirm_reapply"
    assert not out.exists()
    assert job_site_letter.run(POSTING, out=out, confirm=Confirmations(reapply=True)).status == "ok"


def test_a_docx_job_site_letter_records_the_posting_file(env: Env) -> None:
    out = env.out / "site.docx"
    job_site_letter.run(POSTING, source=STRONG, out=out)
    assert json.loads(Path(f"{out}.meta.json").read_text())["inputs"] == [str(STRONG)]


# -- cold-call letter --------------------------------------------------------------------------


def test_the_cold_call_letter_needs_no_posting(env: Env) -> None:
    out = env.out / "cold.docx"
    result = cold_call.run(recruiter_name="Pat Lee", role_type="Senior .NET roles", out=out)
    _assert_made(result, out)


def test_the_cold_call_letter_refuses_a_location_pass_in_a_posting(env: Env) -> None:
    out = env.out / "cold.docx"
    result = cold_call.run(QUEBEC.read_text(encoding="utf-8"), out=out)
    assert result.status == "refused" and not out.exists()


def test_the_cold_call_letter_takes_pasted_text_as_markdown(env: Env) -> None:
    result = cold_call.run(POSTING, out=env.out / "cold.docx")
    assert result.status == "ok"
    meta = json.loads(Path(f"{env.out / 'cold.docx'}.meta.json").read_text())
    assert meta["inputs"] == []  # pasted: there is no file to name
    with_file = cold_call.run(POSTING, source=STRONG, out=env.out / "cold2.docx")
    assert with_file.status == "ok"
    meta = json.loads(Path(f"{env.out / 'cold2.docx'}.meta.json").read_text())
    assert meta["inputs"] == [str(STRONG)]


# -- thank-you letter --------------------------------------------------------------------------


def test_the_thank_you_letter_is_made_from_real_discussion_points(env: Env) -> None:
    out = env.out / "thanks.docx"
    result = thank_you.run(POSTING, discussion_points=DISCUSSION, out=out)
    _assert_made(result, out)


def test_the_thank_you_letter_fails_without_a_discussion_point(env: Env) -> None:
    result = thank_you.run(POSTING, out=env.out / "thanks.docx")
    assert result.status == "error"
    assert "discussion_points is required" in result.messages[-1].text


def test_the_thank_you_letter_warns_when_nothing_grounds_the_skills(env: Env) -> None:
    result = thank_you.run(discussion_points=DISCUSSION, out=env.out / "thanks.docx")
    assert result.status == "ok"
    assert [m.level for m in result.messages] == ["warning"]
    assert result.messages[0].text.startswith("thank-you letter has no grounded required-skill")


# -- interview prep ----------------------------------------------------------------------------


def test_the_interview_prep_is_made(env: Env) -> None:
    out = env.out / "prep.docx"
    _assert_made(interview_prep.run(POSTING, out=out), out)


def test_an_unknown_stage_is_an_error_result(env: Env) -> None:
    result = interview_prep.run(POSTING, stage="coffee_chat", out=env.out / "prep.docx")
    assert result.status == "error"
    assert "unknown stage 'coffee_chat'" in result.messages[-1].text


def test_malformed_qa_cards_are_an_error_that_writes_nothing(env: Env) -> None:
    out = env.out / "prep.docx"
    result = interview_prep.run(POSTING, out=out, qa_cards_json="{not json")
    assert result.status == "error"
    assert result.messages[-1].text.startswith("invalid JSON in --qa-cards file")
    assert not out.exists()


def test_qa_cards_are_merged_in(env: Env) -> None:
    cards = json.dumps([{"question": "Why us?", "answer": "The platform work."}])
    assert (
        interview_prep.run(POSTING, out=env.out / "prep.docx", qa_cards_json=cards).status == "ok"
    )


def test_a_salary_section_before_the_final_round_is_noted_and_omitted(env: Env) -> None:
    result = interview_prep.run(POSTING, out=env.out / "prep.docx", salary_section="Ask for X.")
    assert any(
        m.text.startswith("Salary section supplied but stage is not final_round")
        for m in result.messages
    )


def test_recording_story_use_is_said_for_each_story(env: Env) -> None:
    result = interview_prep.run(POSTING, out=env.out / "prep.docx", update_star_bank=True)
    stories = [m.text for m in result.messages if m.text.startswith("STAR story ")]
    assert stories and all("last_used ->" in text for text in stories)
