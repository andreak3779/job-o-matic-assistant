from datetime import date, timedelta
from pathlib import Path

import pytest

from jobomatic import applications as apps
from jobomatic.interfaces.cli.main import main

FIXTURES = Path(__file__).resolve().parent / "fixtures"
STRONG = FIXTURES / "strong-fit-jd.md"
WEAK = FIXTURES / "data-engineer-jd.md"


def _jd(
    tmp_path: Path, company: str = "Contoso", job_id: str = "REQ-1", title: str = "Dev"
) -> Path:
    path = tmp_path / f"jd-{company}-{job_id}.md"
    path.write_text(
        f"# {title}\n\n**Company:** {company}\n**Job ID:** {job_id}\n\n## Requirements\n- C#\n",
        encoding="utf-8",
    )
    return path


def test_add_then_applied_then_list(tmp_path: Path, capsys) -> None:
    jd = _jd(tmp_path)
    assert main(["applications", "add", str(jd), "--platform", "LinkedIn"]) == 0
    assert "Added as drafted" in capsys.readouterr().out
    [app] = apps.load_applications()
    assert app.status == "drafted" and app.platform == "LinkedIn"

    assert main(["applications", "applied", "--id", app.id, "--date", "2026-10-01"]) == 0
    assert apps.get_application(app.id).applied_on == "2026-10-01"

    assert main(["applications", "list", "--status", "applied"]) == 0
    out = capsys.readouterr().out
    assert "Contoso" in out and "applied" in out


def test_add_is_idempotent(tmp_path: Path, capsys) -> None:
    jd = _jd(tmp_path)
    main(["applications", "add", str(jd)])
    main(["applications", "add", str(jd)])
    assert "Already in the log" in capsys.readouterr().out
    assert len(apps.load_applications()) == 1


def test_applied_by_jd_creates_the_entry_if_it_was_never_drafted(tmp_path: Path) -> None:
    jd = _jd(tmp_path)
    assert main(["applications", "applied", "--jd", str(jd)]) == 0
    [app] = apps.load_applications()
    assert app.status == "applied" and app.applied_on == date.today().isoformat()


def test_applied_by_jd_reuses_an_existing_draft(tmp_path: Path) -> None:
    jd = _jd(tmp_path)
    main(["applications", "add", str(jd)])
    main(["applications", "applied", "--jd", str(jd), "--date", "2026-10-02"])
    [app] = apps.load_applications()
    assert app.status == "applied" and app.applied_on == "2026-10-02"


def test_applied_requires_an_id_or_a_jd(capsys) -> None:
    with pytest.raises(SystemExit):
        main(["applications", "applied"])


def test_bad_date_and_unknown_id_fail_cleanly(tmp_path: Path, capsys) -> None:
    jd = _jd(tmp_path)
    main(["applications", "add", str(jd)])
    [app] = apps.load_applications()
    assert main(["applications", "applied", "--id", app.id, "--date", "tomorrow"]) == 1
    assert "ISO date" in capsys.readouterr().err
    assert main(["applications", "applied", "--id", "zzzz"]) == 1
    assert "no application" in capsys.readouterr().err


def test_status_command(tmp_path: Path, capsys) -> None:
    jd = _jd(tmp_path)
    main(["applications", "applied", "--jd", str(jd)])
    [app] = apps.load_applications()
    assert main(["applications", "status", app.id, "phone_screen", "--next-step", "Call Tue"]) == 0
    assert apps.get_application(app.id).next_step == "Call Tue"


def test_check_reports_new_duplicate_and_strict_exit_code(tmp_path: Path, capsys) -> None:
    jd = _jd(tmp_path)
    assert main(["applications", "check", str(jd)]) == 0
    assert "NEW" in capsys.readouterr().out

    recent = (date.today() - timedelta(days=5)).isoformat()
    main(["applications", "applied", "--jd", str(jd), "--date", recent])
    capsys.readouterr()
    assert main(["applications", "check", str(jd)]) == 0
    assert "DUPLICATE" in capsys.readouterr().out
    assert main(["applications", "check", str(jd), "--strict"]) == 2


def test_check_related_shows_other_roles_at_the_company(tmp_path: Path, capsys) -> None:
    main(
        ["applications", "applied", "--jd", str(_jd(tmp_path, job_id="REQ-1", title="Backend Dev"))]
    )
    capsys.readouterr()
    main(["applications", "check", str(_jd(tmp_path, job_id="REQ-2", title="Data Engineer"))])
    assert "RELATED" in capsys.readouterr().out


