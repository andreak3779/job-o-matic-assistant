"""A running MCP server tells the user to restart when the code on disk has changed (not the vault)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from jobomatic.interfaces.mcp import freshness, server


def _package(tmp_path: Path) -> Path:
    pkg = tmp_path / "pkg"
    (pkg / "sub").mkdir(parents=True)
    (pkg / "a.py").write_text("x = 1\n")
    (pkg / "sub" / "b.py").write_text("y = 2\n")
    (pkg / "__pycache__").mkdir()
    (pkg / "__pycache__" / "a.cpython-312.pyc.py").write_text("ignored")
    return pkg


def test_unchanged_code_is_not_stale(tmp_path: Path) -> None:
    pkg = _package(tmp_path)
    assert not freshness.is_stale(freshness.fingerprint(pkg), pkg)


def test_an_edited_file_is_stale(tmp_path: Path) -> None:
    pkg = _package(tmp_path)
    start = freshness.fingerprint(pkg)
    target = pkg / "sub" / "b.py"
    later = target.stat().st_mtime_ns + 5_000_000_000
    os.utime(target, ns=(later, later))
    assert freshness.is_stale(start, pkg)


def test_a_new_or_removed_module_is_stale(tmp_path: Path) -> None:
    pkg = _package(tmp_path)
    start = freshness.fingerprint(pkg)
    (pkg / "c.py").write_text("z = 3\n")
    os.utime(pkg / "c.py", ns=(1, 1))  # older than everything: only the count changes
    assert freshness.is_stale(start, pkg)
    (pkg / "c.py").unlink()
    assert not freshness.is_stale(start, pkg)


def test_pycache_is_ignored(tmp_path: Path) -> None:
    pkg = _package(tmp_path)
    start = freshness.fingerprint(pkg)
    (pkg / "__pycache__" / "new.py").write_text("noise")
    assert not freshness.is_stale(start, pkg)


def test_the_real_package_is_fresh_in_this_process() -> None:
    assert not freshness.is_stale(server._STARTED_WITH)


def test_a_stale_server_refuses_every_tool_call_with_the_restart_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server, "_STARTED_WITH", (0, 0))
    with pytest.raises(ToolError) as info:
        asyncio.run(server.mcp.call_tool("validate_profile", {}))
    assert "Fully quit Claude Desktop" in str(info.value)


def test_a_fresh_server_runs_the_tool() -> None:
    # No "restart" refusal: the call gets as far as the tool itself (which may pass or fail on its own).
    try:
        asyncio.run(server.mcp.call_tool("validate_profile", {}))
    except Exception as exc:  # the tool's own result is not what is tested here
        assert "Fully quit Claude Desktop" not in str(exc)
