"""A safety net for ADR 0028: what the commands print and what the MCP tools return.

Each case in ``tests/command_cases.py`` is run through the command line and through the matching
MCP tool, and what comes back is compared with a recorded file in ``tests/snapshots/commands/``.
The files hold the exit code, stdout and stderr (command line) or the status and content blocks
(MCP), with paths and today's date replaced so they do not change from run to run.

- A snapshot test fails when the output changes. If the change is deliberate, record it with
  ``UPDATE_SNAPSHOTS=1 pytest tests/test_command_snapshots.py`` and read the diff.
- The parity test checks that the two interfaces agree: the MCP text is what the command line
  printed, and the files an MCP tool attaches are the files the command line reported writing.
  It reads the two recorded files, so it holds before and after the commands move to structured
  results.
- Argparse's own error text is not recorded (it wraps by terminal width and differs between
  Python versions); the tests for invalid arguments check only the exit code and the option.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ContentBlock, EmbeddedResource, TextContent

from jobomatic.commands import cold_call, cover_letter, job_site_letter, resume
from jobomatic.interfaces.cli.main import main as cli_main
from jobomatic.interfaces.mcp import server
from tests.command_cases import (
    CASES,
    QUEBEC,
    STRETCH_SKILLS,
    UNRECORDED_TOOLS,
    Case,
    Env,
    _jd,
)

SNAPSHOTS = Path(__file__).resolve().parent / "snapshots" / "commands"
REPO = Path(__file__).resolve().parents[1]
_LONG = 30  # an attached file longer than this many lines is recorded as its first lines

CLI_CASES = [c for c in CASES if c.cli is not None]
MCP_CASES = [c for c in CASES if c.mcp is not None]
BOTH_CASES = [c for c in CASES if c.cli is not None and c.mcp is not None and c.same_text]


@pytest.fixture
def env(tmp_path: Path) -> Env:
    work, out = tmp_path / "work", tmp_path / "out"
    work.mkdir()
    out.mkdir()
    return Env(work=work, out=out)


# -- turning a run into text that does not change from day to day -----------------------------


def _normalize(text: str, tmp_path: Path) -> str:
    vault = Path(os.environ["JOBOMATIC_VAULT"])
    today = date.today()
    replacements = [
        (str(REPO), "<REPO>"),
        (str(tmp_path.resolve()), "<TMP>"),
        (str(tmp_path), "<TMP>"),
        (str(vault.parent.resolve()), "<SCRATCH>"),
        (str(vault.parent), "<SCRATCH>"),
        (str(Path.cwd()), "<CWD>"),
        (today.isoformat(), "<TODAY>"),
        (today.strftime("%B %Y"), "<MONTH-YEAR>"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    # The sidecar files record when they were made, to the second.
    text = re.sub(r"<TODAY>T\d\d:\d\d:\d\d(\.\d+)?Z", "<NOW>", text)
    # ...and how they were run, and a hash of the profile they were made from.
    text = re.sub(r'"command": ".*"', '"command": "<COMMAND>"', text)
    return re.sub(r'"profile_hash": "[0-9a-f]+"', '"profile_hash": "<HASH>"', text)


def _section(title: str, body: str) -> str:
    return f"--- {title}\n{body.rstrip(chr(10))}\n"


def _first_lines(text: str) -> str:
    lines = text.splitlines()
    if len(lines) <= _LONG:
        return text
    return "\n".join([*lines[:10], f"... ({len(lines)} lines in all)"])


def _resource_name(block: EmbeddedResource) -> str:
    return Path(unquote(urlparse(str(block.resource.uri)).path)).name


def _render_blocks(value: str | list[ContentBlock]) -> str:
    """The content blocks of a tool result. The first text block is the command's own output and
    is kept whole; attached files are recorded by name, type and (for text) their first lines."""
    blocks: list[ContentBlock] = (
        [TextContent(type="text", text=value)] if isinstance(value, str) else list(value)
    )
    parts = ["status: ok\n"]
    seen_text = False
    for block in blocks:
        if isinstance(block, TextContent):
            body = block.text if not seen_text else _first_lines(block.text)
            seen_text = True
            parts.append(_section("text", body))
        elif isinstance(block, EmbeddedResource):
            resource = block.resource
            if hasattr(resource, "text"):
                parts.append(
                    _section(
                        f"resource name={_resource_name(block)} mime={resource.mime_type} kind=text",
                        _first_lines(resource.text),
                    )
                )
            else:
                parts.append(
                    _section(
                        f"resource name={_resource_name(block)} mime={resource.mime_type} kind=blob",
                        "non-empty" if resource.blob else "EMPTY",
                    )
                )
        else:
            parts.append(_section(f"other {block.type}", ""))
    return "".join(parts)


def _run_cli(case: Case, env: Env, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> str:
    assert case.cli is not None
    if case.setup:
        case.setup(env)
    argv = case.cli(env)
    capsys.readouterr()  # drop anything a setup step printed
    code = cli_main(argv)
    captured = capsys.readouterr()
    text = f"exit: {code}\n" + _section("stdout", captured.out) + _section("stderr", captured.err)
    return _normalize(text, tmp_path)


def _run_mcp(case: Case, env: Env, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> str:
    assert case.mcp is not None
    if case.setup:
        case.setup(env)
    capsys.readouterr()  # drop anything a setup step printed
    try:
        value = case.mcp(env)
    except ToolError as exc:
        _assert_stdout_untouched(capsys)
        return _normalize("status: error\n" + _section("message", str(exc)), tmp_path)
    _assert_stdout_untouched(capsys)
    return _normalize(_render_blocks(value), tmp_path)


def _assert_stdout_untouched(capsys: pytest.CaptureFixture[str]) -> None:
    """The MCP server speaks its protocol on stdout, so a tool must never print there."""
    assert capsys.readouterr().out == ""


def _assert_snapshot(kind: str, case_id: str, text: str) -> None:
    path = SNAPSHOTS / kind / f"{case_id}.txt"
    if os.environ.get("UPDATE_SNAPSHOTS"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    assert path.exists(), f"no snapshot {path}; record it with UPDATE_SNAPSHOTS=1"
    assert text == path.read_text(encoding="utf-8")


# -- the recorded output ----------------------------------------------------------------------


@pytest.mark.parametrize("case", CLI_CASES, ids=[c.id for c in CLI_CASES])
def test_the_command_line_output_is_unchanged(
    case: Case, env: Env, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _assert_snapshot("cli", case.id, _run_cli(case, env, tmp_path, capsys))


@pytest.mark.parametrize("case", MCP_CASES, ids=[c.id for c in MCP_CASES])
def test_the_mcp_tool_result_is_unchanged(
    case: Case, env: Env, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _assert_snapshot("mcp", case.id, _run_mcp(case, env, tmp_path, capsys))


# -- the two interfaces agree -----------------------------------------------------------------


def _sections(text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for chunk in re.split(r"^--- ", text, flags=re.MULTILINE)[1:]:
        title, _, body = chunk.partition("\n")
        found.append((title, body))
    return found


def _read(kind: str, case_id: str) -> str:
    return (SNAPSHOTS / kind / f"{case_id}.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("case", BOTH_CASES, ids=[c.id for c in BOTH_CASES])
def test_the_mcp_tool_returns_what_the_command_line_prints(case: Case) -> None:
    cli = dict(_sections(_read("cli", case.id)))
    exit_code = int(_read("cli", case.id).split("\n", 1)[0].removeprefix("exit: "))
    printed = cli["stdout"] + (f"\n{cli['stderr']}" if cli["stderr"].strip() else "")

    mcp_text = _read("mcp", case.id)
    mcp = _sections(mcp_text)
    if exit_code != 0:
        assert mcp_text.startswith("status: error\n")
        assert mcp[0][0] == "message"
        assert mcp[0][1].strip() == printed.strip()
        return

    assert mcp_text.startswith("status: ok\n")
    assert mcp[0][0] == "text"
    assert mcp[0][1].strip() == printed.strip()

    wrote = sorted(
        Path(line.removeprefix("Wrote ")).name
        for line in cli["stdout"].splitlines()
        if line.startswith("Wrote ")
    )
    attached = sorted(
        [t.split(" ")[1].removeprefix("name=") for t, _ in mcp if t.startswith("resource ")]
        + [b.splitlines()[0].removeprefix("### ") for t, b in mcp[1:] if b.startswith("### ")]
    )
    assert attached == wrote


# -- the inventory ----------------------------------------------------------------------------


def test_every_mcp_tool_is_recorded_or_excused() -> None:
    """The tool list cannot change without a case (or a stated reason) changing with it."""
    registered = {tool.name for tool in asyncio.run(server.mcp.list_tools())}
    recorded = {case.tool for case in CASES if case.tool}
    assert registered == recorded | set(UNRECORDED_TOOLS)


def test_every_snapshot_belongs_to_a_case() -> None:
    expected = {f"cli/{c.id}.txt" for c in CLI_CASES} | {f"mcp/{c.id}.txt" for c in MCP_CASES}
    present = {str(p.relative_to(SNAPSHOTS)) for p in SNAPSHOTS.glob("*/*.txt")}
    assert present == expected


# -- invalid arguments (exit code and option only) --------------------------------------------


def test_an_invalid_stage_is_refused_by_the_command_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_main(["interview-prep", str(QUEBEC), "--stage", "not-a-stage"])
    assert excinfo.value.code == 2
    assert "--stage" in capsys.readouterr().err


# -- the gates belong to the command, not to the command line's dispatcher (ADR 0028) --------
# A command called directly, as ``python -m jobomatic.commands.resume`` or a future adapter would,
# must refuse what the gate refuses and write nothing.


@pytest.mark.parametrize(
    "module, suffix",
    [(resume, ".docx"), (cover_letter, ".docx"), (job_site_letter, ".txt"), (cold_call, ".docx")],
    ids=["resume", "cover_letter", "job_site_letter", "cold_call"],
)
def test_a_command_refuses_a_location_pass_when_called_directly(
    module, suffix: str, env: Env
) -> None:
    out = env.out / f"refused{suffix}"
    assert module.main([str(QUEBEC), "--out", str(out)]) == 2
    assert not out.exists()


@pytest.mark.parametrize("module", [resume, cover_letter], ids=["resume", "cover_letter"])
def test_a_command_refuses_a_stretch_until_confirmed_when_called_directly(module, env: Env) -> None:
    out = env.out / "refused.docx"
    assert module.main([_jd(env, "stretch.md", *STRETCH_SKILLS), "--out", str(out)]) == 2
    assert not out.exists()
