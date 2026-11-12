"""Smoke tests for the ``jobo`` commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
FIXTURE_JD = FIXTURES_DIR / "sample-jd.md"


from jobomatic import paths
from jobomatic.commands import cold_call as generate_cold_call_letter_module
from jobomatic.commands import cover_letter as generate_cover_letter_module
from jobomatic.commands import fit_check as fit_check_module
from jobomatic.commands import gap_analysis as gap_analysis_module
from jobomatic.commands import interview_prep as interview_prep_module
from jobomatic.commands import job_site_letter as generate_job_site_letter_module
from jobomatic.commands import resume as generate_resume_module
from jobomatic.commands import thank_you as generate_thank_you_letter_module
from jobomatic.commands.fit_check import (
    main as fit_check_main,
)
from jobomatic.commands.gap_analysis import (
    main as gap_analysis_main,
)
from jobomatic.interfaces.cli.main import main as cli_main
from jobomatic.presence.github import (
    main as github_main,
)
from jobomatic.presence.job_board import (
    main as job_board_main,
)
from jobomatic.presence.jobgether import (
    main as jobgether_main,
)
from jobomatic.presence.linkedin import (
    main as linkedin_main,
)
from jobomatic.presence.pluralsight import (
    main as pluralsight_main,
)

# Every script here calls load_profile_or_none() somewhere
# in main() — a missing/unbuilt outputs/the profile (e.g. a fresh
# checkout before "generate profiles" has ever run) used to crash all of them
# except gap_analysis.py with an uncaught FileNotFoundError, instead of the
# clean "ERROR: ..." + exit 1 every other failure path already used. Fixed
# via jobomatic.commands.support.load_profile_or_none.
# "@OUT@" is replaced with a real tmp_path file so no script actually writes
# anywhere (it must fail before ever reaching the write step).
_MISSING_PROFILE_CASES = [
    (fit_check_module, [str(FIXTURE_JD)]),
    (generate_job_site_letter_module, [str(FIXTURE_JD), "--out", "@OUT@.txt"]),
    (generate_cover_letter_module, [str(FIXTURE_JD), "--out", "@OUT@.docx"]),
    (generate_resume_module, [str(FIXTURE_JD), "--out", "@OUT@.docx"]),
    (
        generate_thank_you_letter_module,
        [str(FIXTURE_JD), "--discussion-point", "test", "--out", "@OUT@.docx"],
    ),
    (generate_cold_call_letter_module, [str(FIXTURE_JD), "--out", "@OUT@.docx"]),
    (interview_prep_module, [str(FIXTURE_JD), "--out", "@OUT@.docx"]),
    (gap_analysis_module, [str(FIXTURE_JD), "--out", "@OUT@.md"]),
]


@pytest.mark.parametrize(
    "module,argv", _MISSING_PROFILE_CASES, ids=[m.__name__ for m, _ in _MISSING_PROFILE_CASES]
)
def test_main_missing_profile_returns_clean_error_not_crash(
    module, argv, tmp_path: Path, tmp_vault: Path, capsys
) -> None:
    # ``tmp_vault`` is a vault with no profile in it.
    out_file = tmp_path / "out"
    argv = [a.replace("@OUT@", str(out_file)) for a in argv]

    rc = module.main(argv)

    assert rc == 1
    assert "ERROR" in capsys.readouterr().err
    assert not any(tmp_path.glob("out.*"))


@pytest.mark.parametrize(
    "module",
    [m for m, _ in _MISSING_PROFILE_CASES],
    ids=[m.__name__ for m, _ in _MISSING_PROFILE_CASES],
)
def test_no_command_takes_a_root_option(module, capsys) -> None:
    """There is one way to locate data: the vault (ADR 0029)."""
    with pytest.raises(SystemExit) as excinfo:
        module.main([str(FIXTURE_JD), "--root", "somewhere"])
    assert excinfo.value.code == 2
    assert "--root" in capsys.readouterr().err


def test_interview_prep_has_no_star_bank_path_option(capsys) -> None:
    """The story bank is the vault's stories.yaml; it cannot be redirected (ADR 0029)."""
    with pytest.raises(SystemExit) as excinfo:
        cli_main(["interview-prep", str(FIXTURE_JD), "--star-bank-path", "somewhere"])
    assert excinfo.value.code == 2
    assert "--star-bank-path" in capsys.readouterr().err


