#!/usr/bin/env python3
"""``jobo``: the command line entry point and dispatcher."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import cast

from jobomatic import paths
from jobomatic.interfaces.cli import (
    applications_cli,
    learning_cli,
    profile_cli,
    render_cli,
    retrieval_cli,
)
from jobomatic.results import emit


def _root() -> Path:
    return paths.code_root()


def _generate_learning_plan(role_json: Path) -> int:
    from jobomatic.commands import learning_plan

    return emit(learning_plan.run(role_json))


def _fit_check(jd_path: Path) -> int:
    from jobomatic.commands.fit_check import (
        main as fit_check_main,
    )

    return cast(int, fit_check_main([str(jd_path)]))


def _gap_analysis(jd_path: Path, out_path: Path | None) -> int:
    from jobomatic.commands.gap_analysis import (
        main as gap_main,
    )

    args = [str(jd_path)]
    if out_path is not None:
        args.extend(["--out", str(out_path)])
    return cast(int, gap_main(args))


def _generate_linkedin(out_path: Path | None) -> int:
    from jobomatic.presence.linkedin import (
        main as linkedin_main,
    )

    args: list[str] = []
    if out_path is not None:
        args.extend(["--out", str(out_path)])
    return cast(int, linkedin_main(args))


def _generate_github(out_path: Path | None) -> int:
    from jobomatic.presence.github import (
        main as github_main,
    )

    args: list[str] = []
    if out_path is not None:
        args.extend(["--out", str(out_path)])
    return cast(int, github_main(args))


def _generate_jobgether(out_path: Path | None) -> int:
    from jobomatic.presence.jobgether import (
        main as jobgether_main,
    )

    args: list[str] = []
    if out_path is not None:
        args.extend(["--out", str(out_path)])
    return cast(int, jobgether_main(args))


def _generate_job_board(out_path: Path | None) -> int:
    from jobomatic.presence.job_board import (
        main as job_board_main,
    )

    args: list[str] = []
    if out_path is not None:
        args.extend(["--out", str(out_path)])
    return cast(int, job_board_main(args))


def _generate_pluralsight(out_path: Path | None) -> int:
    from jobomatic.presence.pluralsight import (
        main as pluralsight_main,
    )

    args: list[str] = []
    if out_path is not None:
        args.extend(["--out", str(out_path)])
    return cast(int, pluralsight_main(args))


# Map CLI subcommand → underlying script module's full dotted path. These
# three take the same (jd, optional --company, optional --out) arguments, so
# they share a dispatcher. generate-cold-call and generate-thank-you are the
# exceptions — both have optional jd plus extra per-application flags (see
# _generate_cold_call / _generate_thank_you below), so each is dispatched
# separately.
_LETTER_GENERATORS = {
    "generate-resume": "jobomatic.commands.resume",
    "generate-cover-letter": "jobomatic.commands.cover_letter",
    "generate-job-site": "jobomatic.commands.job_site_letter",
}


def _generate_platform_document(kind: str, out_path: Path | None, check_pages: bool = False) -> int:
    """The resume or cover-letter template for uploading to job boards: no posting, no log."""
    from jobomatic import bootstrap
    from jobomatic.commands.support import print_wrote
    from jobomatic.documents.service import DocumentError
    from jobomatic.profile.service import ProfileError

    try:
        profile = bootstrap.load_profile()
    except ProfileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if kind == "resume":
        from jobomatic.commands.resume import (
            generate_profile_resume as generate,
        )
    else:
        from jobomatic.commands.cover_letter import (
            generate_profile_cover_letter as generate,
        )
    try:
        print_wrote(*generate(profile=profile, out_path=out_path, check_pages=check_pages))
    except DocumentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


def _application_dir(jd_path: Path) -> int:
    """Print where this posting's documents go, for skills that write a file by hand."""
    from jobomatic.applications import outputs

    try:
        text = jd_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(outputs.locate_application(text, log=False).folder)
    return 0


def _generate_letter(
    command: str,
    jd_path: Path,
    company: str | None,
    out_path: Path | None,
    confirmations: dict[str, bool] | None = None,
    check_pages: bool = False,
) -> int:
    # Import the script module under its full name. Using a runtime
    # ``importlib.import_module`` here is intentional: the scripts are
    # discovered from the static ``_LETTER_GENERATORS`` mapping below, and
    # failing closed (loud ``ImportError``) when a new generator is added
    # but not listed is the right behavior.
    module = importlib.import_module(_LETTER_GENERATORS[command])
    args: list[str] = [str(jd_path)]
    if company:
        args.extend(["--company", company])
    if out_path is not None:
        args.extend(["--out", str(out_path)])
    if check_pages:
        args.append("--check-pages")
    # The gate runs inside the command (ADR 0028); the user's confirmations are passed through.
    for name, given in (confirmations or {}).items():
        if given:
            args.append("--" + name.replace("_", "-"))
    return cast(int, module.main(args))


