"""scripts/migrate_outputs.py: old loose files into the outputs hierarchy, on fictional files."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

from jobomatic import applications as apps

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migrate_outputs.py"


def _load():
    spec = importlib.util.spec_from_file_location("migrate_outputs", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["migrate_outputs"] = module
    spec.loader.exec_module(module)
    return module


migrate = _load()


def _touch(path: Path, day: str, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    stamp = datetime.fromisoformat(f"{day}T12:00:00+00:00").timestamp()
    os.utime(path, (stamp, stamp))
    return path


@pytest.fixture
def outputs(tmp_path: Path) -> Path:
    return tmp_path / "outputs"


def _plan(outputs: Path, log_apps=()):
    return {str(m.src): (str(m.dest), m.why) for m in migrate.plan(outputs, list(log_apps))}


def test_files_for_one_employer_share_one_dated_folder(outputs: Path) -> None:
    old = outputs / "_legacy_import" / "outputs"
    _touch(old / "Sarah_Resume_BrightPath.docx", "2026-10-02")
    _touch(old / "Sarah_CoverLetter_BrightPath.docx", "2026-10-03")
    _touch(old / "SalaryExpectations_BrightPath.md", "2026-10-04")
    planned = _plan(outputs)
    folder = "applications/2026-10-02_bright-path"
    assert (
        planned["_legacy_import/outputs/Sarah_Resume_BrightPath.docx"][0] == f"{folder}/resume.docx"
    )
    assert planned["_legacy_import/outputs/Sarah_CoverLetter_BrightPath.docx"][0] == (
        f"{folder}/cover-letter.docx"
    )
    assert planned["_legacy_import/outputs/SalaryExpectations_BrightPath.md"][0] == (
        f"{folder}/salary.md"
    )


def test_a_file_is_filed_under_the_logged_application_it_matches(
    outputs: Path, tmp_path: Path
) -> None:
    log = tmp_path / "applications.jsonl"
    first = apps.create_application(
        "Acme Health Inc.", "Full Stack Developer", path=log, day="2026-10-10"
    )
    second = apps.create_application(
        "Acme Health Inc.", "Senior .NET Engineer", path=log, day="2026-10-11"
    )
    old = outputs / "_legacy_import" / "outputs"
    _touch(old / "Sarah_Resume_AcmeHealth.docx", "2026-10-10")
    _touch(old / "Sarah_Resume_AcmeHealthSeniorNET.docx", "2026-10-11")
    planned = _plan(outputs, apps.load_applications(log))
    assert planned["_legacy_import/outputs/Sarah_Resume_AcmeHealth.docx"] == (
        f"applications/{first}/resume.docx",
        "matches a logged application",
    )
    assert planned["_legacy_import/outputs/Sarah_Resume_AcmeHealthSeniorNET.docx"][0] == (
        f"applications/{second}/resume.docx"
    )


def test_sidecars_follow_their_file_and_the_sidecar_date_wins(outputs: Path) -> None:
    old = outputs / "_legacy_import" / "outputs"
    resume = _touch(old / "Sarah_Resume_Acme.docx", "2026-10-30")
    side = old / "Sarah_Resume_Acme.docx.meta.json"
    side.write_text(json.dumps({"generated_at": "2026-09-01T10:00:00Z"}), encoding="utf-8")
    assert resume.exists()
    planned = _plan(outputs)
    assert planned["_legacy_import/outputs/Sarah_Resume_Acme.docx.meta.json"][0] == (
        "applications/2026-09-01_acme/resume.docx.meta.json"
    )


def test_generic_names_go_to_templates_and_research(outputs: Path) -> None:
    old = outputs / "_legacy_import" / "outputs"
    _touch(old / "Sarah_Resume_SeniorFullStackNET.docx", "2026-10-01")
    _touch(old / "Sarah_CoverLetter_Template.docx", "2026-10-01")
    _touch(old / "SalaryExpectations_General.md", "2026-10-01")
    _touch(old / "JobFitRecommendations.md", "2026-10-01")
    planned = _plan(outputs)
    assert {v[0] for v in planned.values()} == {
        "templates/resume.docx",
        "templates/cover-letter.docx",
        "research/salary-expectations.md",
        "research/job-fit-recommendations.md",
    }


def test_part_time_outreach_and_profile_drafts(outputs: Path) -> None:
    old = outputs / "_legacy_import" / "outputs"
    _touch(old / "part-time" / "Sarah_PartTimeResume_CornerShop.docx", "2026-10-05")
    _touch(old / "Sarah_ColdCall_TalentCo.docx", "2026-10-06")
    _touch(outputs / "profiles" / "drafts" / "linkedin-profile-update-draft.md", "2026-10-07")
    planned = _plan(outputs)
    assert {v[0] for v in planned.values()} == {
        "part-time/2026-10-05_corner-shop/resume.docx",
        "outreach/2026-10-06_talent-co/cold-outreach.docx",
        "profiles/linkedin/2026-10-07.md",
    }


def test_anything_unrecognised_goes_to_unsorted_with_its_old_path(outputs: Path) -> None:
    old = outputs / "_legacy_import"
    _touch(old / "outputs" / "tmp" / "scratch.js", "2026-10-01")
    _touch(old / "project-2-outputs" / "data.json", "2026-10-01")
    _touch(old / "outputs" / ".gitkeep", "2026-10-01")
    planned = _plan(outputs)
    assert planned == {
        "_legacy_import/outputs/tmp/scratch.js": (
            "_unsorted/outputs/tmp/scratch.js",
            "not recognised",
        ),
        "_legacy_import/project-2-outputs/data.json": (
            "_unsorted/project-2-outputs/data.json",
            "not recognised",
        ),
    }


def test_when_two_files_want_one_place_the_newer_wins_and_nothing_is_lost(outputs: Path) -> None:
    old = outputs / "_legacy_import" / "outputs"
    _touch(old / "Sarah_Resume_Acme.docx", "2026-10-20", "new")
    _touch(old / "outputs.bak" / "Sarah_Resume_Acme.docx", "2026-10-10", "old")
    planned = _plan(outputs)
    assert planned["_legacy_import/outputs/Sarah_Resume_Acme.docx"][0].startswith("applications/")
    older = planned["_legacy_import/outputs/outputs.bak/Sarah_Resume_Acme.docx"]
    assert older[0] == "_unsorted/outputs/outputs.bak/Sarah_Resume_Acme.docx"
    assert "older than" in older[1]


def test_dry_run_changes_nothing_and_apply_moves_everything(
    outputs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault = tmp_path
    old = outputs / "_legacy_import" / "outputs"
    _touch(old / "Sarah_Resume_Acme.docx", "2026-10-02", "resume text")
    _touch(old / "tmp" / "scratch.js", "2026-10-02", "js")
    before = sorted(p.relative_to(outputs) for p in outputs.rglob("*") if p.is_file())

    assert migrate.main(["--vault", str(vault)]) == 0
    assert "Dry run" in capsys.readouterr().out
    assert sorted(p.relative_to(outputs) for p in outputs.rglob("*") if p.is_file()) == before

    assert migrate.main(["--vault", str(vault), "--apply"]) == 0
    moved = outputs / "applications" / "2026-10-02_acme" / "resume.docx"
    assert moved.read_text(encoding="utf-8") == "resume text"
    assert (outputs / "_unsorted" / "outputs" / "tmp" / "scratch.js").read_text() == "js"
    assert not (old / "Sarah_Resume_Acme.docx").exists()
    mapping = (outputs / "_migration-map.tsv").read_text(encoding="utf-8")
    assert "Sarah_Resume_Acme.docx\tapplications/2026-10-02_acme/resume.docx" in mapping


def test_apply_never_overwrites_an_existing_file(outputs: Path, tmp_path: Path) -> None:
    old = outputs / "_legacy_import" / "outputs"
    _touch(old / "Sarah_Resume_Acme.docx", "2026-10-02", "incoming")
    existing = _touch(
        outputs / "applications" / "2026-10-02_acme" / "resume.docx", "2026-10-02", "already here"
    )
    migrate.apply(outputs, migrate.plan(outputs, []))
    assert existing.read_text(encoding="utf-8") == "already here"
    assert (outputs / "_unsorted" / "outputs" / "Sarah_Resume_Acme.docx").read_text() == "incoming"
