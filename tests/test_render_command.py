"""The render command and the MCP tools over it (ADR 0035): content written by a model, laid out by
code, behind the same gate as the generators."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import EmbeddedResource, TextContent

from jobomatic import applications, paths
from jobomatic.commands import render as render_command
from jobomatic.commands.support import Confirmations
from jobomatic.documents import service
from jobomatic.interfaces.mcp import server
from scripts import golden_outputs
from tests.command_cases import PASS_SKILLS, STRETCH_SKILLS, Env, _applied_today, _jd

FIXTURES = Path(__file__).parent / "fixtures"
CONTENT = FIXTURES / "documents"
STRONG = FIXTURES / "strong-fit-jd.md"


def _resume_json() -> str:
    return (CONTENT / "resume.json").read_text(encoding="utf-8")


def _letter_json() -> str:
    return (CONTENT / "cover-letter.json").read_text(encoding="utf-8")


@pytest.fixture
def stretch_jd(tmp_path: Path) -> str:
    return _jd(Env(tmp_path, tmp_path), "stretch.md", *STRETCH_SKILLS)


@pytest.fixture
def pass_jd(tmp_path: Path) -> str:
    return _jd(Env(tmp_path, tmp_path), "skills-pass.md", *PASS_SKILLS)


def _first_text(blocks: list) -> str:
    return next(b.text for b in blocks if isinstance(b, TextContent))


# -- the tools exist, and take what a client sends --------------------------------------------


def test_the_render_tools_are_registered() -> None:
    tools = {tool.name for tool in asyncio.run(server.mcp.list_tools())}
    assert {"render_schema", "render_draft", "render_resume", "render_cover_letter"} <= tools


def test_render_schema_lists_the_fields_of_each_kind() -> None:
    assert "tagline" in json.loads(server.render_schema("resume"))["properties"]
    assert "bring" in json.loads(server.render_schema("cover-letter"))["properties"]


def test_the_part_time_kinds_are_not_rendered_by_this_command(tmp_path: Path) -> None:
    result = render_command.run("part-time-resume", "{}", out=tmp_path / "x.docx")
    assert result.status == "error" and "unknown document kind" in result.messages[-1].text
    assert not (tmp_path / "x.docx").exists()


# -- render ----------------------------------------------------------------------------------


def test_render_resume_accepts_an_object_as_well_as_json_text(tmp_path: Path) -> None:
    content = json.loads(_resume_json())
    server.render_resume(content, str(STRONG), out=str(tmp_path / "a.docx"))
    server.render_resume(_resume_json(), str(STRONG), out=str(tmp_path / "b.docx"))
    first = golden_outputs.docx_text(tmp_path / "a.docx")
    assert first.splitlines()[0] == "SARAH ASHFORD"
    assert first == golden_outputs.docx_text(tmp_path / "b.docx")


def test_render_files_the_document_in_the_postings_folder_and_logs_a_draft_only() -> None:
    blocks = server.render_resume(_resume_json(), STRONG.read_text(encoding="utf-8"))
    [app] = applications.load_applications()
    assert app.status == "drafted" and "resume" in app.documents  # never applied
    folder = paths.output_dir("application", name=applications.folder_name_for(app))
    assert (folder / "resume.docx").is_file()
    assert any(isinstance(b, EmbeddedResource) for b in blocks)  # the client gets the file
    server.render_cover_letter(_letter_json(), STRONG.read_text(encoding="utf-8"))
    assert (folder / "cover-letter.docx").is_file()
    assert len(applications.load_applications()) == 1


def test_bad_content_names_the_field_and_writes_nothing(tmp_path: Path) -> None:
    data = json.loads(_resume_json())
    data["summary"] = ["a", "b", "c"]
    out = tmp_path / "r.docx"
    with pytest.raises(ToolError, match="summary"):
        server.render_resume(data, str(STRONG), out=str(out))
    assert not out.exists()
    assert applications.load_applications() == []  # nothing logged for a document never made


def test_not_json_is_an_error_not_a_crash(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="not valid JSON"):
        server.render_cover_letter("{oops", str(STRONG), out=str(tmp_path / "c.docx"))


def test_a_cover_letter_is_not_accepted_as_a_resume(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="invalid resume"):
        server.render_resume(_letter_json(), str(STRONG), out=str(tmp_path / "r.docx"))


# -- the gate holds, as for the generators -----------------------------------------------------


@pytest.mark.parametrize("tool", ["render_resume", "render_cover_letter"])
def test_a_stretch_posting_is_refused_until_the_user_confirms(
    tool: str, tmp_path: Path, stretch_jd: str
) -> None:
    content = _resume_json() if tool == "render_resume" else _letter_json()
    call = getattr(server, tool)
    out = tmp_path / "doc.docx"
    with pytest.raises(ToolError, match="confirm_gaps"):
        call(content, stretch_jd, out=str(out))
    assert not out.exists() and applications.load_applications() == []
    call(content, stretch_jd, out=str(out), confirm_gaps=True)
    assert out.is_file()


def test_a_pass_cannot_be_confirmed_past(tmp_path: Path, pass_jd: str) -> None:
    out = tmp_path / "r.docx"
    with pytest.raises(ToolError):
        server.render_resume(_resume_json(), pass_jd, out=str(out), confirm_gaps=True)
    assert not out.exists()


def test_a_duplicate_application_is_refused_until_confirmed(tmp_path: Path) -> None:
    _applied_today(Env(tmp_path, tmp_path))
    out = tmp_path / "r.docx"
    with pytest.raises(ToolError, match="confirm_reapply"):
        server.render_resume(_resume_json(), str(STRONG), out=str(out))
    server.render_resume(_resume_json(), str(STRONG), out=str(out), confirm_reapply=True)
    assert out.is_file()


def test_without_a_posting_the_command_needs_an_output_path_and_runs_no_gate(
    tmp_path: Path,
) -> None:
    result = render_command.run("resume", _resume_json())
    assert result.status == "error" and "output path" in result.messages[-1].text
    out = tmp_path / "r.docx"
    result = render_command.run("resume", _resume_json(), out=out)
    assert result.status == "ok" and result.written == (out,)  # no posting: no sidecar, no log
    assert applications.load_applications() == []


# -- draft -------------------------------------------------------------------------------------


def test_the_draft_is_content_that_renders_back_unchanged(tmp_path: Path) -> None:
    blocks = server.render_draft("resume", str(STRONG))
    draft = _first_text(blocks)
    service.parse_content("resume", draft)  # valid for the schema as it stands
    assert "Fit Rating" not in draft  # the gate's notes are a block of their own
    assert "Fit Rating: Strong" in blocks[1].text
    out = tmp_path / "r.docx"
    server.render_resume(draft, str(STRONG), out=str(out))
    assert out.is_file()


def test_the_cover_letter_draft_is_valid_content() -> None:
    draft = _first_text(server.render_draft("cover-letter", str(STRONG), company="Acme"))
    letter = service.parse_content("cover-letter", draft)
    assert letter.company == "Acme"


def test_a_draft_writes_nothing_and_logs_nothing() -> None:
    server.render_draft("resume", str(STRONG))
    server.render_draft("cover-letter", str(STRONG))
    assert applications.load_applications() == []
    assert not list(paths.outputs_dir().glob("applications/*"))


def test_a_draft_is_gated_like_the_documents_are(stretch_jd: str, pass_jd: str) -> None:
    with pytest.raises(ToolError, match="confirm_gaps"):
        server.render_draft("resume", stretch_jd)
    assert _first_text(server.render_draft("resume", stretch_jd, confirm_gaps=True))
    with pytest.raises(ToolError):
        server.render_draft("resume", pass_jd, confirm_gaps=True)


def test_the_draft_matches_what_the_generator_renders(tmp_path: Path) -> None:
    """Rendering the draft unchanged gives the same text as ``generate-resume``: the two paths start
    from one set of facts."""
    from jobomatic.commands import resume as resume_command

    generated = resume_command.run(
        STRONG.read_text(encoding="utf-8"), out=tmp_path / "generated.docx", confirm=Confirmations()
    )
    assert generated.status == "ok"
    draft = render_command.draft("resume", STRONG.read_text(encoding="utf-8"))
    assert draft.data is not None
    rendered = render_command.run("resume", draft.data.content, out=tmp_path / "rendered.docx")
    assert rendered.status == "ok"
    assert golden_outputs.docx_text(tmp_path / "generated.docx") == golden_outputs.docx_text(
        tmp_path / "rendered.docx"
    )
