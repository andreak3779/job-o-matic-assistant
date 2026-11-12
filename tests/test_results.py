"""The result a command returns, and the boundary that makes failures into results (ADR 0028)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobomatic.documents.service import DocumentError
from jobomatic.gate import GateRefusal
from jobomatic.learning.service import LearningError
from jobomatic.paths import VaultError
from jobomatic.profile.service import ProfileError
from jobomatic.results import (
    CommandResult,
    Message,
    Refusal,
    failure,
    guarded,
    ok,
    override_hint,
    refusal,
)
from jobomatic.retrieval.model import RetrievalError

# -- the result ---------------------------------------------------------------------------------


def test_the_exit_status_follows_the_status() -> None:
    assert ok().exit_code == 0
    assert failure("no file").exit_code == 1
    assert refusal("too weak").exit_code == 2


def test_an_ok_result_carries_its_payload_messages_and_files() -> None:
    result = ok(
        {"rating": "Strong"},
        messages=(Message("note", "check the salary"),),
        written=(Path("/out/resume.docx"),),
    )
    assert result.data == {"rating": "Strong"}
    assert result.messages == (Message("note", "check the salary"),)
    assert result.written == (Path("/out/resume.docx"),)
    assert result.override is None


def test_a_failure_keeps_earlier_messages_and_ends_with_the_error() -> None:
    result = failure("could not read it", messages=(Message("warning", "slow disk"),))
    assert result.messages == (
        Message("warning", "slow disk"),
        Message("error", "could not read it"),
    )


def test_a_refusal_names_what_would_let_it_through() -> None:
    result = refusal("Stretch fit", override="confirm_gaps")
    assert result.status == "refused"
    assert result.override == "confirm_gaps"


def test_a_refusal_with_no_override_cannot_be_confirmed_past() -> None:
    assert refusal("location Pass").override is None


@pytest.mark.parametrize("status", ["error", "refused"])
def test_a_result_that_did_not_succeed_must_say_why(status: str) -> None:
    with pytest.raises(ValueError, match="needs an error message"):
        CommandResult(status)  # type: ignore[arg-type]


def test_only_a_refusal_can_name_an_override() -> None:
    with pytest.raises(ValueError, match="only a refused result"):
        CommandResult("error", messages=(Message("error", "x"),), override="confirm_gaps")


def test_the_result_cannot_be_changed_after_it_is_made() -> None:
    result = ok()
    with pytest.raises(AttributeError):
        result.status = "error"  # type: ignore[misc]


# -- the hint on how to confirm -----------------------------------------------------------------


def test_the_hint_names_the_flag_and_the_tool_argument() -> None:
    assert override_hint("confirm_below_minimum") == (
        "Only if the user says so, run again with confirm_below_minimum "
        "(command line: --confirm-below-minimum; tool: confirm_below_minimum=true)."
    )


def test_the_gate_refusal_reads_as_it_always_did() -> None:
    assert str(GateRefusal("Fit is Stretch.", "confirm_gaps")) == (
        "Fit is Stretch.\nOnly if the user says so, run again with confirm_gaps "
        "(command line: --confirm-gaps; tool: confirm_gaps=true)."
    )
    assert str(GateRefusal("Location Pass.")) == "Location Pass."


def test_the_gate_refusal_is_a_refusal() -> None:
    assert isinstance(GateRefusal("no"), Refusal)


# -- the boundary -------------------------------------------------------------------------------


def test_guarded_returns_the_result_the_command_made() -> None:
    result = ok("data")
    assert guarded(lambda: result) is result


def _raises(exc: BaseException):
    def command():
        raise exc

    return command


@pytest.mark.parametrize(
    "exc",
    [
        ProfileError("profile is broken"),
        VaultError("no vault"),
        DocumentError("cannot build"),
        LearningError("bad item"),
        RetrievalError("no index"),
        ValueError("bad value"),
        FileNotFoundError("missing.md"),
        PermissionError("read-only"),
    ],
    ids=lambda exc: type(exc).__name__,
)
def test_an_expected_failure_becomes_an_error_result(exc: Exception) -> None:
    result = guarded(_raises(exc))
    assert result.status == "error"
    assert result.messages == (Message("error", str(exc)),)
    assert result.written == ()


def test_a_gate_refusal_becomes_a_refused_result_with_its_override() -> None:
    result = guarded(_raises(GateRefusal("Fit is Stretch.", "confirm_gaps")))
    assert result.status == "refused"
    assert result.override == "confirm_gaps"
    assert result.messages == (Message("error", "Fit is Stretch."),)


def test_a_refusal_with_no_override_stays_unconfirmable() -> None:
    assert guarded(_raises(GateRefusal("Location Pass."))).override is None


@pytest.mark.parametrize("exc", [KeyError("x"), RuntimeError("bug"), AttributeError("bug")])
def test_a_bug_is_not_hidden(exc: Exception) -> None:
    with pytest.raises(type(exc)):
        guarded(_raises(exc))
