"""The gates hold for both interfaces, and ``confirm_gaps`` passes the user's decision through."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from jobomatic.interfaces.cli.main import main
from jobomatic.interfaces.mcp.server import (
    generate_application_documents,
    generate_cover_letter,
    generate_resume,
)

COVERED = ["C#", "SQL", "Angular", "Docker", "Git"]


def _write(tmp_path: Path, name: str, *required: str) -> Path:
    lines = "".join(f"- {line}\n" for line in required)
    path = tmp_path / name
    path.write_text(f"# Dev | Acme Corp\n\n## Requirements\n{lines}", encoding="utf-8")
    return path


@pytest.fixture
def stretch(tmp_path: Path) -> Path:
    return _write(tmp_path, "stretch.md", "Rust", *COVERED, "Python", "Jira")


@pytest.fixture
def skills_pass(tmp_path: Path) -> Path:
    return _write(tmp_path, "pass.md", "Rust", "Kotlin", *COVERED)


@pytest.mark.parametrize("command", ["generate-resume", "generate-cover-letter"])
def test_the_command_line_refuses_a_stretch_until_confirmed(
    tmp_path: Path, stretch: Path, capsys, command: str
) -> None:
    out = tmp_path / "doc.docx"
    assert main([command, str(stretch), "--out", str(out)]) == 2
    assert not out.exists()
    err = capsys.readouterr().err
    assert "REFUSED" in err and "--confirm-gaps" in err


@pytest.mark.parametrize("command", ["generate-resume", "generate-cover-letter"])
def test_the_command_line_proceeds_past_a_stretch_when_confirmed(
    tmp_path: Path, stretch: Path, capsys, command: str
) -> None:
    out = tmp_path / "doc.docx"
    assert main([command, str(stretch), "--out", str(out), "--confirm-gaps"]) == 0
    assert out.exists()
    assert "Proceeding past a Stretch rating" in capsys.readouterr().out


def test_the_command_line_never_confirms_past_a_skills_pass(
    tmp_path: Path, skills_pass: Path, capsys
) -> None:
    out = tmp_path / "doc.docx"
    assert main(["generate-resume", str(skills_pass), "--out", str(out), "--confirm-gaps"]) == 2
    assert not out.exists()
    assert "cannot be confirmed past" in capsys.readouterr().err


def test_the_tool_refuses_a_stretch_until_confirmed(tmp_path: Path, stretch: Path) -> None:
    out = tmp_path / "resume.docx"
    with pytest.raises(ToolError, match="confirm_gaps"):
        generate_resume(str(stretch), out=str(out))
    assert not out.exists()
    blocks = generate_resume(str(stretch), out=str(out), confirm_gaps=True)
    assert out.exists() and blocks


def test_the_tool_never_confirms_past_a_skills_pass(tmp_path: Path, skills_pass: Path) -> None:
    out = tmp_path / "cover.docx"
    with pytest.raises(ToolError, match="cannot be confirmed past"):
        generate_cover_letter(str(skills_pass), out=str(out), confirm_gaps=True)
    assert not out.exists()


def test_the_combined_tool_passes_the_confirmation_to_both_documents(stretch: Path) -> None:
    with pytest.raises(ToolError, match="confirm_gaps"):
        generate_application_documents(str(stretch))
    blocks = generate_application_documents(str(stretch), confirm_gaps=True)
    assert blocks
