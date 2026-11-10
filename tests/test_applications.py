import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from jobomatic import applications as apps

TODAY = date(2026, 10, 15)


@pytest.fixture
def log(tmp_path: Path) -> Path:
    return tmp_path / "applications.jsonl"


JD = """# Senior .NET Developer

**Company:** Contoso Cloud Solutions Inc.
**Job ID:** REQ-1234

## Requirements
- C#
- Azure
"""


# ── event log ────────────────────────────────────────────────────────────────


def test_missing_log_is_empty(log: Path) -> None:
    assert apps.load_applications(log) == []


def test_create_and_fold(log: Path) -> None:
    app_id = apps.create_application("Acme", "Dev", path=log, fit_rating="Strong")
    [app] = apps.load_applications(log)
    assert (app.id, app.company, app.title, app.status, app.fit_rating) == (
        app_id,
        "Acme",
        "Dev",
        "drafted",
        "Strong",
    )
    assert not app.submitted


def test_log_is_append_only_one_json_object_per_line(log: Path) -> None:
    a = apps.create_application("Acme", "Dev", path=log)
    before = log.read_text().splitlines()
    apps.update_application(a, path=log, notes="hello")
    after = log.read_text().splitlines()
    assert after[: len(before)] == before and len(after) == len(before) + 1
    assert all(isinstance(json.loads(line), dict) for line in after)


def test_documents_accumulate_without_duplicates(log: Path) -> None:
    a = apps.create_application("Acme", "Dev", path=log, documents=["resume"])
    apps.update_application(a, path=log, documents=["resume", "cover_letter"])
    assert apps.get_application(a, log).documents == ("resume", "cover_letter")


def test_events_fold_in_timestamp_order_regardless_of_file_order(log: Path) -> None:
    """Two laptops merging via union can interleave lines; the fold must not care."""
    lines = [
        {
            "ts": "2026-10-02T10:00:00.000000Z",
            "id": "x",
            "op": "update",
            "data": {"notes": "later"},
        },
        {
            "ts": "2026-10-01T10:00:00.000000Z",
            "id": "x",
            "op": "create",
            "data": {"company": "Acme", "title": "Dev", "status": "drafted", "notes": "first"},
        },
    ]
    log.write_text("\n".join(json.dumps(e) for e in lines) + "\n")
    [app] = apps.load_applications(log)
    assert app.notes == "later" and app.created == "2026-10-01"


def test_update_for_unknown_id_is_rejected(log: Path) -> None:
    with pytest.raises(ValueError, match="no application"):
        apps.update_application("nope", path=log, notes="x")


@pytest.mark.parametrize(
    "line",
    ["{not json", '{"op": "create"}', '{"op":"zap","id":"a","ts":"t","data":{}}'],
)
def test_malformed_lines_fail_loudly_with_the_line_number(log: Path, line: str) -> None:
    log.write_text(line + "\n")
    with pytest.raises(ValueError, match="line 1"):
        apps.load_applications(log)


def test_unknown_field_is_rejected_on_write_and_read(log: Path) -> None:
    with pytest.raises(ValueError, match="unknown"):
        apps.create_application("A", "B", path=log, salary=1)
    log.write_text(json.dumps({"ts": "t", "id": "a", "op": "create", "data": {"salary": 1}}) + "\n")
    with pytest.raises(ValueError, match="unknown field"):
        apps.load_applications(log)


def test_invalid_status_and_date_are_rejected(log: Path) -> None:
    with pytest.raises(ValueError, match="status"):
        apps.create_application("A", "B", status="hired", path=log)
    a = apps.create_application("A", "B", path=log)
    with pytest.raises(ValueError, match="ISO date"):
        apps.update_application(a, path=log, applied_on="yesterday")


# ── applied is explicit ──────────────────────────────────────────────────────


def test_record_draft_never_marks_anything_applied(log: Path) -> None:
    apps.record_draft(JD, documents=("resume", "cover_letter"), fit_rating="Strong", path=log)
    [app] = apps.load_applications(log)
    assert app.status == "drafted" and app.applied_on is None and not app.submitted
    assert (app.company, app.job_id) == ("Contoso Cloud Solutions Inc.", "REQ-1234")


def test_mark_applied_is_the_explicit_transition(log: Path) -> None:
    a = apps.create_application("Acme", "Dev", path=log)
    done = apps.mark_applied(a, "2026-10-10", log)
    assert done.status == "applied" and done.applied_on == "2026-10-10" and done.submitted


def test_mark_applied_defaults_to_today(log: Path) -> None:
    a = apps.create_application("Acme", "Dev", path=log)
    assert apps.mark_applied(a, path=log).applied_on == date.today().isoformat()


def test_later_status_sets_applied_date_if_missing(log: Path) -> None:
    a = apps.create_application("Acme", "Dev", path=log)
    done = apps.set_status(a, "phone_screen", next_step="Call Tue", path=log)
    assert done.submitted and done.applied_on and done.next_step == "Call Tue"


