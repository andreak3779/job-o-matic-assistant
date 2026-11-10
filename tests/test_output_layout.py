"""The outputs hierarchy: paths, readable application ids, and one folder per posting (ADR 0015)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from jobomatic import applications as apps
from jobomatic import paths
from jobomatic.applications import outputs
from jobomatic.interfaces.cli.main import main

STRONG = Path(__file__).parent / "fixtures" / "strong-fit-jd.md"
JD_TEXT = STRONG.read_text(encoding="utf-8")
COMPANY_ROLE = "northgate-insurance-group_senior-full-stack-net-developer"


# -- jobomatic.paths ---------------------------------------------------------------------------


def test_slug_is_lowercase_hyphenated_and_never_empty() -> None:
    assert paths.slug("Acme Health, Inc.") == "acme-health-inc"
    assert paths.slug("  ") == "unknown"
    assert paths.slug("x" * 100) == "x" * 40


def test_folder_name_skips_empty_parts() -> None:
    assert paths.folder_name(date(2026, 10, 31), "Acme", None, "") == "2026-10-31_acme"
    assert paths.folder_name("2026-10-31", "Acme", ".NET Dev") == "2026-10-31_acme_net-dev"


def test_output_dir_for_each_kind(tmp_vault: Path) -> None:
    out = tmp_vault / "outputs"
    day = date(2026, 10, 31)
    assert paths.output_dir("application", day=day, company="Acme", role="Dev") == (
        out / "applications" / "2026-10-31_acme_dev"
    )
    assert paths.output_dir("part-time", day=day, company="Corner Shop", role="ignored") == (
        out / "part-time" / "2026-10-31_corner-shop"
    )
    assert paths.output_dir("outreach", day=day, company="Talent Co") == (
        out / "outreach" / "2026-10-31_talent-co"
    )
    assert paths.output_dir("profiles", platform="LinkedIn") == out / "profiles" / "linkedin"
    assert paths.output_dir("learning-plans") == out / "learning-plans"
    assert paths.output_dir("research") == out / "research"
    assert paths.output_dir("templates") == out / "templates"
    assert paths.output_dir("application", name="custom") == out / "applications" / "custom"


def test_output_dir_rejects_bad_requests(tmp_vault: Path) -> None:
    with pytest.raises(ValueError, match="unknown output kind"):
        paths.output_dir("downloads")
    with pytest.raises(ValueError, match="needs a platform"):
        paths.output_dir("profiles")
    with pytest.raises(ValueError, match="needs a day and a company"):
        paths.output_dir("application", company="Acme")


# -- application ids ------------------------------------------------------------------------


def test_new_application_ids_are_readable_and_unique(tmp_path: Path) -> None:
    log = tmp_path / "applications.jsonl"
    first = apps.create_application("Acme Health", "Senior Dev", path=log, day="2026-10-31")
    second = apps.create_application("Acme Health", "Senior Dev", path=log, day="2026-10-31")
    assert first == "2026-10-31_acme-health_senior-dev"
    assert second == f"{first}-2"
    assert paths.is_dated_name(first) and paths.is_dated_name(second)


def test_folder_name_for_an_application_with_an_old_random_id(tmp_path: Path) -> None:
    app = apps.Application(
        id="bb67a357",
        company="Acme Health",
        title="Senior Dev",
        status="drafted",
        created="2026-10-15",
        updated="2026-10-15T10:00:00.000000Z",
    )
    assert apps.folder_name_for(app) == "2026-10-15_acme-health_senior-dev"


# -- locating the folder for a posting ------------------------------------------------------


def test_logging_generators_create_the_entry_and_name_the_folder_after_it(tmp_vault: Path) -> None:
    located = outputs.locate_application(
        JD_TEXT, log=True, documents=("resume",), fit_rating="Strong"
    )
    assert located.logged and located.app_id
    assert located.folder == tmp_vault / "outputs" / "applications" / located.app_id
    assert located.app_id.endswith(f"_{COMPANY_ROLE}")
    assert (located.folder / "jd.md").read_text(encoding="utf-8") == JD_TEXT


def test_a_second_document_reuses_the_same_folder(tmp_vault: Path) -> None:
    first = outputs.locate_application(JD_TEXT, log=True, documents=("resume",))
    second = outputs.locate_application(JD_TEXT, log=True, documents=("cover_letter",))
    assert first.folder == second.folder
    assert len(apps.load_applications()) == 1


def test_non_logging_documents_never_create_an_entry(tmp_vault: Path) -> None:
    located = outputs.locate_application(JD_TEXT, log=False)
    assert located.app_id is None and not located.logged
    assert apps.load_applications() == []


def test_non_logging_documents_reuse_an_existing_entry(tmp_vault: Path) -> None:
    logged = outputs.locate_application(JD_TEXT, log=True, documents=("resume",))
    later = outputs.locate_application(JD_TEXT, log=False)
    assert later.app_id == logged.app_id and later.folder == logged.folder and not later.logged


def test_an_earlier_unlogged_folder_is_adopted_when_the_entry_is_created(tmp_vault: Path) -> None:
    early = tmp_vault / "outputs" / "applications" / f"2026-09-01_{COMPANY_ROLE}"
    early.mkdir(parents=True)
    located = outputs.locate_application(JD_TEXT, log=True, documents=("resume",))
    assert located.folder == early
    assert located.app_id == early.name
    assert [p.name for p in (tmp_vault / "outputs" / "applications").iterdir()] == [early.name]


def test_explicit_output_path_leaves_the_disk_alone(tmp_vault: Path) -> None:
    located = outputs.locate_application(
        JD_TEXT, log=True, documents=("resume",), create_folder=False
    )
    assert located.logged
    assert not located.folder.exists()


# -- generators, end to end -----------------------------------------------------------------


def test_documents_for_one_posting_share_one_dated_folder() -> None:
    vault = paths.vault_root()
    assert main(["generate-resume", str(STRONG)]) == 0
    assert main(["generate-cover-letter", str(STRONG)]) == 0
    assert main(["gap-analysis", str(STRONG)]) == 0
    assert main(["interview-prep", str(STRONG)]) == 0
    [folder] = (vault / "outputs" / "applications").iterdir()
    assert {p.name for p in folder.iterdir() if not p.name.endswith(".meta.json")} == {
        "jd.md",
        "resume.docx",
        "cover-letter.docx",
        "gap-analysis.md",
        "interview-prep.docx",
    }
    [app] = apps.load_applications()
    assert app.id == folder.name and set(app.documents) == {"resume", "cover_letter"}


def test_gap_analysis_alone_leaves_the_log_empty_but_files_its_folder() -> None:
    vault = paths.vault_root()
    assert main(["gap-analysis", str(STRONG)]) == 0
    assert apps.load_applications() == []
    [folder] = (vault / "outputs" / "applications").iterdir()
    assert (folder / "gap-analysis.md").is_file()
    # applying later adopts that folder instead of starting a second one
    assert main(["generate-resume", str(STRONG)]) == 0
    assert [p.name for p in (vault / "outputs" / "applications").iterdir()] == [folder.name]
    assert (folder / "resume.docx").is_file()


def test_application_dir_prints_the_folder_and_does_not_log(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["application-dir", str(STRONG)]) == 0
    printed = Path(capsys.readouterr().out.strip())
    assert printed.parent == paths.vault_root() / "outputs" / "applications"
    assert printed.name.endswith(COMPANY_ROLE)
    assert (printed / "jd.md").is_file()
    assert apps.load_applications() == []
    assert main(["application-dir", str(STRONG.parent / "missing.md")]) == 1


def test_cold_outreach_goes_to_its_own_dated_folder() -> None:
    vault = paths.vault_root()
    assert main(["generate-cold-call", "--company", "Talent Co"]) == 0
    [folder] = (vault / "outputs" / "outreach").iterdir()
    assert folder.name == f"{date.today().isoformat()}_talent-co"
    assert (folder / "cold-outreach.docx").is_file()
    assert apps.load_applications() == []
