"""The resume and cover letter as commands that return a result (ADR 0028)."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from jobomatic import applications as apps
from jobomatic.commands import cover_letter, resume
from jobomatic.commands.support import (
    Confirmations,
    DocumentData,
    produce_document,
    vault_write_lock,
)
from jobomatic.results import Message
from tests.command_cases import PASS_SKILLS, QUEBEC, STRETCH_SKILLS, STRONG, Env, _jd

POSTING = STRONG.read_text(encoding="utf-8")
COMMANDS = [pytest.param(resume, id="resume"), pytest.param(cover_letter, id="cover_letter")]


@pytest.fixture
def env(tmp_path: Path) -> Env:
    work, out = tmp_path / "work", tmp_path / "out"
    work.mkdir()
    out.mkdir()
    return Env(work=work, out=out)


@pytest.mark.parametrize("module", COMMANDS)
def test_run_returns_the_document_and_what_it_wrote_and_prints_nothing(
    module, env: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    out = env.out / "doc.docx"
    result = module.run(POSTING, out=out)
    assert result.status == "ok"
    assert isinstance(result.data, DocumentData)
    assert result.data.path == out
    assert result.data.fit is not None and result.data.fit.rating == "Strong"
    assert result.written == (out, Path(f"{out}.meta.json"))
    assert all(path.exists() for path in result.written)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("module", COMMANDS)
def test_the_messages_are_the_rating_then_the_draft_that_was_logged(module, env: Env) -> None:
    result = module.run(POSTING, out=env.out / "doc.docx")
    levels_and_text = [(m.level, m.text) for m in result.messages]
    assert levels_and_text[0][0] == "info" and levels_and_text[0][1].startswith(
        "Fit Rating: Strong"
    )
    assert levels_and_text[-1][1].startswith("Logged as drafted (not applied): application ")


@pytest.mark.parametrize("module", COMMANDS)
def test_a_stretch_is_refused_with_the_override_that_would_clear_it(module, env: Env) -> None:
    out = env.out / "doc.docx"
    posting = Path(_jd(env, "stretch.md", *STRETCH_SKILLS)).read_text(encoding="utf-8")
    result = module.run(posting, out=out)
    assert result.status == "refused" and result.exit_code == 2
    assert result.override == "confirm_gaps"
    assert result.written == () and not out.exists()


@pytest.mark.parametrize("module", COMMANDS)
def test_a_stretch_goes_ahead_once_the_user_confirms(module, env: Env) -> None:
    posting = Path(_jd(env, "stretch.md", *STRETCH_SKILLS)).read_text(encoding="utf-8")
    result = module.run(posting, out=env.out / "doc.docx", confirm=Confirmations(gaps=True))
    assert result.status == "ok"
    notes = [m.text for m in result.messages if m.level == "note"]
    assert any(n.startswith("Proceeding past a Stretch rating") for n in notes)


@pytest.mark.parametrize("module", COMMANDS)
def test_a_skills_pass_and_a_location_pass_cannot_be_confirmed_past(module, env: Env) -> None:
    everything = Confirmations(gaps=True, reapply=True, below_minimum=True)
    for text in (
        Path(_jd(env, "pass.md", *PASS_SKILLS)).read_text(encoding="utf-8"),
        QUEBEC.read_text(encoding="utf-8"),
    ):
        result = module.run(text, out=env.out / "doc.docx", confirm=everything)
        assert result.status == "refused" and result.override is None


@pytest.mark.parametrize("module", COMMANDS)
def test_a_refusal_records_nothing(module, env: Env) -> None:
    module.run(QUEBEC.read_text(encoding="utf-8"), out=env.out / "doc.docx")
    assert apps.load_applications() == []


@pytest.mark.parametrize("module", COMMANDS)
def test_the_sidecar_records_the_posting_file_only_when_there_was_one(module, env: Env) -> None:
    from_file = env.out / "from-file.docx"
    module.run(POSTING, source=STRONG, out=from_file)
    assert json.loads(Path(f"{from_file}.meta.json").read_text())["inputs"] == [str(STRONG)]
    pasted = env.out / "pasted.docx"
    module.run(POSTING, out=pasted, confirm=Confirmations(reapply=True))
    assert json.loads(Path(f"{pasted}.meta.json").read_text())["inputs"] == []


@pytest.mark.parametrize("module", COMMANDS)
def test_a_broken_profile_is_an_error_result(module, env: Env, tmp_vault: Path) -> None:
    result = module.run(POSTING, out=env.out / "doc.docx")
    assert result.status == "error" and result.written == ()


def test_the_function_that_takes_a_path_still_prints_for_a_direct_caller(
    env: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    """Callers that pass no ``notes`` list (tests, scripts) see what the command line always did."""
    resume.generate_resume(STRONG, out_path=env.out / "doc.docx")
    assert "Logged as drafted (not applied): application " in capsys.readouterr().out


def _another_thread_can_take_the_lock() -> bool:
    """Try to take the lock from another thread, and let go again if that worked."""
    got: list[bool] = []

    def attempt() -> None:
        lock = vault_write_lock()
        acquired = lock.acquire(blocking=False)
        got.append(acquired)
        if acquired:
            lock.release()  # a thread that ends holding it would block every later caller

    other = threading.Thread(target=attempt)
    other.start()
    other.join()
    return got[0]


def test_a_document_run_holds_the_vault_write_lock_until_it_is_done() -> None:
    """The duplicate check and the draft it records must not interleave with another caller."""
    during: list[bool] = []

    def make(profile, notes: list[Message]):
        during.append(_another_thread_can_take_the_lock())
        return Path("a.docx"), Path("a.docx.meta.json"), None

    produce_document(make=make)
    assert during == [False]  # another thread could not take the lock while it was made
    assert _another_thread_can_take_the_lock()  # and it is free again afterwards
