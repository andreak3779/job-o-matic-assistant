"""Tests for jobomatic.commands.support."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobomatic import paths
from jobomatic.commands.support import load_profile_or_none, require_path


def test_require_path_returns_path_when_it_exists(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hi", encoding="utf-8")
    assert require_path(f, "File") == f


def test_require_path_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        require_path(tmp_path / "does-not-exist.txt", "File")


def test_load_profile_or_none_returns_the_profile_from_the_vault() -> None:
    profile = load_profile_or_none()

    assert profile is not None
    assert profile.identity.name == "Sarah Ashford"


def test_load_profile_or_none_returns_none_for_a_missing_profile(
    tmp_vault: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = load_profile_or_none()
    assert result is None
    err = capsys.readouterr().err
    assert "ERROR" in err
    assert "missing profile file" in err


def test_load_profile_or_none_returns_none_for_a_broken_file(
    capsys: pytest.CaptureFixture[str],
) -> None:
    (paths.profile_dir() / "roles.yaml").write_text("roles: [", encoding="utf-8")

    result = load_profile_or_none()

    assert result is None
    err = capsys.readouterr().err
    assert "ERROR" in err
    assert "not valid YAML" in err


def test_load_profile_or_none_returns_none_when_there_is_no_vault(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("JOBOMATIC_VAULT", str(tmp_path / "nowhere"))
    assert load_profile_or_none() is None
    assert "ERROR" in capsys.readouterr().err
