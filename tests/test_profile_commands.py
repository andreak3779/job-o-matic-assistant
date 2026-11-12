"""The profile commands as commands that return a result (ADR 0028)."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from jobomatic import bootstrap
from jobomatic.commands import profile as commands
from jobomatic.interfaces.mcp import server
from jobomatic.results import console


def test_validate_returns_the_counts_and_prints_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = commands.validate()
    assert result.status == "ok"
    assert isinstance(result.data, commands.ValidateData)
    assert result.data.roles > 0
    assert commands.render_validate(result.data).splitlines()[-1].startswith("[OK] Profile valid")
    assert capsys.readouterr() == ("", "")


def test_a_profile_with_an_error_fails_but_still_reports_what_it_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from jobomatic.profile.service import Issue

    monkeypatch.setattr(commands, "check", lambda profile: [Issue("error", "roles[0]", "no title")])
    result = commands.validate()
    assert result.status == "error"
    assert result.data is not None and result.data.errors == 1
    text = console(result, commands.render_validate)
    lines = text.stdout.splitlines()
    assert lines[0] == "[ERROR] roles[0]: no title"
    assert lines[-1] == "Profile has 1 error(s)."
    assert not any(line.startswith("[OK]") for line in lines)
    assert text.stderr == ""


def test_a_profile_that_cannot_be_loaded_is_a_failed_result(tmp_vault: Path) -> None:
    result = commands.validate()
    assert result.status == "error" and result.data is None
    assert result.messages[0].text.startswith("[ERROR] ")


def test_the_public_view_has_no_contact_details() -> None:
    result = commands.show("contact", public=True)
    assert result.status == "error"
    assert result.messages[0].text == "[ERROR] contact details are not part of the public view"
    facts = commands.show("facts", public=True)
    assert facts.data is not None and "Professional Headline" in facts.data.text


def test_a_slice_names_the_sections_it_could_not_find_before_the_text() -> None:
    result = commands.show("section", ("Key Differentiators", "No Such Heading"))
    assert result.status == "ok"
    assert result.data is not None and result.data.missing == ("No Such Heading",)
    first, *_ = commands.render_show(result.data).splitlines()
    assert first == "[ERROR] no section called 'No Such Heading'"


def test_asking_only_for_sections_that_are_not_there_fails() -> None:
    result = commands.show("section", ("No Such Heading",))
    assert result.status == "error"
    assert [m.text for m in result.messages] == ["[ERROR] no section called 'No Such Heading'"]


def test_the_contact_slice_is_the_contact_text() -> None:
    result = commands.show("contact")
    assert result.data is not None
    assert result.data.text.rstrip("\n") == commands.profile_text.contact_text(
        bootstrap.load_profile()
    )


def test_the_mcp_summary_is_the_public_view_and_a_broken_profile_is_a_tool_error(
    tmp_vault: Path,
) -> None:
    with pytest.raises(ToolError, match=r"\[ERROR\]"):
        server.profile_summary()