def test_missing_jd_file_is_a_clean_error(tmp_path: Path, capsys) -> None:
    assert main(["applications", "check", str(tmp_path / "nope.md")]) == 1
    assert "not found" in capsys.readouterr().err


# ── generating documents logs 'drafted' only ─────────────────────────────────


@pytest.mark.parametrize(
    "command,kind",
    [("generate-resume", "resume"), ("generate-cover-letter", "cover_letter")],
)
def test_generating_documents_records_a_draft_never_applied(
    tmp_path: Path, capsys, command, kind
) -> None:
    out = tmp_path / "doc.docx"
    assert main([command, str(STRONG), "--out", str(out)]) == 0
    assert "Logged as drafted (not applied)" in capsys.readouterr().out
    [app] = apps.load_applications()
    assert app.status == "drafted" and app.applied_on is None
    assert kind in app.documents and app.fit_rating in {"Strong", "Good"}


def test_resume_then_cover_letter_share_one_entry(tmp_path: Path) -> None:
    main(["generate-resume", str(STRONG), "--out", str(tmp_path / "r.docx")])
    main(["generate-cover-letter", str(STRONG), "--out", str(tmp_path / "c.docx")])
    [app] = apps.load_applications()
    assert set(app.documents) == {"resume", "cover_letter"}


def test_generation_does_not_downgrade_an_applied_entry(tmp_path: Path) -> None:
    main(["applications", "applied", "--jd", str(STRONG), "--date", "2026-10-01"])
    main(["generate-resume", str(STRONG), "--out", str(tmp_path / "r.docx"), "--confirm-reapply"])
    [app] = apps.load_applications()
    assert app.status == "applied" and "resume" in app.documents


def test_thank_you_and_interview_prep_do_not_touch_the_log(tmp_path: Path) -> None:
    main(
        [
            "generate-thank-you",
            str(STRONG),
            "--out",
            str(tmp_path / "t.docx"),
            "--discussion-point",
            "We discussed sprint priorities.",
        ]
    )
    main(["interview-prep", str(STRONG), "--out", str(tmp_path / "i.docx")])
    assert apps.load_applications() == []


def test_a_failed_generation_records_nothing(tmp_path: Path) -> None:
    assert main(["generate-resume", str(tmp_path / "missing.md")]) != 0
    assert apps.load_applications() == []


# ── CSV import ───────────────────────────────────────────────────────────────


def test_import_csv_dry_run_then_real(tmp_path: Path, capsys) -> None:
    csv_file = tmp_path / "t.csv"
    csv_file.write_text(
        "Company,Role,Platform,Date Applied,Status,Next Step\n"
        'Example Corp,Senior .NET Developer,LinkedIn,"Apr 21, 2026",Applied,Follow up\n',
        encoding="utf-8",
    )
    assert main(["applications", "import-csv", str(csv_file), "--dry-run"]) == 0
    assert "Would import 1" in capsys.readouterr().out
    assert apps.load_applications() == []
    assert main(["applications", "import-csv", str(csv_file)]) == 0
    assert apps.load_applications()[0].applied_on == "2026-04-21"


def test_import_csv_reports_errors_with_nonzero_exit(tmp_path: Path, capsys) -> None:
    csv_file = tmp_path / "t.csv"
    csv_file.write_text("Company,Role,Date Applied\nAcme,Dev,04/05/2026\n", encoding="utf-8")
    assert main(["applications", "import-csv", str(csv_file)]) == 1
    assert "ambiguous date" in capsys.readouterr().err


# ── constraints ──────────────────────────────────────────────────────────────


def test_constraints_show_missing_and_present(capsys, _isolate_personal_data) -> None:
    assert main(["constraints", "show"]) == 0
    assert "No private/search-constraints.json" in capsys.readouterr().out
    private = _isolate_personal_data / "private"
    private.mkdir()
    (private / "search-constraints.json").write_text(
        '{"min_permanent_base_cad": 85000}', encoding="utf-8"
    )
    assert main(["constraints", "show"]) == 0
    assert "$85,000" in capsys.readouterr().out


def test_a_missing_relative_jd_names_the_current_folder(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["applications", "check", "nope.md"]) == 1
    err = capsys.readouterr().err
    assert f"Current folder: {tmp_path}" in err
    assert "give the full path" in err
