"""Expose the application-workflow skills to Claude Desktop as MCP prompts.

The skills in ``.claude/skills/<name>/SKILL.md`` are written for Claude Code, which can run shell
commands (``python -m jobomatic ...``). Claude Desktop has the MCP tools instead, so each
prompt is the skill's own text behind a short preamble that says which tool to call in place of
each command. The skill files stay the single source: nothing is copied or edited.

Only skills whose commands all have a tool are listed. The importers (``learning import``), the
part-time resume (``render``) and the learning-plan skills (``learning lookup``) need a shell or
file access that Desktop does not have, so they stay Claude Code only (see the README).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.prompts import Prompt

from jobomatic import paths

# Skill folder name -> the prompt name Desktop shows (the skill's own hyphenated name).
CURATED_SKILLS: tuple[str, ...] = (
    "job_description_fit",
    "gap_analysis_job_description",
    "create_a_cover_letter_and_tailored_resume_for_job_description",
    "interview_prep",
    "interview_practice",
    "interview_practice_job_description",
    "post_interview_thank_you_letter",
    "cold_outreach_recruiter_letter",
    "salary_research",
)

# What a skill tells Claude Code to run -> the MCP tool that does the same job.
COMMAND_TO_TOOL: dict[str, str] = {
    "fit-check": "fit_check",
    "gap-analysis": "gap_analysis",
    "generate-resume": "generate_resume",
    "generate-cover-letter": "generate_cover_letter",
    "generate-cold-call": "generate_cold_call",
    "generate-job-site": "generate_job_site_letter",
    "generate-thank-you": "generate_thank_you",
    "interview-prep": "interview_prep",
    "applications check": "applications_check",
    "applications list": "applications_list",
    "applications applied": "applications_mark_applied",
    "applications status": "applications_set_status",
    "constraints show": "search_constraints",
    "profile show": "profile_summary (public facts only)",
    "profile validate": "validate_profile",
    "evidence / search": "search_evidence",
}

_PREAMBLE = """\
You are in Claude Desktop, connected to the job-o-matic tools. You cannot run shell commands here.
Where the workflow below tells you to run a `claude-jobs` / `python -m jobomatic` command,
call the tool that does the same job (its parameters mirror the command's options):

{mapping}

`render`, `application-dir`, `learning ...` and file-import commands have no tool: do not try to
run them. For tailored documents use `generate_application_documents` (or `generate_resume` and
`generate_cover_letter`); each checks the fit rating, the duplicate-application log and the pay
minimum first and refuses with a reason if one of them fails. A Stretch or Worth a try rating can be
confirmed past: list the gaps, ask the user, and only if they say yes call the tool again with
`confirm_gaps=true`; a Pass (skills or location) cannot. Likewise `confirm_reapply` and
`confirm_below_minimum` are set only after the user says so. Never mark an application as applied
unless the user says they submitted it. Ask the user before adding any self-identification
information to a document, once per posting. If a result carries a "Low-confidence result" notice (more than half the required skills show
no evidence), tell the user to read the posting themselves. "Soft requirements" are education,
years, title-level and soft-skill lines: show them as written, never score them, and do not decide whether they are met.
If a result lists "Terms to confirm" (a word that is
also a skill name, read as ordinary English), ask the user which meaning the posting intends.
If a result lists "Possible typos" (a word one letter from a skill name, not scored), ask the user
whether the posting meant that skill.

Workflow
--------
"""


@dataclass(frozen=True)
class Skill:
    folder: str
    name: str
    description: str
    body: str


def skills_dir() -> Path:
    return paths.code_root() / ".claude" / "skills"


def load_skill(folder: str, root: Path | None = None) -> Skill:
    """Read one ``SKILL.md``: the ``---`` front matter gives name and description, the rest is the body."""
    text = ((root or skills_dir()) / folder / "SKILL.md").read_text(encoding="utf-8")
    _, front, body = text.split("---", 2)
    meta = yaml.safe_load(front) or {}
    description = " ".join(str(meta.get("description", "")).split())
    return Skill(folder, str(meta.get("name", folder)), description, body.strip())


def _short(description: str, limit: int = 200) -> str:
    """The first sentence of a long skill description, for Desktop's prompt picker."""
    first = description.split(". ")[0].rstrip(".") + "."
    return first if len(first) <= limit else first[: limit - 1].rstrip() + "…"


def _preamble() -> str:
    mapping = "\n".join(f"- {command} -> {tool}" for command, tool in COMMAND_TO_TOOL.items())
    return _PREAMBLE.format(mapping=mapping)


def prompt_text(skill: Skill, jd: str = "") -> str:
    parts = [_preamble() + skill.body]
    if jd.strip():
        parts.append("The job description to work on:\n\n" + jd.strip())
    return "\n\n".join(parts)


def _make_prompt(skill: Skill) -> Prompt:
    def render(jd: str = "") -> str:
        return prompt_text(skill, jd)

    render.__doc__ = skill.description
    return Prompt.from_function(
        render,
        name=skill.name,
        title=skill.name.replace("-", " ").title(),
        description=_short(skill.description),
    )


def build_prompts(
    folders: tuple[str, ...] = CURATED_SKILLS, root: Path | None = None
) -> list[Prompt]:
    return [_make_prompt(load_skill(folder, root)) for folder in folders]


def register(server: MCPServer) -> int:
    """Add the curated prompts to ``server``; returns how many were added."""
    prompts = build_prompts()
    for prompt in prompts:
        server.add_prompt(prompt)
    return len(prompts)
