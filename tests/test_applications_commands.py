"""The applications and constraints commands as commands that return a result (ADR 0028)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from jobomatic import applications as apps
from jobomatic import paths
from jobomatic.commands import applications as commands
from jobomatic.commands import constraints
from jobomatic.interfaces.cli import applications_cli
from jobomatic.interfaces.mcp import server
from tests.command_cases import STRONG

POSTING = STRONG.read_text(encoding="utf-8")


def _draft() -> str:
    found = apps.find_for_jd(POSTING)
    assert found is not None
    return found.id


@pytest.fixture
def drafted() -> str:
    assert applications_cli.run(_args("add")) == 0
    return _draft()


def _args(command: str):
    import argparse

    return argparse.Namespace(
        command="applications",
        applications_command=command,
        jd=STRONG,
        platform=None,
        url=None,
    )


# -- check and list --------------------------------------------------------------------------


def test_check_returns_the_verdict_as_data_and_prints_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = commands.check(POSTING)
    assert result.status == "ok"
    assert isinstance(result.data, commands.CheckData)
    assert result.data.check.verdict == "new"
    assert result.written == ()
    assert capsys.readouterr() == ("", "")


def test_a_posting_already_drafted_is_reported_as_drafted(drafted: str) -> None:
    result = commands.check(POSTING)
    assert result.data is not None
    assert result.data.check.verdict == "drafted"
    assert drafted in commands.render_check(result.data)


def test_list_returns_the_rows_and_can_filter(drafted: str) -> None:
    everything = commands.list_applications()
    assert everything.data is not None
    assert [a.id for a in everything.data.rows] == [drafted]
    assert commands.list_applications(status="applied").data == commands.ApplicationList(())
    assert commands.list_applications(company="Northgate Insurance Group").data is not None


def test_an_unknown_status_is_an_error_result_not_an_empty_list() -> None:
    result = commands.list_applications(status="bogus")
    assert result.status == "error"
    assert "unknown status 'bogus'" in result.messages[-1].text


# -- the writes ------------------------------------------------------------------------------


def test_applied_by_posting_creates_the_entry_and_marks_it() -> None:
    result = commands.applied(jd_text=POSTING, date="2026-01-05")
    assert result.status == "ok"
    assert result.data is not None
    assert (result.data.status, result.data.applied_on) == ("applied", "2026-01-05")
    assert commands.render_applied(result.data).startswith("Marked applied on 2026-01-05:")


def test_applied_by_id_marks_the_existing_entry(drafted: str) -> None:
    result = commands.applied(application_id=drafted, date="2026-02-01")
    assert result.data is not None and result.data.id == drafted


def test_applied_with_neither_id_nor_posting_is_an_error() -> None:
    result = commands.applied()
    assert result.status == "error"


def test_applied_for_an_unknown_id_is_an_error_result() -> None:
    assert commands.applied(application_id="no-such-id").status == "error"


def test_set_status_moves_the_entry_and_says_so(drafted: str) -> None:
    result = commands.set_status(drafted, "technical", note="second round")
    assert result.data is not None and result.data.status == "technical"
    assert commands.render_status(result.data).endswith("is now technical")


def test_an_unknown_status_cannot_be_set(drafted: str) -> None:
    result = commands.set_status(drafted, "bogus")
    assert result.status == "error"
    assert apps.get_application(drafted).status == "drafted"


def test_the_mcp_tool_rejects_an_unknown_status_with_a_tool_error(drafted: str) -> None:
    with pytest.raises(ToolError, match="unknown status"):
        server.applications_set_status(drafted, "bogus")
    with pytest.raises(ToolError, match="unknown status"):
        server.applications_list(status="bogus")


def test_two_callers_marking_the_same_new_posting_make_one_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The write lock serializes the read-then-create (it did, as a side effect, before)."""
    real = apps.find_for_jd

    def slow_find(text: str, *args, **kwargs):
        found = real(text, *args, **kwargs)
        time.sleep(0.15)  # long enough for the other caller to reach the same place
        return found

    monkeypatch.setattr(commands.apps, "find_for_jd", slow_find)
    results: list[object] = []
    callers = [
        threading.Thread(target=lambda: results.append(commands.applied(jd_text=POSTING)))
        for _ in range(2)
    ]
    for caller in callers:
        caller.start()
    for caller in callers:
        caller.join()
    assert [a.title for a in apps.load_applications()].count(
        "Senior Full-Stack .NET Developer"
    ) == 1


# -- constraints -----------------------------------------------------------------------------


def test_missing_constraints_are_a_normal_result() -> None:
    result = constraints.show()
    assert result.status == "ok"
    assert result.data is not None and result.data.constraints is None
    assert constraints.render(result.data).startswith("No private/search-constraints.json")


def test_configured_constraints_are_described() -> None:
    paths.private_dir().mkdir(parents=True, exist_ok=True)
    (paths.private_dir() / "search-constraints.json").write_text(
        '{"min_permanent_base_cad": 90000}', encoding="utf-8"
    )
    data = constraints.show().data
    assert data is not None
    assert constraints.render(data) == "Minimums (search-constraints.json): permanent base $90,000"


def test_malformed_constraints_are_an_error_result(tmp_path: Path) -> None:
    paths.private_dir().mkdir(parents=True, exist_ok=True)
    (paths.private_dir() / "search-constraints.json").write_text("{nope", encoding="utf-8")
    assert constraints.show().status == "error"
