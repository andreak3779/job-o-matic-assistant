"""Shared pytest fixtures/helpers for the test suite."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

DEMO_VAULT = Path(__file__).resolve().parents[1] / "demo-vault"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolate_personal_data(tmp_path_factory, monkeypatch):
    """Give every test a throwaway copy of the fictional demo vault.

    Generators and the CLI record drafts in the applications log, read the private
    search-constraints and load the profile from the vault by default; no test may ever touch
    the real vault. The copy is separate from ``tmp_path`` so tests that inspect ``tmp_path``
    contents are unaffected, and each test may change its own copy freely.
    """
    scratch = tmp_path_factory.mktemp("personal")
    vault = scratch / "vault"
    shutil.copytree(DEMO_VAULT, vault)
    for sub in ("private", "applications", "outputs", "imports", "index"):
        (vault / sub).mkdir(exist_ok=True)
    monkeypatch.setenv("CLAUDE_JOBS_APPLICATIONS_LOG", str(scratch / "applications.jsonl"))
    monkeypatch.setenv("CLAUDE_JOBS_PRIVATE_DIR", str(scratch / "private"))
    monkeypatch.setenv("JOBOMATIC_VAULT", str(vault))
    monkeypatch.setenv("JOBOMATIC_CONFIG", str(scratch / "no-config.toml"))
    # The MCP server does not read the code repository (src/jobomatic/interfaces/mcp/access.py). The sample job
    # descriptions live in tests/fixtures, so the tests opt that one folder in, the same way a
    # user would with CLAUDE_JOBS_ALLOWED_DIRS. Tests that check this variable set their own.
    monkeypatch.setenv("CLAUDE_JOBS_ALLOWED_DIRS", str(FIXTURES))
    return scratch


@pytest.fixture
def tmp_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway vault with no profile (marker plus the standard folders and the example
    location preferences), selected through JOBOMATIC_VAULT.

    Drops the per-file overrides the autouse fixture sets, so ``jobomatic.paths`` resolves
    everything inside this vault.
    """
    vault = tmp_path / "vault"
    for sub in ("profile", "private", "applications", "imports", "outputs", "index"):
        (vault / sub).mkdir(parents=True)
    (vault / ".jobomatic.toml").write_text("vault_version = 1\n", encoding="utf-8")
    (vault / "profile" / "location-preferences.json").write_text(
        (DEMO_VAULT / "profile" / "location-preferences.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.delenv("CLAUDE_JOBS_APPLICATIONS_LOG", raising=False)
    monkeypatch.delenv("CLAUDE_JOBS_PRIVATE_DIR", raising=False)
    monkeypatch.setenv("JOBOMATIC_VAULT", str(vault))
    return vault