def test_recording_a_draft_again_does_not_downgrade_an_applied_entry(log: Path) -> None:
    apps.record_draft(JD, documents=("resume",), path=log)
    [first] = apps.load_applications(log)
    apps.mark_applied(first.id, "2026-10-01", log)
    apps.record_draft(JD, documents=("cover_letter",), path=log)
    [app] = apps.load_applications(log)
    assert app.status == "applied" and set(app.documents) == {"resume", "cover_letter"}


def test_record_draft_skips_postings_whose_company_is_unreadable(log: Path) -> None:
    assert apps.record_draft("Just some words, no company.", path=log) is None
    assert apps.load_applications(log) == []


def test_record_draft_can_fall_back_to_a_company_override(log: Path) -> None:
    assert apps.record_draft("# Dev\n- C#", company_fallback="Acme", path=log)
    assert apps.load_applications(log)[0].company == "Acme"


# ── matching ─────────────────────────────────────────────────────────────────


def _app(company: str, title: str, job_id: str | None = None, **kw) -> apps.Application:
    return apps.Application(
        id=kw.pop("id", "a1"),
        company=company,
        title=title,
        status=kw.pop("status", "applied"),
        created="2026-09-01",
        updated="2026-09-01T00:00:00.000000Z",
        job_id=job_id,
        applied_on=kw.pop("applied_on", "2026-09-01"),
    )


@pytest.mark.parametrize(
    "other_company",
    ["Contoso Cloud Solutions", "CONTOSO CLOUD SOLUTIONS, INC.", "contoso cloud solutions ltd"],
)
def test_company_names_match_ignoring_case_punctuation_and_legal_suffix(other_company) -> None:
    assert apps.is_same_posting(
        _app("Contoso Cloud Solutions Inc.", "Dev"), other_company, "Dev", None
    )


def test_job_id_decides_when_both_sides_have_one() -> None:
    a = _app("Acme", "Developer", "REQ-1")
    assert apps.is_same_posting(a, "Acme", "Totally Different Title", "req 1")
    assert not apps.is_same_posting(a, "Acme", "Developer", "REQ-2")


def test_title_similarity_decides_without_ids() -> None:
    a = _app("Acme", "Senior .NET Developer")
    assert apps.is_same_posting(a, "Acme", "Senior .NET Developer", None)
    assert not apps.is_same_posting(a, "Acme", "Data Engineer", None)


def test_different_company_never_matches_even_with_same_job_id() -> None:
    assert not apps.is_same_posting(_app("Acme", "Dev", "1"), "Globex", "Dev", "1")


def test_unknown_placeholders_never_match() -> None:
    a = _app("Unknown Company", "Unknown Role")
    assert not apps.is_same_posting(a, "Unknown Company", "Unknown Role", None)


# ── duplicate check ──────────────────────────────────────────────────────────


def test_new_posting() -> None:
    assert apps.check_posting("Acme", "Dev", applications=[], today=TODAY).verdict == "new"


def test_duplicate_inside_the_window_blocks() -> None:
    applied = (TODAY - timedelta(days=10)).isoformat()
    check = apps.check_posting(
        "Acme", "Dev", applications=[_app("Acme", "Dev", applied_on=applied)], today=TODAY
    )
    assert check.verdict == "duplicate" and check.blocking and check.days_ago == 10
    assert "DUPLICATE" in check.summary()


def test_window_boundary() -> None:
    def verdict(days: int) -> str:
        applied = (TODAY - timedelta(days=days)).isoformat()
        return apps.check_posting(
            "Acme", "Dev", applications=[_app("Acme", "Dev", applied_on=applied)], today=TODAY
        ).verdict

    assert verdict(apps.DUPLICATE_WINDOW_DAYS) == "duplicate"
    assert verdict(apps.DUPLICATE_WINDOW_DAYS + 1) == "repeat"


def test_repeat_outside_the_window_does_not_block() -> None:
    check = apps.check_posting(
        "Acme", "Dev", applications=[_app("Acme", "Dev", applied_on="2026-01-01")], today=TODAY
    )
    assert check.verdict == "repeat" and not check.blocking


def test_drafted_only_does_not_block() -> None:
    check = apps.check_posting(
        "Acme",
        "Dev",
        applications=[_app("Acme", "Dev", status="drafted", applied_on=None)],
        today=TODAY,
    )
    assert check.verdict == "drafted" and not check.blocking


def test_same_company_different_role_is_related_not_a_duplicate() -> None:
    check = apps.check_posting(
        "Acme", "Data Engineer", applications=[_app("Acme", "Dev")], today=TODAY
    )
    assert check.verdict == "related" and not check.blocking


def test_no_response_pattern_is_flagged_after_two_unanswered_applications() -> None:
    history = [
        _app("Acme", "Dev A", id="1"),
        _app("Acme", "Dev B", id="2"),
    ]
    check = apps.check_posting("Acme", "Dev C", applications=history, today=TODAY)
    assert check.no_response_pattern and any("no response" in n for n in check.notes)


