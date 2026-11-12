"""The variables that were renamed (ADR 0030) are an error when set, not silently ignored.

Ignoring ``CLAUDE_JOBS_APPLICATIONS_LOG`` would write the applications log to the vault instead of
where the user pointed it, so each old name raises a ``VaultError`` that names its replacement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jobomatic import paths
from jobomatic.interfaces.cli.main import main
from jobomatic.interfaces.mcp import server

OLD_AND_NEW = [
    ("CLAUDE_JOBS_PRIVATE_DIR", "JOBOMATIC_PRIVATE_DIR"),
    ("CLAUDE_JOBS_APPLICATIONS_LOG", "JOBOMATIC_APPLICATIONS_LOG"),
    ("CLAUDE_JOBS_ALLOWED_DIRS", "JOBOMATIC_ALLOWED_DIRS"),
]


def test_the_map_is_exactly_the_three_renamed_variables() -> None:
    assert paths.RETIRED_VARIABLES == dict(OLD_AND_NEW)


@pytest.mark.parametrize("old, new", OLD_AND_NEW)
def test_an_old_name_raises_and_names_the_new_one(
    old: str, new: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(old, str(tmp_path))
    with pytest.raises(paths.VaultError) as raised:
        paths.reject_retired_variables()
    assert old in str(raised.value) and new in str(raised.value)


def test_an_empty_old_name_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    # An empty value moved nothing before and moves nothing now.
    monkeypatch.setenv("CLAUDE_JOBS_PRIVATE_DIR", "")
    paths.reject_retired_variables()


def test_the_private_folder_lookup_refuses_the_old_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_JOBS_PRIVATE_DIR", str(tmp_path))
    with pytest.raises(paths.VaultError, match="JOBOMATIC_PRIVATE_DIR"):
        paths.private_dir()


def test_the_applications_log_lookup_refuses_the_old_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_JOBS_APPLICATIONS_LOG", str(tmp_path / "log.jsonl"))
    with pytest.raises(paths.VaultError, match="JOBOMATIC_APPLICATIONS_LOG"):
        paths.applications_log()


def test_the_new_names_still_work(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JOBOMATIC_PRIVATE_DIR", str(tmp_path / "p"))
    monkeypatch.setenv("JOBOMATIC_APPLICATIONS_LOG", str(tmp_path / "a.jsonl"))
    assert paths.private_dir() == tmp_path / "p"
    assert paths.applications_log() == tmp_path / "a.jsonl"


def test_the_command_line_prints_one_line_and_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CLAUDE_JOBS_APPLICATIONS_LOG", str(tmp_path / "log.jsonl"))
    assert main(["applications", "list"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("ERROR: CLAUDE_JOBS_APPLICATIONS_LOG is no longer read")
    assert "Traceback" not in err


@pytest.mark.parametrize("old, new", OLD_AND_NEW)
def test_the_mcp_server_refuses_an_old_name_with_a_vault(
    old: str, new: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(old, str(tmp_path))
    with pytest.raises(paths.VaultError, match=new):
        server._locations()


@pytest.mark.parametrize("old, new", OLD_AND_NEW)
def test_the_mcp_server_refuses_an_old_name_with_no_vault(
    old: str, new: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # ``_locations`` treats "no vault" as a normal case and swallows its error when it looks up
    # the private folder; the old-name error must not be swallowed there.
    monkeypatch.setenv("JOBOMATIC_VAULT", str(tmp_path / "not-a-vault"))
    monkeypatch.setenv(old, str(tmp_path))
    with pytest.raises(paths.VaultError, match=new):
        server._locations()


def test_the_mcp_server_without_a_vault_still_works_when_no_old_name_is_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("JOBOMATIC_VAULT", str(tmp_path / "not-a-vault"))
    assert server._locations().vault is None