def _generate_cold_call(
    jd_path: Path | None,
    company: str | None,
    recruiter_name: str | None,
    role_type: str | None,
    out_path: Path | None,
) -> int:
    from jobomatic.commands.cold_call import (
        main as cold_call_main,
    )

    args: list[str] = [str(jd_path)] if jd_path is not None else []
    if company:
        args.extend(["--company", company])
    if recruiter_name:
        args.extend(["--recruiter-name", recruiter_name])
    if role_type:
        args.extend(["--role-type", role_type])
    if out_path is not None:
        args.extend(["--out", str(out_path)])
    return cast(int, cold_call_main(args))


def _generate_thank_you(
    jd_path: Path | None,
    company: str | None,
    role: str | None,
    interviewers: list[str] | None,
    date: str | None,
    discussion_points: list[str] | None,
    out_path: Path | None,
) -> int:
    from jobomatic.commands.thank_you import (
        main as thank_you_main,
    )

    args: list[str] = [str(jd_path)] if jd_path is not None else []
    if company:
        args.extend(["--company", company])
    if role:
        args.extend(["--role", role])
    for interviewer in interviewers or []:
        args.extend(["--interviewer", interviewer])
    if date:
        args.extend(["--date", date])
    for point in discussion_points or []:
        args.extend(["--discussion-point", point])
    if out_path is not None:
        args.extend(["--out", str(out_path)])
    return cast(int, thank_you_main(args))


def _interview_prep(
    jd_path: Path,
    out_path: Path | None,
    stage: str | None,
    update_star_bank: bool = False,
    company_research_path: Path | None = None,
    recruiter_briefing_path: Path | None = None,
    qa_cards_path: Path | None = None,
    salary_section_path: Path | None = None,
) -> int:
    from jobomatic.commands.interview_prep import (
        main as interview_main,
    )

    args = [str(jd_path)]
    if stage:
        args.extend(["--stage", stage])
    if out_path is not None:
        args.extend(["--out", str(out_path)])
    if update_star_bank:
        args.append("--update-star-bank")
    if company_research_path is not None:
        args.extend(["--company-research", str(company_research_path)])
    if recruiter_briefing_path is not None:
        args.extend(["--recruiter-briefing", str(recruiter_briefing_path)])
    if qa_cards_path is not None:
        args.extend(["--qa-cards", str(qa_cards_path)])
    if salary_section_path is not None:
        args.extend(["--salary-section", str(salary_section_path)])
    return cast(int, interview_main(args))


