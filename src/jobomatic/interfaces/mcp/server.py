#!/usr/bin/env python3
"""The job-o-matic MCP server: the claude-jobs CLI as MCP tools, plus prompts, for Claude Desktop.

Each tool is a thin adapter: it builds the same argv list the CLI itself would build, calls
``jobomatic.interfaces.cli.main.main(argv)`` with stdout/stderr captured, and returns the captured text plus
(for document-producing tools) the generated artifact's content, read back off disk. No
generation logic and no gate logic lives here: the rules for when documents may be generated
(fit rating, location, duplicate application, pay) are in ``jobomatic.gate``, which the CLI runs
before it writes anything, so they hold for every caller. The tools only pass the user's
confirmations (``confirm_gaps``, ``confirm_reapply``, ``confirm_below_minimum``) through.
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import re
import tempfile
import threading
from collections.abc import Callable, Iterable
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Any, NamedTuple

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import (
    BlobResourceContents,
    ContentBlock,
    EmbeddedResource,
    Icon,
    TextContent,
    TextResourceContents,
)

from jobomatic import applications as applications_log
from jobomatic import paths, results
from jobomatic.commands import applications as applications_commands
from jobomatic.commands import cold_call as cold_call_command
from jobomatic.commands import constraints as constraints_command
from jobomatic.commands import cover_letter as cover_letter_command
from jobomatic.commands import fit_check as fit_check_command
from jobomatic.commands import gap_analysis as gap_analysis_command
from jobomatic.commands import interview_prep as interview_prep_command
from jobomatic.commands import job_site_letter as job_site_command
from jobomatic.commands import profile as profile_commands
from jobomatic.commands import resume as resume_command
from jobomatic.commands import search as search_command
from jobomatic.commands import thank_you as thank_you_command
from jobomatic.commands.support import Confirmations, vault_write_lock
from jobomatic.interfaces.cli.main import main as cli_main
from jobomatic.interfaces.mcp import access, skill_prompts
from jobomatic.presence import github, job_board, jobgether, linkedin, pluralsight

# Icons shown by MCP clients that display them. The server runs over stdio and hosts nothing, so
# each icon is sent as a data: URI. (file name, MIME type, sizes). The gauge icon is used rather
# than the full logo because the logo's lettering is unreadable at icon sizes.
_ICON_FILES = (
    ("job-o-matic-icon.svg", "image/svg+xml", ["any"]),
    ("icon-512.png", "image/png", ["512x512"]),
)


def server_icons() -> list[Icon]:
    """The server's icons, read from the branding folder. A missing file is skipped, since an
    icon is cosmetic and must never stop the server starting."""
    folder = resources.files("jobomatic") / "branding"
    icons: list[Icon] = []
    for name, mime_type, sizes in _ICON_FILES:
        try:
            data = (folder / name).read_bytes()
        except OSError:
            continue
        encoded = base64.b64encode(data).decode("ascii")
        icons.append(
            Icon(src=f"data:{mime_type};base64,{encoded}", mime_type=mime_type, sizes=sizes)
        )
    return icons


mcp = MCPServer("job-o-matic", title="Job-O-Matic Assistant", icons=server_icons())

# contextlib.redirect_stdout/stderr mutate process-global sys.stdout/sys.stderr
# for the duration of the `with` block — not thread-safe. The mcp SDK dispatches
# each tool call as its own task and runs sync tool functions (all of ours) via
# anyio.to_thread.run_sync, so two tool calls issued without waiting on each
# other genuinely execute on different threads. Without this lock, concurrent
# calls can corrupt each other's captured output. These are one-shot document
# generation calls, not a hot path, so serializing them costs nothing that matters.
_CLI_LOCK = threading.Lock()

# Every path an MCP client hands us is untrusted: a prompt-injected job posting can
# steer a tool call at any file the server process can reach. The rules live in
# src/jobomatic/interfaces/mcp/access.py (pure functions, tested on their own); this section only says where
# things are. Reads are limited to the vault, the system temp dir and extra directories;
# writes (and what gets attached back to the client) to the vault's outputs/, the
# learning-plans/ folder, the stories file, the temp dir and the extra directories. The
# code repository is not readable. Extra directories are allowed with
# CLAUDE_JOBS_ALLOWED_DIRS (os.pathsep-separated).


def _extra_roots() -> tuple[Path, ...]:
    raw = os.environ.get("CLAUDE_JOBS_ALLOWED_DIRS", "")
    return tuple(Path(p).expanduser().resolve() for p in raw.split(os.pathsep) if p.strip())


def _or_none(find: Callable[[], Path]) -> Path | None:
    """``find()``, or ``None`` when there is no vault to look in."""
    try:
        return find()
    except paths.VaultError:
        return None


def _locations() -> access.Locations:
    """Where things are right now (read per call: the vault and env can change in tests)."""
    code_root = paths.code_root()
    temp = Path(tempfile.gettempdir()).resolve()
    vault = _or_none(paths.vault_root)
    if vault is None:
        # No vault: only temp and the extra directories are open, but a private folder or
        # applications log set by environment variable must still be closed.
        return access.Locations(
            code_root=code_root,
            temp=temp,
            extra=_extra_roots(),
            private=_or_none(paths.private_dir),
            applications_log=_or_none(applications_log.log_path),
        )
    return access.Locations(
        code_root=code_root,
        temp=temp,
        extra=_extra_roots(),
        vault=vault,
        outputs=paths.outputs_dir(),
        learning_plans=paths.learning_plans_dir(),
        # interview_prep --update-star-bank writes back to this one file.
        stories_file=paths.profile_dir() / "stories.yaml",
        private=paths.private_dir(),
        applications_log=applications_log.log_path(),
    )


def _policy() -> access.Policy:
    return access.build_policy(_locations())


def _checked_path(value: str, *, write: bool, label: str) -> str:
    """Return ``value`` as a resolved path string, or raise ToolError if it is out of bounds."""
    policy = _policy()
    roots = policy.roots(write=write)
    resolved = access.resolve(value, roots, policy.denied)
    if resolved is None:
        allowed = ", ".join(str(r) for r in roots)
        raise ToolError(
            f"{label} {value!r} is outside the directories this server may "
            f"{'write to' if write else 'read from'} ({allowed}). "
            "Set CLAUDE_JOBS_ALLOWED_DIRS to allow another directory."
        )
    return str(resolved)


def _run_cli(argv: list[str]) -> str:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with _CLI_LOCK, vault_write_lock():
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = cli_main(argv)
        except SystemExit as exc:
            # argparse calls sys.exit() on bad arguments (e.g. --help, missing
            # required positional) instead of returning a code.
            exit_code = exc.code if isinstance(exc.code, int) else 1

    output = stdout.getvalue()
    errors = stderr.getvalue()
    combined = output + (f"\n{errors}" if errors else "")

    if exit_code != 0:
        raise ToolError(combined.strip() or f"'{' '.join(argv)}' failed (exit {exit_code})")
    return combined.strip()


_WROTE_RE = re.compile(r"^Wrote (.+)$", re.MULTILINE)
_TEXT_SUFFIXES = {".md", ".txt", ".json"}
_TEXT_MIME_TYPES = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".json": "application/json",
}
_MIME_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}


def _artifact_content_blocks(
    stdout_text: str, embed_text_as_resource: bool = False
) -> list[ContentBlock]:
    """Read back every artifact a CLI command just wrote (per its ``Wrote
    <path>`` stdout lines — the convention every generator script already
    follows) and return its content: a base64 ``EmbeddedResource`` for
    DOCX/PDF, and for markdown/text/JSON either inline text or (when
    ``embed_text_as_resource`` is set) a text ``EmbeddedResource`` too. This
    is what actually makes generated documents retrievable through the MCP
    interface, rather than leaving the client with a local filesystem path
    it can't read.

    ``embed_text_as_resource`` is for the profile-update tools
    (generate_linkedin, generate_github): their markdown draft is the whole
    deliverable, not a status message, so it comes back as an attachment in
    MCP clients like Claude Desktop the same way DOCX/PDF documents do,
    instead of dumping the full draft into the chat transcript as plain
    text. Other markdown-producing tools (e.g. gap_analysis) keep the
    inline-text behavior, since their content is meant to be read/discussed
    in the conversation itself.
    """
    return _attachment_blocks(
        (Path(match.group(1).strip()) for match in _WROTE_RE.finditer(stdout_text)),
        embed_text_as_resource=embed_text_as_resource,
    )


def _attachment_blocks(
    files: Iterable[Path], embed_text_as_resource: bool = False
) -> list[ContentBlock]:
    """The content of each file a command wrote, as blocks (see ``_artifact_content_blocks``)."""
    blocks: list[ContentBlock] = []
    for path in files:
        # Only attach files this server was allowed to write: whatever names a file (a printed
        # line that a posting can influence, or a command's own list) must not be a way to make
        # the server read back an arbitrary file.
        policy = _policy()
        if access.resolve(path, policy.write_roots, policy.denied) is None:
            continue
        if not path.is_file():
            # Defensive: e.g. `build`'s "Wrote X (v29)" trailer doesn't
            # resolve to a real path — skip rather than crash.
            continue
        suffix = path.suffix.lower()
        try:
            if suffix in _TEXT_SUFFIXES:
                text = path.read_text(encoding="utf-8")
                if embed_text_as_resource:
                    # .as_uri() requires an absolute path — resolve() first
                    # so a caller-supplied relative --out doesn't raise
                    # ValueError and crash the whole tool call.
                    uri = path.resolve().as_uri()
                    mime = _TEXT_MIME_TYPES.get(suffix, "text/plain")
                    blocks.append(
                        EmbeddedResource(
                            type="resource",
                            resource=TextResourceContents(uri=uri, mime_type=mime, text=text),
                        )
                    )
                else:
                    blocks.append(TextContent(type="text", text=f"### {path.name}\n\n{text}"))
            else:
                data = base64.b64encode(path.read_bytes()).decode()
                mime = _MIME_TYPES.get(suffix, "application/octet-stream")
                uri = path.resolve().as_uri()
                blocks.append(
                    EmbeddedResource(
                        type="resource",
                        resource=BlobResourceContents(uri=uri, mime_type=mime, blob=data),
                    )
                )
        except OSError as exc:
            # Don't let one unreadable artifact (permissions, race, odd
            # encoding) take down attachments that already succeeded.
            blocks.append(TextContent(type="text", text=f"[could not attach {path.name}: {exc}]"))
    return blocks


def _tool_blocks(
    result: results.CommandResult[Any],
    render: Callable[[Any], str] | None = None,
    *,
    embed_text_as_resource: bool = False,
) -> list[ContentBlock]:
    """A command's result as the blocks a document tool returns: its text, then each file it wrote
    (``result.written``), or a tool error when the command did not succeed."""
    blocks: list[ContentBlock] = [TextContent(type="text", text=_tool_text(result, render))]
    blocks.extend(_attachment_blocks(result.written, embed_text_as_resource=embed_text_as_resource))
    return blocks


def _run_cli_with_artifacts(
    argv: list[str], embed_text_as_resource: bool = False
) -> list[ContentBlock]:
    combined = _run_cli(argv)
    blocks: list[ContentBlock] = [TextContent(type="text", text=combined)]
    blocks.extend(_artifact_content_blocks(combined, embed_text_as_resource=embed_text_as_resource))
    return blocks


def _looks_like_path(jd: str) -> bool:
    """A JD arg is *shaped* like a path if it's a short, single-line string
    with no spaces — real job description text always has both. Anything
    else (pasted or attached JD text — the common case when a client hands
    over a job description in chat rather than writing it to disk first) is
    treated as the JD content itself."""
    return "\n" not in jd and " " not in jd and len(jd) < 400


class _Posting(NamedTuple):
    text: str
    source: Path | None  # the file it was read from, or None when it was pasted in


def _posting(jd: str) -> _Posting:
    """The posting a tool was given: the text itself, or a file this server may read.

    A path-shaped string must be a real file the server may read (a clear error otherwise, e.g. a
    typo); anything else is the job description text, as a client that pastes it in chat sends it.
    """
    if not _looks_like_path(jd):
        return _Posting(jd, None)
    path = Path(_checked_path(jd, write=False, label="job description path"))
    if not path.is_file():
        raise ToolError(f"job description file not found: {path}")
    try:
        return _Posting(path.read_text(encoding="utf-8"), path)
    except OSError as exc:
        raise ToolError(f"could not read the job description {path}: {exc}") from exc


def _posting_text(jd: str) -> str:
    return _posting(jd).text


def _checked_out(out: str | None) -> Path | None:
    """The ``out`` argument of a tool as a path this server may write to, or None."""
    return Path(_checked_path(out, write=True, label="out")) if out else None


def _tool_text(
    result: results.CommandResult[Any], render: Callable[[Any], str] | None = None
) -> str:
    """A command's result as the text a tool returns: what the command line prints, or a tool
    error when the command did not succeed."""
    text = results.console(result, render)
    combined = (text.stdout + (f"\n{text.stderr}" if text.stderr else "")).strip()
    if result.status != "ok":
        raise ToolError(combined or f"the command failed ({result.status})")
    return combined


@mcp.tool(description="Validate the candidate profile and run its consistency checks")
def validate_profile() -> str:
    return _tool_text(profile_commands.validate(), profile_commands.render_validate)


@mcp.tool(description="Inline fit check for a job description")
def fit_check(jd: str) -> str:
    """jd: path to a job description markdown file, or the job description
    text itself (e.g. pasted or attached in the chat)."""
    return _tool_text(fit_check_command.run(_posting_text(jd)), fit_check_command.render)


@mcp.tool(description="Generate a markdown gap analysis report", structured_output=False)
def gap_analysis(jd: str, out: str | None = None) -> list[ContentBlock]:
    """jd: path to a job description markdown file, or the job description
    text itself (e.g. pasted or attached in the chat). out: optional output
    markdown path."""
    return _tool_blocks(gap_analysis_command.run(_posting_text(jd), _checked_out(out)))


@mcp.tool(description="Generate LinkedIn profile copy", structured_output=False)
def generate_linkedin(out: str | None = None) -> list[ContentBlock]:
    """out: optional output markdown path."""
    return _tool_blocks(linkedin.run(_checked_out(out)), embed_text_as_resource=True)


@mcp.tool(
    description="Generate GitHub profile copy (bio, status, README, fields, pins)",
    structured_output=False,
)
def generate_github(out: str | None = None) -> list[ContentBlock]:
    """out: optional output markdown path."""
    return _tool_blocks(github.run(_checked_out(out)), embed_text_as_resource=True)


@mcp.tool(description="Generate Jobgether profile copy", structured_output=False)
def generate_jobgether(out: str | None = None) -> list[ContentBlock]:
    """out: optional output markdown path."""
    return _tool_blocks(jobgether.run(_checked_out(out)), embed_text_as_resource=True)


@mcp.tool(description="Generate Indeed & ZipRecruiter profile copy", structured_output=False)
def generate_job_board(out: str | None = None) -> list[ContentBlock]:
    """out: optional output markdown path."""
    return _tool_blocks(job_board.run(_checked_out(out)), embed_text_as_resource=True)


@mcp.tool(description="Generate Pluralsight profile copy", structured_output=False)
def generate_pluralsight(out: str | None = None) -> list[ContentBlock]:
    """out: optional output markdown path."""
    return _tool_blocks(pluralsight.run(_checked_out(out)), embed_text_as_resource=True)


def _supplied_text(value: str | None, label: str) -> str | None:
    """The text of an optional input file a tool was given a path to, or None if it was not given.

    The path must be one this server may read, and a file."""
    if not value:
        return None
    path = Path(_checked_path(value, write=False, label=label))
    if not path.is_file():
        raise ToolError(f"{label} not found: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ToolError(f"could not read {label} {path}: {exc}") from exc


def _document_tool(
    command: Callable[..., results.CommandResult[Any]],
    jd: str,
    company: str | None,
    out: str | None,
    *,
    confirm_gaps: bool = False,
    confirm_reapply: bool = False,
    confirm_below_minimum: bool = False,
) -> list[ContentBlock]:
    """Run a gated document command (its gates run inside it) and return its text and files."""
    posting = _posting(jd)
    result = command(
        posting.text,
        source=posting.source,
        company=company or None,
        out=_checked_out(out),
        confirm=Confirmations(confirm_gaps, confirm_reapply, confirm_below_minimum),
    )
    return _tool_blocks(result)


@mcp.tool(
    description="Generate a tailored resume DOCX (refuses if fit rating is below Good)",
    structured_output=False,
)
def generate_resume(
    jd: str,
    company: str | None = None,
    out: str | None = None,
    confirm_reapply: bool = False,
    confirm_below_minimum: bool = False,
    confirm_gaps: bool = False,
) -> list[ContentBlock]:
    """jd: path to a job description markdown file, or the job description
    text itself (e.g. pasted or attached in the chat). company: optional
    filename override. out: optional output DOCX path. Refuses to generate
    (raises a tool error) when the computed fit rating is below Good — call
    fit_check first to see the rating without generating a document. A Stretch
    or Worth a try rating can be confirmed past: list the gaps, ask the user, and
    only if they say yes call again with confirm_gaps=true. A Pass cannot.

    Also refuses (tool error) when the posting was already applied to within
    60 days (pass confirm_reapply=true only if the user explicitly says to
    proceed anyway), or when the posted pay is below the user's minimum (pass
    confirm_below_minimum=true only after the user says to continue).
    Generating only logs a *draft*; it never marks the posting as applied."""
    return _document_tool(
        resume_command.run,
        jd,
        company,
        out,
        confirm_reapply=confirm_reapply,
        confirm_gaps=confirm_gaps,
        confirm_below_minimum=confirm_below_minimum,
    )


@mcp.tool(
    description="Generate a tailored cover-letter DOCX (refuses if fit rating is below Good)",
    structured_output=False,
)
def generate_cover_letter(
    jd: str,
    company: str | None = None,
    out: str | None = None,
    confirm_reapply: bool = False,
    confirm_below_minimum: bool = False,
    confirm_gaps: bool = False,
) -> list[ContentBlock]:
    """jd: path to a job description markdown file, or the job description
    text itself (e.g. pasted or attached in the chat). company: optional
    filename override. out: optional output DOCX path. Refuses to generate
    (raises a tool error) when the computed fit rating is below Good — call
    fit_check first to see the rating without generating a document. A Stretch
    or Worth a try rating can be confirmed past: list the gaps, ask the user, and
    only if they say yes call again with confirm_gaps=true. A Pass cannot.

    Also refuses (tool error) when the posting was already applied to within
    60 days (pass confirm_reapply=true only if the user explicitly says to
    proceed anyway), or when the posted pay is below the user's minimum (pass
    confirm_below_minimum=true only after the user says to continue).
    Generating only logs a *draft*; it never marks the posting as applied."""
    return _document_tool(
        cover_letter_command.run,
        jd,
        company,
        out,
        confirm_reapply=confirm_reapply,
        confirm_gaps=confirm_gaps,
        confirm_below_minimum=confirm_below_minimum,
    )


@mcp.tool(
    description="Generate a tailored resume and cover letter for a job description in one "
    "call (refuses if fit rating is below Good)",
    structured_output=False,
)
def generate_application_documents(
    jd: str,
    company: str | None = None,
    confirm_reapply: bool = False,
    confirm_below_minimum: bool = False,
    confirm_gaps: bool = False,
) -> list[ContentBlock]:
    """jd: path to a job description markdown file, or the job description
    text itself (e.g. pasted or attached in the chat). company: optional
    filename override applied to both documents. Refuses to generate (raises
    a tool error) when the computed fit rating is below Good — call
    fit_check first to see the rating without generating documents. A Stretch or
    Worth a try rating can be confirmed past (confirm_gaps=true, only after the user
    says so); a Pass cannot. Both
    documents land in their normal default outputs/ location; use
    generate_resume / generate_cover_letter individually for a custom output
    path. The duplicate-application and below-minimum-pay checks (and their
    confirm_reapply / confirm_below_minimum overrides) work as on generate_resume."""
    blocks: list[ContentBlock] = []
    for command in (resume_command.run, cover_letter_command.run):
        blocks.extend(
            _document_tool(
                command,
                jd,
                company,
                None,
                confirm_reapply=confirm_reapply,
                confirm_gaps=confirm_gaps,
                confirm_below_minimum=confirm_below_minimum,
            )
        )
    return blocks


@mcp.tool(description="Generate a short cold-call cover-letter DOCX", structured_output=False)
def generate_cold_call(
    jd: str | None = None,
    company: str | None = None,
    recruiter_name: str | None = None,
    role_type: str | None = None,
    out: str | None = None,
) -> list[ContentBlock]:
    """jd: optional path to a target company description or JD markdown file,
    or that text itself (e.g. pasted or attached in the chat) — cold
    outreach is usually conversational, with no JD in hand; prefer
    recruiter_name/role_type instead. company: optional filename/salutation
    override. recruiter_name: salutation name, e.g. "Jane Doe" (default
    "Hiring Team"). role_type: target role type, e.g. "Senior .NET Developer
    roles". out: optional output DOCX path."""

    posting = _posting(jd) if jd else None
    return _tool_blocks(
        cold_call_command.run(
            posting.text if posting else None,
            source=posting.source if posting else None,
            company=company or None,
            recruiter_name=recruiter_name or None,
            role_type=role_type or None,
            out=_checked_out(out),
        )
    )


