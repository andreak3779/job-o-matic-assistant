"""jobomatic.paths: the one place that decides where personal data lives."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from jobomatic import paths


@pytest.fixture
def legacy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """No vault configured anywhere: no env var, no config file, no sibling directory.

    Returns the fake checkout directory; a sibling vault would live next to it.
    """
    checkout = tmp_path / "work" / "checkout"
    checkout.mkdir(parents=True)
    monkeypatch.delenv("JOBOMATIC_VAULT", raising=False)
    monkeypatch.delenv("CLAUDE_JOBS_APPLICATIONS_LOG", raising=False)
    monkeypatch.delenv("CLAUDE_JOBS_PRIVATE_DIR", raising=False)
    monkeypatch.setenv("JOBOMATIC_CONFIG", str(tmp_path / "no-config.toml"))
    monkeypatch.setattr(paths, "code_root", lambda: checkout)
    return checkout


def test_no_vault_anywhere_fails_loudly(legacy: Path) -> None:
    for lookup in (
        paths.vault_root,
        paths.private_dir,
        paths.applications_log,
        paths.outputs_dir,
        paths.profile_dir,
    ):
        with pytest.raises(paths.VaultError, match="No vault found"):
            lookup()


def test_sibling_vault_is_discovered(legacy: Path) -> None:
    sibling = legacy.parent / "job-o-matic-vault"
    sibling.mkdir()
    (sibling / ".jobomatic.toml").write_text("vault_version = 1\n", encoding="utf-8")
    assert paths.vault_root() == sibling.resolve()
    assert paths.applications_log() == sibling.resolve() / "applications" / "applications.jsonl"


def test_sibling_without_marker_is_ignored(legacy: Path) -> None:
    (legacy.parent / "job-o-matic-vault").mkdir()
    with pytest.raises(paths.VaultError, match="No vault found"):
        paths.vault_root()


def test_no_function_takes_an_explicit_root() -> None:
    """There is one way to locate data: the vault (ADR 0029)."""
    for name, function in inspect.getmembers(paths, inspect.isfunction):
        assert "root" not in inspect.signature(function).parameters, name


def test_vault_layout_when_env_var_names_a_valid_vault(tmp_vault: Path) -> None:
    vault = tmp_vault.resolve()
    assert paths.vault_root() == vault
    assert paths.private_dir() == vault / "private"
    assert paths.outputs_dir() == vault / "outputs"
    assert paths.applications_log() == vault / "applications" / "applications.jsonl"
    assert paths.evidence_index_path() == vault / "index" / "evidence.sqlite"
    assert paths.profile_dir() == vault / "profile"
    assert paths.learning_plans_dir() == vault / "outputs" / "learning-plans"


def test_vault_without_marker_fails_loudly(
    legacy: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JOBOMATIC_VAULT", str(tmp_path))
    with pytest.raises(paths.VaultError, match=r"\.jobomatic\.toml"):
        paths.vault_root()
    with pytest.raises(paths.VaultError):
        paths.outputs_dir()  # never silently falls back to the repo


def test_config_file_selects_the_vault(
    legacy: None, tmp_vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("JOBOMATIC_VAULT")
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'vault = "{tmp_vault}"\n', encoding="utf-8")
    monkeypatch.setenv("JOBOMATIC_CONFIG", str(cfg))
    assert paths.vault_root() == tmp_vault.resolve()


def test_env_var_beats_config_file(
    legacy: None, tmp_vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('vault = "/definitely/not/a/vault"\n', encoding="utf-8")
    monkeypatch.setenv("JOBOMATIC_CONFIG", str(cfg))
    assert paths.vault_root() == tmp_vault.resolve()


def test_invalid_config_toml_fails_loudly(
    legacy: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text("vault = = nope\n", encoding="utf-8")
    monkeypatch.setenv("JOBOMATIC_CONFIG", str(cfg))
    with pytest.raises(paths.VaultError, match="not valid TOML"):
        paths.vault_root()


def test_per_file_overrides_still_win_inside_a_vault(
    tmp_vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_JOBS_PRIVATE_DIR", str(tmp_path / "p"))
    monkeypatch.setenv("CLAUDE_JOBS_APPLICATIONS_LOG", str(tmp_path / "a.jsonl"))
    assert paths.private_dir() == tmp_path / "p"
    assert paths.applications_log() == tmp_path / "a.jsonl"


def test_consumers_follow_the_vault(tmp_vault: Path) -> None:
    from jobomatic import applications
    from jobomatic.fit import constraints

    assert applications.log_path() == tmp_vault.resolve() / "applications" / "applications.jsonl"
    assert constraints.constraints_path() == (
        tmp_vault.resolve() / "private" / "search-constraints.json"
    )


def test_mcp_allow_lists_follow_the_vault(tmp_vault: Path) -> None:
    from jobomatic.interfaces.mcp import server

    vault = tmp_vault.resolve()
    policy = server._policy()
    assert vault / "outputs" in policy.write_roots
    assert vault in policy.read_roots
    denied = policy.denied
    assert vault / "private" in denied
    assert vault / ".git" in denied
    assert paths.code_root() / "private" in denied  # the in-repo default stays denied too
