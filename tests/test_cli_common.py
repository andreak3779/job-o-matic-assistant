"""Tests for jobomatic.commands.support."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobomatic import paths
from jobomatic.commands.support import require_path


def test_require_path_returns_path_when_it_exists(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hi", encoding="utf-8")
    assert require_path(f, "File") == f


def test_require_path_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        require_path(tmp_path / "does-not-exist.txt", "File")


def test_require_path_says_where_it_looked_for_a_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError) as caught:
        require_path(Path("posting.md"), "JD file")
    text = str(caught.value)
    assert text.startswith("JD file not found: posting.md")
    assert f"Looked for: {tmp_path / 'posting.md'}" in text
    assert f"Current folder: {tmp_path}" in text
    assert "give the full path" in text


def test_require_path_for_an_absolute_path_only_asks_for_the_spelling(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError) as caught:
        require_path(tmp_path / "nope.md", "JD file")
    text = str(caught.value)
    assert "Check the spelling" in text
    assert "Current folder" not in text


# A profile that cannot be loaded is a clean error result from every command (ADR 0007, 0028), not
# a traceback. ``fit-check`` stands for them all; the missing-profile test in test_cli_commands.py
# runs every command.


def _error_text_of_fit_check() -> str:
    from jobomatic.commands import fit_check

    result = fit_check.run("# Dev | Acme Corp\n\n## Requirements\n- C#\n")
    assert result.status == "error"
    return result.messages[-1].text


def test_a_missing_profile_file_is_an_error_that_names_it(tmp_vault: Path) -> None:
    assert "missing profile file" in _error_text_of_fit_check()


def test_a_broken_profile_file_is_an_error_that_says_so() -> None:
    (paths.profile_dir() / "roles.yaml").write_text("roles: [", encoding="utf-8")
    assert "not valid YAML" in _error_text_of_fit_check()


def test_no_vault_at_all_is_an_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JOBOMATIC_VAULT", str(tmp_path / "nowhere"))
    assert _error_text_of_fit_check()