@mcp.tool(
    description="Generate a short job-site cover letter (default: .txt)",
    structured_output=False,
)
def generate_job_site_letter(
    jd: str, company: str | None = None, out: str | None = None, confirm_reapply: bool = False
) -> list[ContentBlock]:
    """jd: path to a job description markdown file, or the job description
    text itself (e.g. pasted or attached in the chat). company: optional
    filename override. out: optional output path (.txt default, .docx for
    DOCX)."""
    return _document_tool(job_site_command.run, jd, company, out, confirm_reapply=confirm_reapply)


@mcp.tool(description="Generate a post-interview thank-you letter DOCX", structured_output=False)
def generate_thank_you(
    jd: str | None = None,
    company: str | None = None,
    role: str | None = None,
    interviewers: list[str] | None = None,
    date: str | None = None,
    discussion_points: list[str] | None = None,
    out: str | None = None,
) -> list[ContentBlock]:
    """jd: optional path to a job description markdown file, or that text
    itself (e.g. pasted or attached in the chat), for company/role/
    skills-fit context — never a substitute for discussion_points. company:
    optional filename/salutation override. role: role interviewed for.
    interviewers: interviewer name(s) — drives the salutation. date: interview
    date. discussion_points: specific details from the actual interview
    (required — at least one; generation refuses without it). out: optional
    output DOCX path."""

    posting = _posting(jd) if jd else None
    return _tool_blocks(
        thank_you_command.run(
            posting.text if posting else None,
            source=posting.source if posting else None,
            company=company or None,
            role=role or None,
            interviewers=interviewers or None,
            date=date or None,
            discussion_points=discussion_points or None,
            out=_checked_out(out),
        )
    )