def test_fit_check_runs_on_sample_jd(capsys) -> None:
    assert FIXTURE_JD.exists()
    assert fit_check_main([str(FIXTURE_JD)]) == 0
    out = capsys.readouterr().out
    assert "Fit Check" in out
    assert "Fit Rating:" in out
    assert "Contoso Cloud Solutions" in out


def test_gap_analysis_writes_markdown_report(tmp_path: Path) -> None:
    out_file = tmp_path / "GapAnalysis.md"
    assert gap_analysis_main([str(FIXTURE_JD), "--out", str(out_file)]) == 0
    assert out_file.exists()
    text = out_file.read_text(encoding="utf-8")
    assert "# Gap Analysis:" in text
    assert "Summary Table" in text
    assert "Contoso Cloud Solutions" in text


def test_generate_linkedin_writes_copy(tmp_path: Path) -> None:
    out_file = tmp_path / "LinkedIn.md"
    assert linkedin_main(["--out", str(out_file)]) == 0
    assert out_file.exists()
    text = out_file.read_text(encoding="utf-8")
    assert "# LinkedIn Profile Update Draft" in text


def test_generate_github_writes_readme(tmp_path: Path) -> None:
    out_file = tmp_path / "GitHub.md"
    assert github_main(["--out", str(out_file)]) == 0
    assert out_file.exists()
    text = out_file.read_text(encoding="utf-8")
    assert "# GitHub Profile Update Draft" in text
    assert "## Step 3 — Profile README" in text


def test_generate_jobgether_writes_copy(tmp_path: Path) -> None:
    out_file = tmp_path / "Jobgether.md"
    assert jobgether_main(["--out", str(out_file)]) == 0
    assert out_file.exists()
    text = out_file.read_text(encoding="utf-8")
    assert "# Jobgether Profile Update Draft" in text
    assert "## Resume File Dependency Check" in text


def test_generate_job_board_writes_copy(tmp_path: Path) -> None:
    out_file = tmp_path / "JobBoard.md"
    assert job_board_main(["--out", str(out_file)]) == 0
    assert out_file.exists()
    text = out_file.read_text(encoding="utf-8")
    assert "# Indeed & ZipRecruiter Profile Update Draft" in text
    assert "## Resume File Dependency Check" in text


def test_generate_pluralsight_writes_copy(tmp_path: Path) -> None:
    out_file = tmp_path / "Pluralsight.md"
    assert pluralsight_main(["--out", str(out_file)]) == 0
    assert out_file.exists()
    text = out_file.read_text(encoding="utf-8")
    assert "# Pluralsight Profile Update Draft" in text


def _run_cli_command(command: str, out_file: Path, company: str = "SampleCo") -> int:
    if command in {
        "generate-linkedin",
        "generate-github",
        "generate-jobgether",
        "generate-job-board",
        "generate-pluralsight",
    }:
        return cli_main([command, "--out", str(out_file)])
    argv = [command, str(FIXTURE_JD), "--company", company, "--out", str(out_file)]
    return cli_main(argv)


def _assert_docx_created(out_file: Path) -> None:
    assert out_file.exists()
    assert out_file.stat().st_size > 0


def test_generate_resume_writes_docx(tmp_path: Path) -> None:
    out_file = tmp_path / "resume.docx"
    assert _run_cli_command("generate-resume", out_file) == 0
    _assert_docx_created(out_file)


def test_generate_cover_letter_writes_docx(tmp_path: Path) -> None:
    out_file = tmp_path / "cover.docx"
    assert _run_cli_command("generate-cover-letter", out_file) == 0
    _assert_docx_created(out_file)


def test_generate_cold_call_writes_docx(tmp_path: Path) -> None:
    out_file = tmp_path / "cold_call.docx"
    assert _run_cli_command("generate-cold-call", out_file) == 0
    _assert_docx_created(out_file)


def test_generate_cold_call_without_jd_uses_recruiter_and_role_type(tmp_path: Path) -> None:
    """The Phase 3 fix: no JD file needed on the CLI either."""
    out_file = tmp_path / "cold_call_no_jd.docx"
    assert (
        cli_main(
            [
                "generate-cold-call",
                "--recruiter-name",
                "Jane Doe",
                "--role-type",
                "Senior .NET Developer roles",
                "--out",
                str(out_file),
            ]
        )
        == 0
    )
    _assert_docx_created(out_file)


