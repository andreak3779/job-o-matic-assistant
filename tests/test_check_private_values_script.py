"""scripts/check_private_values.py must not fail a commit just because there is no vault.

The pre-commit hook runs it for everyone. A contributor with only the code has no vault, and the
script used to crash with a traceback on the salary check, which blocked every commit.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env_without_a_vault(not_a_vault: Path) -> dict[str, str]:
    """The environment a contributor has: no per-file overrides, and a vault setting that points
    at a folder without the vault marker (the case that always raises, whatever sits next to the
    checkout)."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("CLAUDE_JOBS_", "JOBOMATIC_"))
    }
    env["JOBOMATIC_VAULT"] = str(not_a_vault)
    return env


def test_both_checks_skip_and_the_script_passes_without_a_vault(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_private_values.py")],
        cwd=ROOT,
        env=_env_without_a_vault(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    assert "salary check skipped" in result.stdout
    assert "identifier check skipped" in result.stdout


def test_an_old_variable_name_is_an_error_not_a_reason_to_skip_the_checks(tmp_path: Path) -> None:
    # ADR 0030: a renamed variable raises the error this script reads as "no vault". Left like
    # that, a stale variable in the shell would quietly switch both leak checks off.
    env = _env_without_a_vault(tmp_path)
    env["CLAUDE_JOBS_PRIVATE_DIR"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_private_values.py")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "JOBOMATIC_PRIVATE_DIR" in result.stderr
    assert "skipped" not in result.stdout
