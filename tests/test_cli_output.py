"""Printing a command's result on the command line (ADR 0028): text, streams and exit status."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from jobomatic.interfaces.cli.output import emit
from jobomatic.results import Message, failure, ok, refusal


def _emit(result, render=None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = emit(result, render, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def test_a_plain_success_prints_nothing_and_exits_zero() -> None:
    assert _emit(ok()) == (0, "", "")


def test_the_payload_is_rendered_to_stdout() -> None:
    code, out, err = _emit(ok({"rating": "Strong"}), lambda data: f"Fit Rating: {data['rating']}")
    assert (code, out, err) == (0, "Fit Rating: Strong\n", "")


def test_a_payload_with_no_renderer_prints_nothing() -> None:
    assert _emit(ok({"rating": "Strong"})) == (0, "", "")


def test_messages_go_to_the_stream_their_level_says() -> None:
    result = ok(
        messages=(
            Message("info", "Logged as drafted"),
            Message("note", "salary below range"),
            Message("warning", "log unreadable"),
        )
    )
    code, out, err = _emit(result)
    assert code == 0
    assert out == "Logged as drafted\nNote: salary below range\n"
    assert err == "WARNING: log unreadable\n"


def test_written_files_are_listed_last_in_order() -> None:
    result = ok(
        {"x": 1},
        messages=(Message("note", "n"),),
        written=(Path("/out/a.docx"), Path("/out/a.docx.meta.json")),
    )
    _, out, _ = _emit(result, lambda data: "payload")
    assert out == "payload\nNote: n\nWrote /out/a.docx\nWrote /out/a.docx.meta.json\n"


def test_a_failure_prints_an_error_on_stderr_and_exits_one() -> None:
    assert _emit(failure("JD file not found: x.md")) == (1, "", "ERROR: JD file not found: x.md\n")


def test_a_refusal_prints_refused_and_how_to_confirm_and_exits_two() -> None:
    code, out, err = _emit(refusal("Fit rating is Stretch.", override="confirm_gaps"))
    assert code == 2
    assert out == ""
    assert err == (
        "REFUSED: Fit rating is Stretch.\n"
        "Only if the user says so, run again with confirm_gaps "
        "(command line: --confirm-gaps; tool: confirm_gaps=true).\n"
    )


def test_a_refusal_that_cannot_be_confirmed_has_no_hint() -> None:
    assert _emit(refusal("Outside the location rules.")) == (
        2,
        "",
        "REFUSED: Outside the location rules.\n",
    )


def test_what_was_said_before_a_failure_is_still_said() -> None:
    result = failure("could not write", messages=(Message("info", "Fit Rating: Strong"),))
    assert _emit(result) == (1, "Fit Rating: Strong\n", "ERROR: could not write\n")


def test_the_default_streams_are_looked_up_when_called(capsys: pytest.CaptureFixture[str]) -> None:
    assert emit(failure("nope")) == 1
    assert capsys.readouterr().err == "ERROR: nope\n"