def test_generate_job_site_writes_txt(tmp_path: Path) -> None:
    out_file = tmp_path / "job_site.txt"
    assert _run_cli_command("generate-job-site", out_file) == 0
    assert out_file.exists()
    text = out_file.read_text(encoding="utf-8")
    assert len(text) > 0
    assert "Full-Stack .NET Developer" in text


def test_generate_thank_you_writes_docx(tmp_path: Path) -> None:
    # Unlike the other letter generators, generate-thank-you requires
    # --discussion-point regardless of whether a JD is given (Phase 4 fix) —
    # doesn't fit the shared _run_cli_command helper's uniform argv shape.
    out_file = tmp_path / "thank_you.docx"
    assert (
        cli_main(
            [
                "generate-thank-you",
                str(FIXTURE_JD),
                "--company",
                "SampleCo",
                "--discussion-point",
                "We discussed the team's roadmap.",
                "--out",
                str(out_file),
            ]
        )
        == 0
    )
    _assert_docx_created(out_file)


def test_generate_thank_you_without_discussion_point_fails_closed(tmp_path: Path) -> None:
    out_file = tmp_path / "thank_you_fail.docx"
    assert (
        cli_main(
            ["generate-thank-you", str(FIXTURE_JD), "--company", "SampleCo", "--out", str(out_file)]
        )
        == 1
    )
    assert not out_file.exists()


def test_interview_prep_writes_docx(tmp_path: Path) -> None:
    out_file = tmp_path / "InterviewPrep.docx"
    assert cli_main(["interview-prep", str(FIXTURE_JD), "--out", str(out_file)]) == 0
    _assert_docx_created(out_file)


def test_interview_prep_stage_flag_accepted(tmp_path: Path) -> None:
    out_file = tmp_path / "InterviewPrep.docx"
    assert (
        cli_main(
            [
                "interview-prep",
                str(FIXTURE_JD),
                "--stage",
                "phone_screen",
                "--out",
                str(out_file),
            ]
        )
        == 0
    )
    _assert_docx_created(out_file)


def test_interview_prep_update_star_bank_records_the_story_use(tmp_path: Path) -> None:
    """Runs against the throwaway demo vault, never a real one."""
    out_file = tmp_path / "InterviewPrep.docx"
    before = (paths.profile_dir() / "stories.yaml").read_text(encoding="utf-8")

    assert (
        cli_main(["interview-prep", str(FIXTURE_JD), "--out", str(out_file), "--update-star-bank"])
        == 0
    )

    _assert_docx_created(out_file)
    assert (paths.profile_dir() / "stories.yaml").read_text(encoding="utf-8") != before


def test_interview_prep_hybrid_content_flags_accepted(tmp_path: Path) -> None:
    company_research_file = tmp_path / "company-research.md"
    company_research_file.write_text("SampleCo just closed a Series B.", encoding="utf-8")
    recruiter_briefing_file = tmp_path / "recruiter-briefing.md"
    recruiter_briefing_file.write_text("Two rounds, technical then panel.", encoding="utf-8")
    qa_cards_file = tmp_path / "qa-cards.json"
    qa_cards_file.write_text(
        json.dumps([{"question": "Walk me through your resume.", "answer": "..."}]),
        encoding="utf-8",
    )
    salary_section_file = tmp_path / "salary.md"
    salary_section_file.write_text("Target range: $120K-$140K CAD.", encoding="utf-8")
    out_file = tmp_path / "InterviewPrep.docx"

    assert (
        cli_main(
            [
                "interview-prep",
                str(FIXTURE_JD),
                "--out",
                str(out_file),
                "--stage",
                "final_round",
                "--company-research",
                str(company_research_file),
                "--recruiter-briefing",
                str(recruiter_briefing_file),
                "--qa-cards",
                str(qa_cards_file),
                "--salary-section",
                str(salary_section_file),
            ]
        )
        == 0
    )
    _assert_docx_created(out_file)


def test_interview_prep_malformed_qa_cards_json_fails_closed(tmp_path: Path) -> None:
    qa_cards_file = tmp_path / "qa-cards.json"
    qa_cards_file.write_text("{not valid json", encoding="utf-8")
    out_file = tmp_path / "InterviewPrep.docx"

    assert (
        cli_main(
            [
                "interview-prep",
                str(FIXTURE_JD),
                "--out",
                str(out_file),
                "--qa-cards",
                str(qa_cards_file),
            ]
        )
        == 1
    )
    assert not out_file.exists()