@mcp.tool(description="Generate an interview prep DOCX for a JD", structured_output=False)
def interview_prep(
    jd: str,
    stage: str | None = None,
    out: str | None = None,
    update_star_bank: bool = False,
    company_research_path: str | None = None,
    recruiter_briefing_path: str | None = None,
    qa_cards_path: str | None = None,
    salary_section_path: str | None = None,
) -> list[ContentBlock]:
    """jd: path to a job description markdown file, or the job description
    text itself (e.g. pasted or attached in the chat).
    stage: optional interview stage (phone_screen, technical_screen, final_round;
    default: technical_screen) — gates document scope. out: optional output DOCX path.
    update_star_bank: when true, writes updated last_used/used_for metadata back
    to the profile's stories.yaml for every STAR story selected in this run.
    company_research_path: optional path to a text file of
    company-research prose (e.g. web_search findings — never fabricated).
    recruiter_briefing_path: optional path to a text file with a pasted
    recruiter briefing. qa_cards_path: optional path to a JSON file of
    LLM-authored Q&A cards (list of {"question", "answer", optional
    "tip"/"category"}) — merged in after the script's own grounded-evidence
    cards. salary_section_path: optional path to a text file of
    salary/negotiation prose; only rendered when stage is final_round,
    otherwise a warning is printed and it's omitted."""
    posting = _posting(jd)
    return _tool_blocks(
        interview_prep_command.run(
            posting.text,
            source=posting.source,
            out=_checked_out(out),
            stage=stage or "technical_screen",
            update_star_bank=update_star_bank,
            company_research=_supplied_text(company_research_path, "company_research_path"),
            recruiter_briefing=_supplied_text(recruiter_briefing_path, "recruiter_briefing_path"),
            qa_cards_json=_supplied_text(qa_cards_path, "qa_cards_path"),
            salary_section=_supplied_text(salary_section_path, "salary_section_path"),
        )
    )


