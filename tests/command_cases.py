"""The commands whose console output and MCP results are recorded (ADR 0028).

Each ``Case`` names one command, the argv the command line gets for it and the call the matching
MCP tool gets, both built from the same inputs. ``tests/test_command_snapshots.py`` records what
each interface returns and checks that the two agree, so the commands can be moved to structured
results (ADR 0028) without the output changing.

Cases that need a starting state (an application already in the log, a salary file) say so in
``setup``. Every test starts from a fresh copy of the fictional demo vault (``tests/conftest.py``),
so a case never sees another case's log.
"""

from __future__ import annotations

import contextlib
import io
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jobomatic import applications, paths
from jobomatic.interfaces.cli.main import main as cli_main
from jobomatic.interfaces.mcp import server

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"
STRONG = FIXTURES / "strong-fit-jd.md"
QUEBEC = FIXTURES / "strong-skills-quebec-jd.md"

COVERED = ("C#", "SQL", "Angular", "Docker", "Git")
STRETCH_SKILLS = ("Rust", *COVERED, "Python", "Jira")
PASS_SKILLS = ("Rust", "Kotlin", *COVERED)

DISCUSSION = "We discussed the team's roadmap."


@dataclass(frozen=True)
class Env:
    """Where a case may put files: ``work`` holds its inputs, ``out`` its outputs."""

    work: Path
    out: Path


@dataclass(frozen=True)
class Case:
    id: str
    cli: Callable[[Env], list[str]] | None = None
    tool: str | None = None  # the MCP tool this case calls, if any
    mcp: Callable[[Env], Any] | None = None
    setup: Callable[[Env], None] | None = None
    # False when the MCP adapter deliberately words the result itself (see the one case).
    same_text: bool = True


# -- inputs a case builds ---------------------------------------------------------------------


def _jd(env: Env, name: str, *required: str) -> str:
    """A small posting whose rating depends only on which of ``required`` the profile covers."""
    path = env.work / name
    lines = "".join(f"- {line}\n" for line in required)
    path.write_text(f"# Dev | Acme Corp\n\n## Requirements\n{lines}", encoding="utf-8")
    return str(path)


def _stretch(env: Env) -> str:
    return _jd(env, "stretch.md", *STRETCH_SKILLS)


def _skills_pass(env: Env) -> str:
    return _jd(env, "skills-pass.md", *PASS_SKILLS)


def _out(env: Env, name: str) -> str:
    return str(env.out / name)


def _role_config(env: Env) -> str:
    """The learning-plan config, with its output inside ``out``."""
    config = json.loads((REPO / "templates" / "roles" / "_example.json").read_text("utf-8"))
    config["output"] = _out(env, "plan.pdf")
    path = env.work / "role.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return str(path)


def _import_file(env: Env) -> str:
    entry = {
        "name": "Learn Azure Things",
        "type": "Course",
        "url": "https://app.pluralsight.com/library/courses/learn-azure-things",
        "duration": "1h 30m",
        "completion_percentage": "100.0%",
        "completed_on": "2026-11-08",
    }
    path = env.work / "pluralsight_import_2026-11-10.json"
    path.write_text(
        json.dumps({"format": "jobomatic-pluralsight-history", "version": 1, "entries": [entry]}),
        encoding="utf-8",
    )
    return str(path)


def _draft_id() -> str:
    found = applications.find_for_jd(STRONG.read_text(encoding="utf-8"))
    assert found is not None
    return found.id


# -- starting states --------------------------------------------------------------------------


def _quietly(argv: list[str]) -> None:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        assert cli_main(argv) == 0


def _drafted(env: Env) -> None:
    _quietly(["applications", "add", str(STRONG)])


def _in_phone_screen(env: Env) -> None:
    _drafted(env)
    _quietly(["applications", "status", _draft_id(), "phone_screen", "--next-step", "call"])


def _applied_today(env: Env) -> None:
    _quietly(["applications", "applied", "--jd", str(STRONG)])


def _salary_file(env: Env) -> None:
    paths.private_dir().mkdir(parents=True, exist_ok=True)
    (paths.private_dir() / "search-constraints.json").write_text(
        json.dumps({"min_permanent_base_cad": 90000, "min_contract_hourly_cad": 65}),
        encoding="utf-8",
    )


# -- the cases --------------------------------------------------------------------------------

