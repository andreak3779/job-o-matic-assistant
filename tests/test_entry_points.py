"""The commands: ``jobo``, ``python -m jobomatic``, the deprecated ``claude-jobs`` and the MCP server."""

from __future__ import annotations

import importlib
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _project() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_the_project_is_named_job_o_matic_assistant() -> None:
    assert _project()["name"] == "job-o-matic-assistant"


@pytest.mark.parametrize("script", ["jobo", "jobo-mcp", "claude-jobs"])
def test_every_declared_command_points_at_a_real_function(script: str) -> None:
    target = _project()["scripts"][script]
    module, _, attr = target.partition(":")
    assert callable(getattr(importlib.import_module(module), attr))


def test_python_dash_m_jobomatic_runs_the_same_cli() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "jobomatic", "--help"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert "usage: jobo" in result.stdout


def test_the_old_command_name_prints_a_notice_and_does_the_same_thing(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    from jobomatic.interfaces.cli import main as cli

    monkeypatch.setattr(cli, "main", lambda argv=None: 7)
    assert cli.deprecated(["x"]) == 7
    assert "now called jobo" in capsys.readouterr().err


def test_the_old_forwarding_packages_are_gone() -> None:
    assert not (ROOT / "cli").exists()
    assert not (ROOT / "mcp_server").exists()


def test_the_mcp_server_has_a_main_for_claude_desktop() -> None:
    server = importlib.import_module("jobomatic.interfaces.mcp.server")
    assert callable(server.main)
