"""The commands return results; they do not print (ADR 0028).

A command's ``run()`` and everything under it must not write to stdout or capture it: the command
line prints a result with ``emit``, and the MCP server returns it, and stdout is the MCP protocol
channel. The one place a command module may print is its own ``main``, which is the command line
(reading the file the user named, and saying when it cannot).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "jobomatic"
MODULES = sorted([*(SRC / "commands").glob("*.py"), *(SRC / "presence").glob("*.py")])

# Not yet moved to structured results: the platform resume and cover letter templates (printed by
# the command line, which no other interface offers), and the helper they use.
STILL_PRINTS = {("support.py", "print_wrote")}


def _prints(path: Path) -> list[tuple[str, int]]:
    """Each call to ``print`` in the module, with the top-level function it sits in."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[str, int]] = []
    for top in tree.body:
        if not isinstance(top, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        for node in ast.walk(top):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                found.append((top.name, node.lineno))
    return found


@pytest.mark.parametrize("path", MODULES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_a_command_prints_only_in_its_own_main(path: Path) -> None:
    offenders = [
        f"{path.name}:{line} in {name}()"
        for name, line in _prints(path)
        if name != "main" and (path.name, name) not in STILL_PRINTS
    ]
    assert not offenders, "print() outside main(): " + ", ".join(offenders)


def test_nothing_captures_stdout() -> None:
    """``redirect_stdout`` is not thread-safe and is not how a result is read any more."""
    offenders = [
        str(path.relative_to(SRC))
        for path in sorted(SRC.rglob("*.py"))
        if "redirect_stdout" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_the_mcp_server_reads_no_printed_text() -> None:
    server = (SRC / "interfaces" / "mcp" / "server.py").read_text(encoding="utf-8")
    for forbidden in ("_run_cli", "_WROTE_RE", "_CLI_LOCK", "cli_main", "Wrote "):
        assert forbidden not in server, forbidden