def test_a_company_that_responded_is_not_a_no_response_pattern() -> None:
    history = [_app("Acme", "Dev A", id="1", status="phone_screen"), _app("Acme", "Dev B", id="2")]
    assert not apps.check_posting(
        "Acme", "Dev C", applications=history, today=TODAY
    ).no_response_pattern


def test_check_jd_text_reads_company_title_and_job_id(log: Path) -> None:
    a = apps.record_draft(JD, path=log)
    apps.mark_applied(a, (date.today() - timedelta(days=3)).isoformat(), log)
    assert apps.check_jd_text(JD, path=log).verdict == "duplicate"
    other = JD.replace("REQ-1234", "REQ-9999")
    assert apps.check_jd_text(other, path=log).verdict != "duplicate"


# ── CSV import ───────────────────────────────────────────────────────────────

CSV_OK = """Company,Role,Platform,Date Applied,Status,Next Step
Example Corp,Senior .NET Developer,LinkedIn,"Apr 21, 2026",Applied,Follow up Apr 28
Globex,Backend Developer,Indeed,2026-05-02,Phone Screen,Call Tue
Initech,QA Lead,,,,
"""


def _csv(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "tracker.csv"
    path.write_text(text, encoding="utf-8-sig")
    return path


def test_import_creates_entries_with_dates_statuses_and_source(tmp_path: Path, log: Path) -> None:
    report = apps.import_csv(_csv(tmp_path, CSV_OK), path=log)
    assert len(report.created) == 3 and not report.errors
    by_company = {a.company: a for a in apps.load_applications(log)}
    ex = by_company["Example Corp"]
    assert (ex.status, ex.applied_on, ex.platform, ex.next_step, ex.source) == (
        "applied",
        "2026-04-21",
        "LinkedIn",
        "Follow up Apr 28",
        "csv-import",
    )
    assert by_company["Globex"].status == "phone_screen"
    assert by_company["Initech"].status == "drafted"  # no date, no status: never assumed applied


def test_import_is_idempotent(tmp_path: Path, log: Path) -> None:
    path = _csv(tmp_path, CSV_OK)
    apps.import_csv(path, path=log)
    again = apps.import_csv(path, path=log)
    assert again.created == [] and len(again.skipped_existing) == 3
    assert len(apps.load_applications(log)) == 3


def test_import_dry_run_writes_nothing_but_detects_repeated_rows(tmp_path: Path, log: Path) -> None:
    text = CSV_OK + "Globex,Backend Developer,Indeed,2026-05-02,Applied,\n"
    report = apps.import_csv(_csv(tmp_path, text), dry_run=True, path=log)
    assert not log.exists()
    assert len(report.created) == 3 and len(report.skipped_existing) == 1


def test_import_reports_bad_rows_and_keeps_good_ones(tmp_path: Path, log: Path) -> None:
    text = (
        "Company,Role,Date Applied,Status\n"
        "Good Co,Dev,2026-05-02,Applied\n"
        "Bad Date Co,Dev,04/05/2026,Applied\n"
        "Bad Status Co,Dev,2026-05-02,Hired!\n"
        ",,,\n"
        "No Role Co,,2026-05-02,Applied\n"
    )
    report = apps.import_csv(_csv(tmp_path, text), path=log)
    assert len(report.created) == 1
    assert len(report.errors) == 3
    assert any("ambiguous date" in e for e in report.errors)
    assert any("unrecognised status" in e for e in report.errors)
    assert any("missing company or role" in e for e in report.errors)


def test_import_accepts_alternative_headers(tmp_path: Path, log: Path) -> None:
    text = "Employer,Job Title,Applied On,Stage\nAcme,Dev,2026-05-02,Submitted\n"
    apps.import_csv(_csv(tmp_path, text), path=log)
    [app] = apps.load_applications(log)
    assert (app.company, app.title, app.status) == ("Acme", "Dev", "applied")


def test_import_requires_company_and_role_columns(tmp_path: Path, log: Path) -> None:
    with pytest.raises(ValueError, match="needs a Company column"):
        apps.import_csv(_csv(tmp_path, "Foo,Bar\n1,2\n"), path=log)


@pytest.mark.parametrize(
    "raw,iso",
    [
        ("2026-04-21", "2026-04-21"),
        ("Apr 21, 2026", "2026-04-21"),
        ("April 21, 2026", "2026-04-21"),
        ("21 Apr 2026", "2026-04-21"),
        ("2026-04-21 00:00:00", "2026-04-21"),
        ("21/04/2026", "2026-04-21"),
        ("04/21/2026", "2026-04-21"),
    ],
)
def test_parse_date(raw: str, iso: str) -> None:
    assert apps.parse_date(raw) == iso


@pytest.mark.parametrize("raw", ["04/05/2026", "soon", ""])
def test_parse_date_refuses_to_guess(raw: str) -> None:
    with pytest.raises(ValueError):
        apps.parse_date(raw)


def test_log_path_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_JOBS_APPLICATIONS_LOG", str(tmp_path / "x.jsonl"))
    assert apps.log_path() == tmp_path / "x.jsonl"