@mcp.tool(description="Check whether a job description was already applied to (duplicate check)")
def applications_check(jd: str) -> str:
    """jd: path to a job description markdown file, or the job description text itself.
    Reports NEW / DRAFTED / RELATED / REPEAT / DUPLICATE against the applications log."""
    return _tool_text(
        applications_commands.check(_posting_text(jd)), applications_commands.render_check
    )


@mcp.tool(description="List applications in the log, optionally filtered by status or company")
def applications_list(status: str | None = None, company: str | None = None) -> str:
    """status: one of drafted, applied, phone_screen, technical, offer, rejected, withdrawn."""
    return _tool_text(
        applications_commands.list_applications(status=status or None, company=company or None),
        applications_commands.render_list,
    )


@mcp.tool(
    description="Record that the USER SUBMITTED an application. Call only when the user has "
    "explicitly said they applied — never because documents were generated."
)
def applications_mark_applied(
    application_id: str | None = None, jd: str | None = None, date: str | None = None
) -> str:
    """Give application_id (from applications_list) or jd (path or pasted text of the
    posting; the entry is created if it was never drafted). date: YYYY-MM-DD, default today."""
    if bool(application_id) == bool(jd):
        raise ToolError("provide exactly one of application_id or jd")
    return _tool_text(
        applications_commands.applied(
            application_id=application_id or None,
            jd_text=_posting_text(jd) if jd else None,
            date=date or None,
        ),
        applications_commands.render_applied,
    )