def test_generate_learning_plan_writes_pdf(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[1] / "templates" / "roles" / "_example.json"
    cfg = json.loads(example.read_text(encoding="utf-8"))
    out_file = tmp_path / "smoke.pdf"
    cfg["output"] = str(out_file)
    cfg_path = tmp_path / "smoke.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    assert cli_main(["generate-learning-plan", str(cfg_path)]) == 0
    assert out_file.exists() and out_file.stat().st_size > 0


@pytest.mark.parametrize(
    "fixture,expected_rating",
    [
        # Was Stretch only because "Strong Azure fundamentals (App Service,
        # Azure Functions, Cosmos DB)" was chopped into fragments that matched
        # nothing (a false gap). Rated as one requirement it is covered, which
        # leaves 2 course/portfolio-only required skills and 9 nice-to-haves.
        ("sample-jd.md", "Strong"),
        ("data-engineer-jd.md", "Pass"),
        # Two upstream bugs previously inflated this rating:
        # (1) _extract_experience_sections (the old markdown parser) used
        #     one regex spanning from a "### " heading to its own pipe-
        #     delimited "**Company | Location | Dates**" line; for the
        #     pipe-less "Professional Development & Portfolio Building"
        #     entry, that let the match lazily reach past its own block into
        #     the *next* real job's header line, merging the two entries
        #     into one bogus record and losing "Senior Full-Stack Developer
        #     / Acme Software" as its own entry.
        # (2) _has_skill (src/jobomatic/fit/engine.py) treated every
        #     profile.resume_roles entry as production evidence, so
        #     that merged entry's coursework prose ("Azure Functions
        #     through targeted coursework") was counted as a production
        #     "match" instead of course-level evidence.
        # With both fixed, "Professional Development & Portfolio Building"
        # parses as its own entry with no company and is excluded from the
        # production-match loop, correctly downgrading skills like Azure
        # Functions/Terraform to course-only. The genuine required gaps are
        # just 2 (bicep; "observability with azure monitor" — the compound
        # phrase doesn't tokenize down to "azure monitor" since "with" isn't
        # a recognized splitter, so it doesn't hit the coursework match
        # despite "Azure Monitor" appearing in technical_skills) -> Stretch.
        # ADR 0021: the same skills now read "Worth a try" (no core gap, two thirds covered).
        ("cloud-devops-jd.md", "Worth a try"),
        ("frontend-angular-jd.md", "Pass"),
        # Same strong skills, different location: the location rules (Quebec,
        # hybrid outside Springfield) force Pass; remote / Springfield stay Strong.
        ("strong-fit-jd.md", "Strong"),
        ("strong-skills-remote-jd.md", "Strong"),
        ("strong-skills-quebec-jd.md", "Pass"),
        ("strong-skills-hybrid-toronto-jd.md", "Pass"),
    ],
)
def test_fit_check_various_jds(capsys, fixture: str, expected_rating: str) -> None:
    jd_path = FIXTURES_DIR / fixture
    assert jd_path.exists()
    assert fit_check_main([str(jd_path)]) == 0
    out = capsys.readouterr().out
    assert "Fit Check" in out
    assert "Fit Rating:" in out
    assert f"Fit Rating: {expected_rating}" in out, f"expected {expected_rating} in:\n{out}"


def test_fit_check_explains_location_pass_and_shows_skills_would_be_strong(capsys) -> None:
    assert fit_check_main([str(FIXTURES_DIR / "strong-skills-quebec-jd.md")]) == 0
    out = capsys.readouterr().out
    assert "Fit Rating: Pass" in out
    assert "Outside job-search constraints" in out
    assert "Skills alone would rate Strong" in out
    assert "**Location & work arrangement**" in out
    assert "🚫 Quebec-based role" in out


def test_fit_check_has_no_location_section_for_clean_location(capsys) -> None:
    assert fit_check_main([str(FIXTURES_DIR / "strong-skills-remote-jd.md")]) == 0
    assert "Location & work arrangement" not in capsys.readouterr().out


def test_fit_check_scores_a_sentence_style_posting_instead_of_failing_it(capsys) -> None:
    """A posting whose requirements are full sentences under "Required
    Qualifications" used to parse to nothing (or, once headings were fixed, to
    a wall of false gaps and a Pass). It must now yield real skill rows, list
    the degree line as a soft requirement, and surface the location flag."""
    assert fit_check_main([str(FIXTURES_DIR / "prose-qualifications-jd.md")]) == 0
    out = capsys.readouterr().out
    assert "| c# | ✅ |" in out
    assert "| azure | ✅ |" in out
    assert "No required skills provided" not in out
    assert "genuine gaps in required skills — critical mismatch" not in out
    assert "**Soft requirements**" in out
    assert "Education — equivalent accepted: Computer science degree or equivalent" in out
    assert "⚠️ Remote posting lists" in out
    assert "Fit Rating: Pass" not in out


# ── salary screen in fit-check ───────────────────────────────────────────────


def _jd_with_pay(tmp_path: Path, pay_line: str) -> Path:
    text = (REPO_ROOT / "tests" / "fixtures" / "strong-fit-jd.md").read_text(encoding="utf-8")
    path = tmp_path / "jd-with-pay.md"
    path.write_text(text + f"\n\n## Compensation\n{pay_line}\n", encoding="utf-8")
    return path


def _write_constraints(monkeypatch_dir: Path) -> None:
    monkeypatch_dir.mkdir(parents=True, exist_ok=True)
    (monkeypatch_dir / "search-constraints.json").write_text(
        '{"min_permanent_base_cad": 85000, "min_contract_hourly_cad": 60}', encoding="utf-8"
    )


def test_fit_check_flags_pay_below_minimum(tmp_path, capsys, _isolate_personal_data) -> None:
    from jobomatic.commands.fit_check import main

    _write_constraints(_isolate_personal_data / "private")
    assert main([str(_jd_with_pay(tmp_path, "Salary: $60,000 - $72,000 per year"))]) == 0
    out = capsys.readouterr().out
    assert "Salary screen" in out and "🔴" in out and "Ask the user whether to continue" in out


def test_fit_check_confirms_pay_at_or_above_minimum(
    tmp_path, capsys, _isolate_personal_data
) -> None:
    from jobomatic.commands.fit_check import main

    _write_constraints(_isolate_personal_data / "private")
    main([str(_jd_with_pay(tmp_path, "Salary: $90,000 - $110,000 per year"))])
    assert "✅" in capsys.readouterr().out


def test_fit_check_without_constraints_file_notes_it_and_does_not_fail(tmp_path, capsys) -> None:
    from jobomatic.commands.fit_check import main

    assert main([str(_jd_with_pay(tmp_path, "Salary: $60,000 per year"))]) == 0
    out = capsys.readouterr().out
    assert "no minimums are configured" in out and "search-constraints.json" in out


def test_fit_check_with_malformed_constraints_fails_loudly(
    tmp_path, capsys, _isolate_personal_data
) -> None:
    from jobomatic.commands.fit_check import main

    d = _isolate_personal_data / "private"
    d.mkdir()
    (d / "search-constraints.json").write_text('{"min_base": 1}', encoding="utf-8")
    assert main([str(_jd_with_pay(tmp_path, "Salary: $60,000 per year"))]) == 1
    assert "unknown key" in capsys.readouterr().err


def test_fit_check_prints_nothing_extra_when_no_pay_is_posted(capsys) -> None:
    from jobomatic.commands.fit_check import main

    main([str(REPO_ROOT / "tests" / "fixtures" / "strong-fit-jd.md")])
    assert "Salary screen" not in capsys.readouterr().out


def test_story_mentions_treats_slash_hyphen_and_space_alike() -> None:
    from jobomatic.commands.support import story_mentions

    assert story_mentions("pipeline ownership ci-cd testing", "CI/CD")
    # a row that joins two skills counts when the story names either one
    assert story_mentions("pipeline ownership ci-cd testing", "CI/CD with GitHub Actions")
    # the old match was a bare substring, so "ci" hit "specific" and "stakeholder-communication"
    assert not story_mentions("a specific stakeholder-communication story", "CI/CD")


def test_a_missing_vault_is_a_clean_error_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobomatic import paths

    # No variable, no config file, and a checkout whose parent holds no sibling vault: never the
    # real ../job-o-matic-vault.
    monkeypatch.delenv("JOBOMATIC_VAULT", raising=False)
    monkeypatch.setenv("JOBOMATIC_CONFIG", str(tmp_path / "no-config.toml"))
    monkeypatch.setattr(paths, "code_root", lambda: tmp_path / "checkout")
    assert cli_main(["profile", "validate"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("ERROR: No vault found") and "JOBOMATIC_VAULT" in err
