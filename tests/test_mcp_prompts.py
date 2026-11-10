"""The skills exposed to Claude Desktop as prompts, and the two tools added with them."""

from __future__ import annotations

import asyncio
import re

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from jobomatic import bootstrap
from jobomatic.interfaces.mcp import server, skill_prompts
from tests.retrieval_fakes import FakeEmbedder

# Commands a curated skill may mention that have no tool, so Desktop must not try them.
NO_TOOL = {"render", "application-dir", "applications import-csv"}


def _names(items) -> set[str]:
    return {item.name for item in items}


def test_the_server_is_called_job_o_matic():
    assert server.mcp.name == "job-o-matic"


def test_every_tool_named_in_the_mapping_exists():
    tools = _names(asyncio.run(server.mcp.list_tools()))
    for tool in skill_prompts.COMMAND_TO_TOOL.values():
        assert tool.split(" ")[0] in tools, tool


def test_each_curated_skill_becomes_one_prompt():
    prompts = _names(asyncio.run(server.mcp.list_prompts()))
    expected = {skill_prompts.load_skill(f).name for f in skill_prompts.CURATED_SKILLS}
    assert prompts == expected and len(expected) == len(skill_prompts.CURATED_SKILLS)


def test_a_prompt_is_the_skill_text_behind_the_tool_preamble():
    skill = skill_prompts.load_skill("post_interview_thank_you_letter")
    text = skill_prompts.prompt_text(skill)
    assert text.startswith("You are in Claude Desktop")
    assert "generate-thank-you -> generate_thank_you" in text
    assert skill.body in text
    assert "The job description to work on" not in text


def test_a_job_description_argument_is_appended():
    skill = skill_prompts.load_skill("job_description_fit")
    text = skill_prompts.prompt_text(skill, "  Senior Developer at Acme  ")
    assert text.rstrip().endswith("Senior Developer at Acme")


def test_prompt_descriptions_are_short_enough_for_a_picker():
    for prompt in asyncio.run(server.mcp.list_prompts()):
        assert prompt.description and len(prompt.description) <= 200


def test_curated_skills_only_need_commands_that_have_a_tool():
    for folder in skill_prompts.CURATED_SKILLS:
        body = skill_prompts.load_skill(folder).body
        used = {
            m.strip()
            for m in re.findall(
                r"(?:cli\.claude_jobs|claude-jobs) +([a-z][a-z-]*(?: +[a-z][a-z-]*)?)", body
            )
        }
        for command in used:
            known = command in skill_prompts.COMMAND_TO_TOOL or command.split(" ")[0] in {
                c.split(" ")[0] for c in skill_prompts.COMMAND_TO_TOOL
            }
            assert known or command in NO_TOOL or command.split(" ")[0] in NO_TOOL, (
                folder,
                command,
            )


# ── search_evidence and profile_summary ──────────────────────────────────────


@pytest.fixture
def fake(monkeypatch):
    embedder = FakeEmbedder()
    monkeypatch.setattr(bootstrap, "retrieval_embedder", lambda model=None: embedder)
    return embedder


def test_search_evidence_finds_a_course_and_never_returns_private_prose(fake, monkeypatch):
    run = server._run_cli  # the fake embedder scores low, so lift the cutoff as the CLI tests do
    monkeypatch.setattr(server, "_run_cli", lambda argv: run([*argv, "--min-score", "0"]))
    out = server.search_evidence("message broker routing")
    assert "Message Queues in Practice" in out
    assert "(resume" not in out and "(interview story" not in out


def test_search_evidence_only_asks_for_cloud_safe_kinds(monkeypatch):
    seen: list[list[str]] = []
    monkeypatch.setattr(server, "_run_cli", lambda argv: seen.append(argv) or "ok")
    server.search_evidence("terraform", k=500)
    argv = seen[0]
    kinds = {argv[i + 1] for i, a in enumerate(argv) if a == "--kind"}
    assert kinds == {"course", "lab", "module", "learning_path", "project"}
    assert argv[argv.index("--k") + 1] == "10"


def test_search_evidence_refuses_an_empty_query():
    with pytest.raises(ToolError):
        server.search_evidence("   ")


def test_profile_summary_is_the_public_view():
    out = server.profile_summary()
    assert "Professional Headline" in out


def test_profile_summary_asks_for_the_public_view_only(monkeypatch):
    seen: list[list[str]] = []
    monkeypatch.setattr(server, "_run_cli", lambda argv: seen.append(argv) or "ok")
    server.profile_summary()
    assert seen[0] == ["profile", "show", "--public", "facts"]