@mcp.tool(description="Move an application to a new status (e.g. phone_screen, offer, rejected)")
def applications_set_status(
    application_id: str, status: str, next_step: str | None = None, note: str | None = None
) -> str:
    return _tool_text(
        applications_commands.set_status(
            application_id, status, next_step=next_step or None, note=note or None
        ),
        applications_commands.render_status,
    )


# -- Pluralsight history import ---------------------------------------------------------------
#
# Access review (ADR 0020 asked for one before any importer tool). The only client-controlled
# inputs are ``file`` (read-checked like every other path, and limited to .html/.htm/.json so the
# tool cannot be used to read arbitrary vault files) and ``content`` (text held in a throwaway
# temp folder for the call). What the import writes is fixed by the CLI, not by the client: the
# vault's ``profile/learning/items.yaml`` and a copy of the export under ``imports/pluralsight/``.
# It never takes a Microsoft Learn transcript or the network (the CLI's ``--mslearn``), and a
# tool result carries only course titles, dates and counts.

_IMPORT_SUFFIXES = (".html", ".htm", ".json")
_MAX_IMPORT_CONTENT_BYTES = 2 * 1024 * 1024  # the import file for a full history is ~100 KB


@contextlib.contextmanager
def _import_file(file: str | None, content: str | dict[str, Any] | list[Any] | None):
    """Yield the path of the Pluralsight export to import, from ``file`` or from ``content``.

    The MCP framework parses a string argument that looks like JSON into an object before the
    tool sees it, so an import file passed as ``content`` arrives as a dict; it is turned back
    into text here.
    """
    if isinstance(content, dict | list):
        content = json.dumps(content)
    if bool(file) == bool(content):
        raise ToolError("provide exactly one of file or content")
    if file:
        path = _checked_path(file, write=False, label="import file path")
        if Path(path).suffix.lower() not in _IMPORT_SUFFIXES:
            raise ToolError(f"import file must be {', '.join(_IMPORT_SUFFIXES)}, not {path!r}")
        if not Path(path).is_file():
            raise ToolError(f"import file not found: {path}")
        yield path
        return
    assert content is not None
    if len(content.encode("utf-8")) > _MAX_IMPORT_CONTENT_BYTES:
        raise ToolError(
            "content is too large to pass through a tool call; save it as a file in the vault "
            "(or a directory in CLAUDE_JOBS_ALLOWED_DIRS) and pass file instead"
        )
    suffix = ".json" if content.lstrip()[:1] in ("{", "[") else ".html"
    with tempfile.TemporaryDirectory(prefix="pluralsight-import-") as scratch:
        # A stable, dated name: it is recorded as each new item's ``source``.
        export = Path(scratch) / f"pluralsight_import_{date.today().isoformat()}{suffix}"
        export.write_text(content, encoding="utf-8")
        yield str(export)


