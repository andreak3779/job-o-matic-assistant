"""The gates: when documents may be generated (ADR 0003, 0008, 0010, 0011, 0021)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from jobomatic import applications, gate
from jobomatic.bootstrap import load_profile
from jobomatic.fit.constraints import SearchConstraints
from jobomatic.fit.engine import rate_parsed_jd
from jobomatic.fit.parser import parse_jd


def _jd(title: str, *required: str, header: str = "") -> str:
    lines = "".join(f"- {line}\n" for line in required)
    return f"# {title}\n{header}\n## Requirements\n{lines}"


COVERED = ["C#", "SQL", "Angular", "Docker", "Git"]
GOOD = _jd("Dev", *COVERED)
WORTH_A_TRY = _jd("Dev", *COVERED, "Python", "Jira", "Rust")  # the gap is late, so not core
STRETCH = _jd("Dev", "Rust", *COVERED, "Python", "Jira")  # a gap on line one is core
PASS = _jd("Dev", "Rust", "Kotlin", *COVERED)  # two core gaps


@pytest.fixture
def profile():
    # Function-scoped on purpose: the suite's throwaway vault is set up per test (conftest), and a
    # module-scoped load would read the real vault, or fail where there is none.
    return load_profile()


def test_the_fixtures_rate_as_named(profile) -> None:
    ratings = {
        name: rate_parsed_jd(parse_jd(text), profile).rating
        for name, text in {
            "good": GOOD,
            "wat": WORTH_A_TRY,
            "stretch": STRETCH,
            "pass": PASS,
        }.items()
    }
    assert ratings == {
        "good": ratings["good"],
        "wat": "Worth a try",
        "stretch": "Stretch",
        "pass": "Pass",
    }
    assert ratings["good"] in gate.PASSING_RATINGS


def test_a_good_rating_passes_without_any_confirmation(profile) -> None:
    result = gate.check_fit(GOOD, profile)
    assert result.fit is not None and result.fit.rating in gate.PASSING_RATINGS
    assert result.notes == []


@pytest.mark.parametrize("text", [WORTH_A_TRY, STRETCH])
def test_stretch_and_worth_a_try_are_refused_until_the_user_confirms(profile, text: str) -> None:
    with pytest.raises(gate.GateRefusal) as refused:
        gate.check_fit(text, profile)
    assert refused.value.override == gate.CONFIRM_GAPS
    message = str(refused.value)
    assert "Only if the user says so" in message and "--confirm-gaps" in message
    assert "confirm_gaps=true" in message


@pytest.mark.parametrize("text", [WORTH_A_TRY, STRETCH])
def test_confirming_gaps_lets_them_through_with_a_note(profile, text: str) -> None:
    result = gate.check_fit(text, profile, confirm_gaps=True)
    assert any("Proceeding past" in note for note in result.notes)


def test_a_skills_pass_can_never_be_confirmed_past(profile) -> None:
    for confirm in (False, True):
        with pytest.raises(gate.GateRefusal) as refused:
            gate.check_fit(PASS, profile, confirm_gaps=confirm)
        assert refused.value.override is None
        assert "cannot be confirmed past" in str(refused.value)


def test_a_location_pass_can_never_be_confirmed_past(profile) -> None:
    text = _jd("Dev", *COVERED, header="\n**Location:** Montreal, Quebec — on-site\n")
    parsed = parse_jd(text)
    if not parsed.location_check.disqualified:
        pytest.skip("the fixture location rules do not disqualify this posting")
    with pytest.raises(gate.GateRefusal) as refused:
        gate.check_fit(text, profile, confirm_gaps=True)
    assert refused.value.override is None
    with pytest.raises(gate.GateRefusal):
        gate.check_location(text)


def test_a_duplicate_is_refused_until_confirmed(tmp_path: Path) -> None:
    log = tmp_path / "applications.jsonl"
    jd = "# Backend Developer\n\n**Company:** Acme\n\n## Requirements\n- C#\n"
    app_id = applications.record_draft(jd, documents=("resume",), path=log)
    assert app_id
    applications.mark_applied(app_id, date.today().isoformat(), path=log)
    with pytest.raises(gate.GateRefusal) as refused:
        gate.check_duplicate(jd, log_path=log)
    assert refused.value.override == gate.CONFIRM_REAPPLY
    assert gate.check_duplicate(jd, confirm_reapply=True, log_path=log)


def test_a_draft_alone_is_not_a_duplicate(tmp_path: Path) -> None:
    log = tmp_path / "applications.jsonl"
    jd = "# Backend Developer\n\n**Company:** Acme\n\n## Requirements\n- C#\n"
    applications.record_draft(jd, documents=("resume",), path=log)
    assert gate.check_duplicate(jd, log_path=log) == []


def test_pay_below_the_minimum_is_refused_until_confirmed() -> None:
    constraints = SearchConstraints(min_permanent_base_cad=99500, min_contract_hourly_cad=66.5)
    low = "Dev\n\n$41,000 - $43,000 per year\n\n## Requirements\n- C#\n"
    with pytest.raises(gate.GateRefusal) as refused:
        gate.check_pay(low, constraints=constraints, load=False)
    assert refused.value.override == gate.CONFIRM_BELOW_MINIMUM
    assert gate.check_pay(low, confirm_below_minimum=True, constraints=constraints, load=False)


def test_no_posted_pay_never_blocks() -> None:
    assert gate.check_pay("Dev\n\n## Requirements\n- C#\n", constraints=None, load=False) == []


def test_the_full_document_gate_runs_fit_duplicate_and_pay(profile, tmp_path: Path) -> None:
    result = gate.check_documents(
        GOOD, profile, log_path=tmp_path / "applications.jsonl", load_constraints_from_vault=False
    )
    assert result.fit is not None
    with pytest.raises(gate.GateRefusal):
        gate.check_documents(
            STRETCH,
            profile,
            log_path=tmp_path / "applications.jsonl",
            load_constraints_from_vault=False,
        )


def test_the_letter_gate_checks_location_and_duplicate_but_not_skills(tmp_path: Path) -> None:
    assert gate.check_letter(PASS, log_path=tmp_path / "applications.jsonl") == []