def main(argv: list[str] | None = None) -> int:
    """Run ``jobo``. A missing or invalid vault is the first thing a new install hits, so it is a
    one-line error with the way out, not a traceback."""
    from jobomatic.paths import VaultError

    try:
        return _run(argv)
    except VaultError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobo", description="Job-search tooling")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fit_parser = subparsers.add_parser("fit-check", help="Inline fit check for a job description")
    fit_parser.add_argument("jd", type=Path, help="Path to job description markdown file")

    gap_parser = subparsers.add_parser(
        "gap-analysis", help="Generate a markdown gap analysis report"
    )
    gap_parser.add_argument("jd", type=Path, help="Path to job description markdown file")
    gap_parser.add_argument("--out", type=Path, help="Output markdown file path")

    linkedin_parser = subparsers.add_parser(
        "generate-linkedin", help="Generate LinkedIn profile copy"
    )
    linkedin_parser.add_argument("--out", type=Path, help="Output markdown file path")

    github_parser = subparsers.add_parser(
        "generate-github", help="Generate GitHub profile README copy"
    )
    github_parser.add_argument("--out", type=Path, help="Output markdown file path")

    jobgether_parser = subparsers.add_parser(
        "generate-jobgether", help="Generate Jobgether profile copy"
    )
    jobgether_parser.add_argument("--out", type=Path, help="Output markdown file path")

    job_board_parser = subparsers.add_parser(
        "generate-job-board", help="Generate Indeed & ZipRecruiter profile copy"
    )
    job_board_parser.add_argument("--out", type=Path, help="Output markdown file path")

    pluralsight_parser = subparsers.add_parser(
        "generate-pluralsight", help="Generate Pluralsight profile copy"
    )
    pluralsight_parser.add_argument("--out", type=Path, help="Output markdown file path")

    resume_parser = subparsers.add_parser("generate-resume", help="Generate a tailored resume DOCX")
    resume_parser.add_argument("jd", type=Path, help="Path to job description markdown file")
    resume_parser.add_argument("--company", help="Override company name used in filename")
    resume_parser.add_argument("--out", type=Path, help="Output DOCX path")
    resume_parser.add_argument(
        "--confirm-gaps",
        action="store_true",
        help="Generate despite a Stretch or Worth a try rating (only after the user says so)",
    )
    resume_parser.add_argument(
        "--confirm-reapply",
        action="store_true",
        help="Generate despite an application to this posting inside the duplicate window",
    )
    resume_parser.add_argument(
        "--confirm-below-minimum",
        action="store_true",
        help="Generate despite stated pay below the minimum (only after the user says so)",
    )

    resume_parser.add_argument(
        "--check-pages",
        action="store_true",
        help="Count the real pages with LibreOffice and fail if over 2 (slow; needs LibreOffice)",
    )

    cover_parser = subparsers.add_parser(
        "generate-cover-letter", help="Generate a tailored cover-letter DOCX"
    )
    cover_parser.add_argument("jd", type=Path, help="Path to job description markdown file")
    cover_parser.add_argument("--company", help="Override company name used in filename")
    cover_parser.add_argument("--out", type=Path, help="Output DOCX path")
    cover_parser.add_argument(
        "--check-pages",
        action="store_true",
        help="Count the real pages with LibreOffice and fail unless it is 1 (slow; needs LibreOffice)",
    )
    cover_parser.add_argument(
        "--confirm-gaps",
        action="store_true",
        help="Generate despite a Stretch or Worth a try rating (only after the user says so)",
    )
    cover_parser.add_argument(
        "--confirm-reapply",
        action="store_true",
        help="Generate despite an application to this posting inside the duplicate window",
    )
    cover_parser.add_argument(
        "--confirm-below-minimum",
        action="store_true",
        help="Generate despite stated pay below the minimum (only after the user says so)",
    )

    cold_parser = subparsers.add_parser(
        "generate-cold-call", help="Generate a short cold-call cover-letter DOCX"
    )
    cold_parser.add_argument(
        "jd",
        type=Path,
        nargs="?",
        default=None,
        help="Optional path to a target company description or JD markdown file. "
        "Cold outreach is usually conversational — omit this and use "
        "--recruiter-name/--role-type instead.",
    )
    cold_parser.add_argument("--company", help="Override company name used in filename")
    cold_parser.add_argument(
        "--recruiter-name", help='Salutation name, e.g. "Jane Doe" (default: "Hiring Team")'
    )
    cold_parser.add_argument(
        "--role-type", help='Target role type, e.g. "Senior .NET Developer roles"'
    )
    cold_parser.add_argument("--out", type=Path, help="Output DOCX path")

    job_site_parser = subparsers.add_parser(
        "generate-job-site", help="Generate a short job-site cover letter (default: .txt)"
    )
    job_site_parser.add_argument("jd", type=Path, help="Path to job description markdown file")
    job_site_parser.add_argument("--company", help="Override company name used in filename")
    job_site_parser.add_argument(
        "--out", type=Path, help="Output path (default .txt; use .docx for DOCX)"
    )
    job_site_parser.add_argument(
        "--confirm-reapply",
        action="store_true",
        help="Generate despite an application to this posting inside the duplicate window",
    )

    thank_you_parser = subparsers.add_parser(
        "generate-thank-you", help="Generate a post-interview thank-you letter DOCX"
    )
    thank_you_parser.add_argument(
        "jd",
        type=Path,
        nargs="?",
        default=None,
        help="Optional path to a job description markdown file, for company/role/"
        "skills-fit context. Never a substitute for --discussion-point.",
    )
    thank_you_parser.add_argument(
        "--company", help="Override company name used in filename and salutation"
    )
    thank_you_parser.add_argument(
        "--role", help='Role interviewed for, e.g. "Senior .NET Developer"'
    )
    thank_you_parser.add_argument(
        "--interviewer",
        action="append",
        dest="interviewers",
        help="Interviewer name (repeatable)",
    )
    thank_you_parser.add_argument("--date", help="Interview date")
    thank_you_parser.add_argument(
        "--discussion-point",
        action="append",
        dest="discussion_points",
        help="A specific detail from the actual interview (repeatable, required — "
        "1-2 points). Generation refuses without at least one.",
    )
    thank_you_parser.add_argument("--out", type=Path, help="Output DOCX path")

    interview_parser = subparsers.add_parser(
        "interview-prep", help="Generate an interview prep DOCX for a JD"
    )
    interview_parser.add_argument("jd", type=Path, help="Path to job description markdown file")
    interview_parser.add_argument(
        "--stage",
        choices=["phone_screen", "technical_screen", "final_round"],
        help="Interview stage — gates document scope (default: technical_screen)",
    )
    interview_parser.add_argument("--out", type=Path, help="Output DOCX file path")
    interview_parser.add_argument(
        "--update-star-bank",
        action="store_true",
        help="Write updated last_used/used_for metadata back to the vault's stories.yaml "
        "for every STAR story selected in this run",
    )
    interview_parser.add_argument(
        "--company-research",
        type=Path,
        help="Path to a text file of company-research prose (e.g. web_search findings)",
    )
    interview_parser.add_argument(
        "--recruiter-briefing",
        type=Path,
        help="Path to a text file with a pasted recruiter briefing",
    )
    interview_parser.add_argument(
        "--qa-cards",
        type=Path,
        help="Path to a JSON file of LLM-authored Q&A cards",
    )
    interview_parser.add_argument(
        "--salary-section",
        type=Path,
        help="Path to a text file of salary/negotiation prose (final_round stage only)",
    )

    learning_plan_parser = subparsers.add_parser(
        "generate-learning-plan", help="Render a role-specific Learning Plan PDF from a JSON config"
    )
    learning_plan_parser.add_argument(
        "role_json",
        type=Path,
        help="Path to a role config JSON (see templates/roles/_example.json)",
    )

    for name, what in (
        ("generate-profile-resume", "the platform-ready resume (no job description)"),
        ("generate-profile-cover-letter", "the reusable cover-letter template"),
    ):
        platform_parser = subparsers.add_parser(name, help=f"Generate {what}")
        platform_parser.add_argument(
            "--out", type=Path, help="Output DOCX path (default: templates/ in the vault)"
        )
        platform_parser.add_argument(
            "--check-pages",
            action="store_true",
            help="Count the real pages with LibreOffice and fail if over the limit "
            "(slow; needs LibreOffice)",
        )

    dir_parser = subparsers.add_parser(
        "application-dir",
        help="Print the folder holding this posting's documents (created if missing; never logged)",
    )
    dir_parser.add_argument("jd", type=Path, help="Path to job description markdown file")

    applications_cli.register(subparsers)
    profile_cli.register(subparsers)
    learning_cli.register(subparsers)
    render_cli.register(subparsers)
    retrieval_cli.register(subparsers)

    args = parser.parse_args(argv)

    if args.command in applications_cli.COMMANDS:
        return applications_cli.run(args)
    if args.command == "generate-profile-resume":
        return _generate_platform_document("resume", args.out, args.check_pages)
    if args.command == "generate-profile-cover-letter":
        return _generate_platform_document("cover_letter", args.out, args.check_pages)
    if args.command == "application-dir":
        return _application_dir(args.jd)
    if args.command == render_cli.COMMAND:
        return render_cli.run(args)
    if args.command == learning_cli.COMMAND:
        return learning_cli.run(args)
    if args.command == profile_cli.COMMAND:
        return profile_cli.run(args)
    if args.command in retrieval_cli.COMMANDS:
        return retrieval_cli.run(args)
    if args.command == "fit-check":
        return _fit_check(args.jd)
    if args.command == "gap-analysis":
        return _gap_analysis(args.jd, getattr(args, "out", None))
    if args.command == "generate-linkedin":
        return _generate_linkedin(getattr(args, "out", None))
    if args.command == "generate-github":
        return _generate_github(getattr(args, "out", None))
    if args.command == "generate-jobgether":
        return _generate_jobgether(getattr(args, "out", None))
    if args.command == "generate-job-board":
        return _generate_job_board(getattr(args, "out", None))
    if args.command == "generate-pluralsight":
        return _generate_pluralsight(getattr(args, "out", None))
    if args.command in _LETTER_GENERATORS:
        return _generate_letter(
            args.command,
            args.jd,
            getattr(args, "company", None),
            getattr(args, "out", None),
            {
                "confirm_gaps": getattr(args, "confirm_gaps", False),
                "confirm_reapply": getattr(args, "confirm_reapply", False),
                "confirm_below_minimum": getattr(args, "confirm_below_minimum", False),
            },
            getattr(args, "check_pages", False),
        )
    if args.command == "generate-cold-call":
        return _generate_cold_call(
            args.jd,
            getattr(args, "company", None),
            getattr(args, "recruiter_name", None),
            getattr(args, "role_type", None),
            getattr(args, "out", None),
        )
    if args.command == "generate-thank-you":
        return _generate_thank_you(
            args.jd,
            getattr(args, "company", None),
            getattr(args, "role", None),
            getattr(args, "interviewers", None),
            getattr(args, "date", None),
            getattr(args, "discussion_points", None),
            getattr(args, "out", None),
        )
    if args.command == "interview-prep":
        return _interview_prep(
            args.jd,
            getattr(args, "out", None),
            getattr(args, "stage", None),
            getattr(args, "update_star_bank", False),
            getattr(args, "company_research", None),
            getattr(args, "recruiter_briefing", None),
            getattr(args, "qa_cards", None),
            getattr(args, "salary_section", None),
        )
    if args.command == "generate-learning-plan":
        return _generate_learning_plan(args.role_json)
    parser.error("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
