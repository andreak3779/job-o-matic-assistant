"""``fit-check`` as a command that returns a result (ADR 0028)."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from jobomatic import paths
from jobomatic.commands import fit_check
from jobomatic.fit.engine import FitResult
from jobomatic.interfaces.mcp import server
from tests.command_cases import QUEBEC, STRONG

POSTING = STRONG.read_text(encoding="utf-8")


def _break_the_constraints() -> None:
    paths.private_dir().mkdir(parents=True, exist_ok=True)
    (paths.private_dir() / "search-constraints.json").write_text("{not json", encoding="utf-8")


def test_run_returns_the_rating_as_data_and_prints_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = fit_check.run(POSTING)
    assert result.status == "ok"
    assert isinstance(result.data, fit_check.FitCheckData)
    assert isinstance(result.data.fit, FitResult)
    assert result.data.fit.rating == "Strong"
    assert (result.data.title, result.data.company) == (
        "Senior Full-Stack .NET Developer",
        "Northgate Insurance Group",
    )
    assert result.written == ()
    assert capsys.readouterr() == ("", "")


def test_a_location_pass_is_still_a_result_not_a_refusal() -> None:
    """A fit check reports a Pass; only the generators refuse."""
    result = fit_check.run(QUEBEC.read_text(encoding="utf-8"))
    assert result.status == "ok"
    assert result.data is not None and result.data.fit.rating == "Pass"


def test_a_missing_profile_is_an_error_result(tmp_vault: Path) -> None:
    result = fit_check.run(POSTING)
    assert result.status == "error"
    assert result.data is None
    assert result.exit_code == 1


def test_invalid_constraints_fail_after_the_table_was_made() -> None:
    _break_the_constraints()
    result = fit_check.run(POSTING)
    assert result.status == "error"
    assert result.data is not None and result.data.salary is None
    assert "search-constraints.json is invalid" in result.messages[-1].text


def test_invalid_constraints_still_print_the_table_before_the_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """As the command line always has: the rating, then the reason the salary screen failed."""
    _break_the_constraints()
    assert fit_check.main([str(STRONG)]) == 1
    captured = capsys.readouterr()
    assert captured.out.startswith("## Fit Check — Senior Full-Stack .NET Developer")
    assert "**Required Skills**" in captured.out
    assert captured.err.startswith("ERROR: private/search-constraints.json is invalid")


def test_the_mcp_tool_says_the_same_and_fails_the_same_way() -> None:
    _break_the_constraints()
    with pytest.raises(ToolError) as excinfo:
        server.fit_check(POSTING)
    assert "**Required Skills**" in str(excinfo.value)
    assert "search-constraints.json is invalid" in str(excinfo.value)


def test_the_mcp_tool_takes_the_text_of_the_posting_or_a_path_to_it() -> None:
    assert server.fit_check(POSTING) == server.fit_check(str(STRONG))