@mcp.tool(
    description=(
        "Import newly completed Pluralsight courses and labs into the user's learning history. "
        "Give file (a path to the import .json from the browser import page, or a saved "
        "Pluralsight history .html) or content (the text of a small import file, e.g. the "
        "'new entries only' download). apply defaults to False: that is a DRY RUN that saves "
        "nothing and shows what is new, changed or re-keyed. Show the user that result and set "
        "apply=True only after they say yes."
    )
)
def learning_import(
    file: str | None = None,
    content: str | dict[str, Any] | list[Any] | None = None,
    apply: bool = False,
) -> str:
    """Pluralsight only (Microsoft Learn imports are CLI only). Items are matched by course
    link, never title; a stored completion date, topics and summary are never overwritten.
    Summaries and the evidence index are separate steps (CLI: learning summarize, index build)."""
    with _import_file(file, content) as path:
        argv = ["learning", "import", path, "--provider", "pluralsight"]
        if apply:
            argv.append("--apply")
        result = _run_cli(argv)
    if apply and "Saved " in result:
        result += (
            "\n\nNext (CLI): `learning summarize --missing` for summaries of the new items, "
            "then `index build` to refresh the evidence index."
        )
    return result


@mcp.tool(description="Show the user's private salary minimums (or say they are not configured)")
def search_constraints() -> str:
    return _tool_text(constraints_command.show(), constraints_command.render)


