"""The gates run inside the commands themselves (ADR 0028), not in the command line's dispatcher.

``tests/test_command_snapshots.py`` shows that a command called directly refuses what the gate
refuses. These tests cover the rest of that move: the confirmations work when a command is called
directly, a refusal leaves no trace, and a skills Pass or a location Pass still cannot be
confirmed past.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jobomatic import applications
from jobomatic.commands import cold_call, cover_letter, job_site_letter, resume
from jobomatic.interfaces.cli.main import main as cli_main
from tests.command_cases import PASS_SKILLS, QUEBEC, STRETCH_SKILLS, STRONG, Env, _jd


@pytest.fixture
def env(tmp_path: Path) -> Env:
    work, out = tmp_path / "work", tmp_path / "out"
    work.mkdir()
    out.mkdir()
    return Env(work=work, out=out)


@pytest.mark.parametrize("module", [resume, cover_letter], ids=["resume", "cover_letter"])
def test_a_stretch_is_confirmed_past_with_the_flag_when_called_directly(
    module, env: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    out = env.out / "doc.docx"
    jd = _jd(env, "stretch.md", *STRETCH_SKILLS)
    assert module.main([jd, "--out", str(out), "--confirm-gaps"]) == 0
    assert out.exists()
    assert "Proceeding past a Stretch rating" in capsys.readouterr().out


@pytest.mark.parametrize("module", [resume, cover_letter], ids=["resume", "cover_letter"])
def test_a_skills_pass_is_never_confirmed_past(module, env: Env) -> None:
    out = env.out / "doc.docx"
    jd = _jd(env, "pass.md", *PASS_SKILLS)
    assert module.main([jd, "--out", str(out), "--confirm-gaps"]) == 2
    assert not out.exists()


@pytest.mark.parametrize(
    "module, suffix",
    [(resume, ".docx"), (cover_letter, ".docx"), (job_site_letter, ".txt"), (cold_call, ".docx")],
    ids=["resume", "cover_letter", "job_site_letter", "cold_call"],
)
def test_a_location_pass_is_never_confirmed_past(module, suffix: str, env: Env) -> None:
    out = env.out / f"doc{suffix}"
    argv = [str(QUEBEC), "--out", str(out)]
    if module is not cold_call:
        argv.append("--confirm-reapply")
    assert module.main(argv) == 2
    assert not out.exists()


def test_a_repeat_application_is_confirmed_past_with_the_flag(env: Env) -> None:
    assert cli_main(["applications", "applied", "--jd", str(STRONG)]) == 0
    out = env.out / "site.txt"
    assert job_site_letter.main([str(STRONG), "--out", str(out)]) == 2
    assert not out.exists()
    assert job_site_letter.main([str(STRONG), "--out", str(out), "--confirm-reapply"]) == 0
    assert out.exists()


@pytest.mark.parametrize(
    "module", [resume, cover_letter, job_site_letter, cold_call], ids=lambda m: m.__name__
)
def test_a_refusal_leaves_nothing_in_the_applications_log(module, env: Env) -> None:
    out = env.out / "doc.docx"
    assert module.main([str(QUEBEC), "--out", str(out)]) == 2
    assert applications.find_for_jd(QUEBEC.read_text(encoding="utf-8")) is None


def test_a_gated_command_on_a_missing_posting_says_where_it_looked(
    env: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = env.work / "missing.md"
    assert resume.main([str(missing), "--out", str(env.out / "r.docx")]) == 1
    err = capsys.readouterr().err
    assert err.startswith("ERROR: JD file not found:")
    assert str(missing) in err
    assert "Errno" not in err


def test_the_command_line_forwards_the_confirmation_to_the_command(env: Env) -> None:
    out = env.out / "resume.docx"
    jd = _jd(env, "stretch.md", *STRETCH_SKILLS)
    assert cli_main(["generate-resume", jd, "--out", str(out)]) == 2
    assert cli_main(["generate-resume", jd, "--out", str(out), "--confirm-gaps"]) == 0
    assert out.exists()