CASES: tuple[Case, ...] = (
    # Fit rating and gap analysis.
    Case(
        "fit-check-strong",
        lambda e: ["fit-check", str(STRONG)],
        "fit_check",
        lambda e: server.fit_check(str(STRONG)),
    ),
    Case(
        "fit-check-location-pass",
        lambda e: ["fit-check", str(QUEBEC)],
        "fit_check",
        lambda e: server.fit_check(str(QUEBEC)),
    ),
    Case(
        "fit-check-missing-file",
        lambda e: ["fit-check", str(e.work / "missing.md")],
        "fit_check",
        lambda e: server.fit_check(str(e.work / "missing.md")),
        # The MCP adapter checks a path itself and says "job description file not found".
        same_text=False,
    ),
    Case(
        "gap-analysis",
        lambda e: ["gap-analysis", str(STRONG), "--out", _out(e, "gap.md")],
        "gap_analysis",
        lambda e: server.gap_analysis(str(STRONG), out=_out(e, "gap.md")),
    ),
    # Profile and constraints.
    Case(
        "validate-profile",
        lambda e: ["profile", "validate"],
        "validate_profile",
        lambda e: server.validate_profile(),
    ),
    Case(
        "profile-summary",
        lambda e: ["profile", "show", "--public", "facts"],
        "profile_summary",
        lambda e: server.profile_summary(),
    ),
    Case(
        "constraints-not-configured",
        lambda e: ["constraints", "show"],
        "search_constraints",
        lambda e: server.search_constraints(),
    ),
    Case(
        "constraints-configured",
        lambda e: ["constraints", "show"],
        "search_constraints",
        lambda e: server.search_constraints(),
        _salary_file,
    ),
    # Profile-update drafts.
    Case(
        "linkedin",
        lambda e: ["generate-linkedin", "--out", _out(e, "li.md")],
        "generate_linkedin",
        lambda e: server.generate_linkedin(out=_out(e, "li.md")),
    ),
    Case(
        "github",
        lambda e: ["generate-github", "--out", _out(e, "gh.md")],
        "generate_github",
        lambda e: server.generate_github(out=_out(e, "gh.md")),
    ),
    Case(
        "jobgether",
        lambda e: ["generate-jobgether", "--out", _out(e, "jg.md")],
        "generate_jobgether",
        lambda e: server.generate_jobgether(out=_out(e, "jg.md")),
    ),
    Case(
        "job-board",
        lambda e: ["generate-job-board", "--out", _out(e, "jb.md")],
        "generate_job_board",
        lambda e: server.generate_job_board(out=_out(e, "jb.md")),
    ),
    Case(
        "pluralsight",
        lambda e: ["generate-pluralsight", "--out", _out(e, "ps.md")],
        "generate_pluralsight",
        lambda e: server.generate_pluralsight(out=_out(e, "ps.md")),
    ),
    # Gated documents: the resume and the cover letter.
    Case(
        "resume",
        lambda e: ["generate-resume", str(STRONG), "--out", _out(e, "resume.docx")],
        "generate_resume",
        lambda e: server.generate_resume(str(STRONG), out=_out(e, "resume.docx")),
    ),
    Case(
        "resume-refused-stretch",
        lambda e: ["generate-resume", _stretch(e), "--out", _out(e, "resume.docx")],
        "generate_resume",
        lambda e: server.generate_resume(_stretch(e), out=_out(e, "resume.docx")),
    ),
    Case(
        "resume-confirmed-past-stretch",
        lambda e: [
            "generate-resume",
            _stretch(e),
            "--out",
            _out(e, "resume.docx"),
            "--confirm-gaps",
        ],
        "generate_resume",
        lambda e: server.generate_resume(
            _stretch(e), out=_out(e, "resume.docx"), confirm_gaps=True
        ),
    ),
    Case(
        "resume-refused-skills-pass",
        lambda e: ["generate-resume", _skills_pass(e), "--out", _out(e, "resume.docx")],
        "generate_resume",
        lambda e: server.generate_resume(_skills_pass(e), out=_out(e, "resume.docx")),
    ),
    Case(
        "resume-refused-location",
        lambda e: ["generate-resume", str(QUEBEC), "--out", _out(e, "resume.docx")],
        "generate_resume",
        lambda e: server.generate_resume(str(QUEBEC), out=_out(e, "resume.docx")),
    ),
    Case(
        "resume-refused-already-applied",
        lambda e: ["generate-resume", str(STRONG), "--out", _out(e, "resume.docx")],
        "generate_resume",
        lambda e: server.generate_resume(str(STRONG), out=_out(e, "resume.docx")),
        _applied_today,
    ),
    Case(
        "cover-letter",
        lambda e: ["generate-cover-letter", str(STRONG), "--out", _out(e, "cover.docx")],
        "generate_cover_letter",
        lambda e: server.generate_cover_letter(str(STRONG), out=_out(e, "cover.docx")),
    ),
    Case(
        "cover-letter-refused-stretch",
        lambda e: ["generate-cover-letter", _stretch(e), "--out", _out(e, "cover.docx")],
        "generate_cover_letter",
        lambda e: server.generate_cover_letter(_stretch(e), out=_out(e, "cover.docx")),
    ),
    # One MCP call that makes both (the command line has no single command for it).
    Case(
        "application-documents",
        tool="generate_application_documents",
        mcp=lambda e: server.generate_application_documents(str(STRONG)),
    ),
    # Letters that are gated on location (and duplicates), not on skill fit.
    Case(
        "job-site-letter",
        lambda e: ["generate-job-site", str(STRONG), "--out", _out(e, "site.txt")],
        "generate_job_site_letter",
        lambda e: server.generate_job_site_letter(str(STRONG), out=_out(e, "site.txt")),
    ),
    Case(
        "job-site-letter-refused-location",
        lambda e: ["generate-job-site", str(QUEBEC), "--out", _out(e, "site.txt")],
        "generate_job_site_letter",
        lambda e: server.generate_job_site_letter(str(QUEBEC), out=_out(e, "site.txt")),
    ),
    Case(
        "cold-call-with-posting",
        lambda e: ["generate-cold-call", str(STRONG), "--out", _out(e, "cold.docx")],
        "generate_cold_call",
        lambda e: server.generate_cold_call(str(STRONG), out=_out(e, "cold.docx")),
    ),
    Case(
        "cold-call-without-posting",
        lambda e: [
            "generate-cold-call",
            "--recruiter-name",
            "Pat Lee",
            "--role-type",
            "Senior .NET Developer roles",
            "--out",
            _out(e, "cold.docx"),
        ],
        "generate_cold_call",
        lambda e: server.generate_cold_call(
            recruiter_name="Pat Lee",
            role_type="Senior .NET Developer roles",
            out=_out(e, "cold.docx"),
        ),
    ),
    Case(
        "cold-call-refused-location",
        lambda e: ["generate-cold-call", str(QUEBEC), "--out", _out(e, "cold.docx")],
        "generate_cold_call",
        lambda e: server.generate_cold_call(str(QUEBEC), out=_out(e, "cold.docx")),
    ),
    # Letters and prep that are not gated.
    Case(
        "thank-you",
        lambda e: [
            "generate-thank-you",
            str(STRONG),
            "--discussion-point",
            DISCUSSION,
            "--out",
            _out(e, "thanks.docx"),
        ],
        "generate_thank_you",
        lambda e: server.generate_thank_you(
            str(STRONG), discussion_points=[DISCUSSION], out=_out(e, "thanks.docx")
        ),
    ),
    Case(
        "thank-you-without-discussion-point",
        lambda e: ["generate-thank-you", str(STRONG), "--out", _out(e, "thanks.docx")],
        "generate_thank_you",
        lambda e: server.generate_thank_you(str(STRONG), out=_out(e, "thanks.docx")),
    ),
    Case(
        "interview-prep",
        lambda e: ["interview-prep", str(STRONG), "--out", _out(e, "prep.docx")],
        "interview_prep",
        lambda e: server.interview_prep(str(STRONG), out=_out(e, "prep.docx")),
    ),
    Case(
        "interview-prep-records-story-use",
        lambda e: [
            "interview-prep",
            str(STRONG),
            "--out",
            _out(e, "prep.docx"),
            "--update-star-bank",
        ],
        "interview_prep",
        lambda e: server.interview_prep(
            str(STRONG), out=_out(e, "prep.docx"), update_star_bank=True
        ),
    ),
    # The applications log.
    Case(
        "applications-check-new",
        lambda e: ["applications", "check", str(STRONG)],
        "applications_check",
        lambda e: server.applications_check(str(STRONG)),
    ),
    Case(
        "applications-check-drafted",
        lambda e: ["applications", "check", str(STRONG)],
        "applications_check",
        lambda e: server.applications_check(str(STRONG)),
        _drafted,
    ),
    Case(
        "applications-list-empty",
        lambda e: ["applications", "list"],
        "applications_list",
        lambda e: server.applications_list(),
    ),
    Case(
        "applications-list-by-status",
        lambda e: ["applications", "list", "--status", "phone_screen"],
        "applications_list",
        lambda e: server.applications_list(status="phone_screen"),
        _in_phone_screen,
    ),
    Case(
        "applications-mark-applied",
        lambda e: ["applications", "applied", "--jd", str(STRONG), "--date", "2026-01-05"],
        "applications_mark_applied",
        lambda e: server.applications_mark_applied(jd=str(STRONG), date="2026-01-05"),
    ),
    Case(
        "applications-set-status",
        lambda e: ["applications", "status", _draft_id(), "technical", "--note", "second round"],
        "applications_set_status",
        lambda e: server.applications_set_status(_draft_id(), "technical", note="second round"),
        _drafted,
    ),
    # Learning history and learning plans.
    Case(
        "learning-import-dry-run",
        lambda e: ["learning", "import", _import_file(e), "--provider", "pluralsight"],
        "learning_import",
        lambda e: server.learning_import(file=_import_file(e)),
    ),
    Case(
        "learning-plan",
        lambda e: ["generate-learning-plan", _role_config(e)],
        "generate_learning_plan",
        lambda e: server.generate_learning_plan(_role_config(e)),
    ),
    # Not an MCP tool, but the skills read what it prints.
    Case("application-dir", lambda e: ["application-dir", str(STRONG)]),
)

# MCP tools with no snapshot, and why. A tool must be here or in ``CASES``.
UNRECORDED_TOOLS = {
    "search_evidence": "needs the local Ollama service; tests/test_mcp_prompts.py runs it with a "
    "fake embedder",
}