# Evidence from private prose (resume bullets, interview stories) never leaves this machine
# (ADR 0019). A tool result goes to the model Claude Desktop talks to, so those kinds are left out.
_CLOUD_SAFE_KINDS = ("course", "lab", "module", "learning_path", "project")


@mcp.tool(
    description=(
        "Find the closest evidence in the user's courses, labs, Microsoft Learn items and projects "
        "for a skill or requirement (advisory; similarity is not proof of experience). Resume "
        "bullets and interview stories are not searched. Needs the local Ollama service."
    )
)
def search_evidence(query: str, k: int = 3) -> str:
    if not query.strip():
        raise ToolError("query must not be empty")
    return _tool_text(
        search_command.search(
            query.strip(),
            k=max(1, min(int(k), 10)),
            kinds=frozenset(_CLOUD_SAFE_KINDS),
        ),
        search_command.render,
    )


@mcp.tool(
    description=(
        "The public-facing profile: headline, summary, certifications and skills, with no contact "
        "details and nothing marked private."
    )
)
def profile_summary() -> str:
    return _tool_text(profile_commands.show("facts", public=True), profile_commands.render_show)


@mcp.tool(
    description="Render a role-specific Learning Plan PDF from a JSON config",
    structured_output=False,
)
def generate_learning_plan(role_json: str) -> list[ContentBlock]:
    """role_json: path to a role config JSON — see
    templates/roles/_example.json for the schema. The
    config must already exist (authored by the cert-learning-plan /
    learning-plan-gap-analysis skill); this only renders it to PDF. The
    config's own "output" path is resolved relative to this server's working
    directory — prefer an absolute path there, or one relative to the repo
    root, and must fall inside the directories this server may write to."""
    config_path = _checked_path(role_json, write=False, label="role_json")
    # The PDF is written wherever the config's own "output" key says, so it needs
    # the same write check as an `out` argument. Unreadable or invalid configs are
    # left for the CLI to report; it fails before writing anything.
    try:
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = None
    if isinstance(cfg, dict) and cfg.get("output") is not None:
        _checked_path(str(cfg["output"]), write=True, label="role_json output")
    return _run_cli_with_artifacts(["generate-learning-plan", config_path])


# The application-workflow skills, as prompts Claude Desktop can offer (see skill_prompts.py).
skill_prompts.register(mcp)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
