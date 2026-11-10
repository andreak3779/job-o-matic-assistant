"""The applications use cases run on any log that honours the port (here, a list in memory)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from jobomatic.applications import service
from jobomatic.applications.adapters.jsonl_log import JsonlApplicationLog


class MemoryLog:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def read_events(self) -> list[dict[str, Any]]:
        return list(self.events)

    def append(self, event: dict[str, Any]) -> None:
        self.events.append(event)


def test_create_then_read_back_without_any_file() -> None:
    log = MemoryLog()
    app_id = service.create_application(log, "Acme", "Developer", fit_rating="Good")
    (app,) = service.load_applications(log)
    assert app.id == app_id and app.status == "drafted" and app.fit_rating == "Good"
    assert len(log.events) == 1 and log.events[0]["op"] == "create"


def test_a_second_application_with_the_same_name_gets_a_suffix() -> None:
    log = MemoryLog()
    first = service.create_application(log, "Acme", "Developer", day="2026-01-02")
    second = service.create_application(log, "Acme", "Developer", day="2026-01-02")
    assert second == f"{first}-2"


def test_drafting_never_marks_applied_but_an_explicit_call_does() -> None:
    log = MemoryLog()
    app_id = service.create_application(log, "Acme", "Developer")
    assert not service.get_application(log, app_id).submitted
    done = service.mark_applied(log, app_id, "2026-03-04")
    assert done.status == "applied" and done.applied_on == "2026-03-04"


def test_set_status_to_a_later_stage_fills_in_the_applied_date() -> None:
    log = MemoryLog()
    app_id = service.create_application(log, "Acme", "Developer")
    updated = service.set_status(log, app_id, "phone_screen", next_step="call Tuesday")
    assert updated.applied_on == date.today().isoformat()
    assert updated.next_step == "call Tuesday"


def test_the_log_only_ever_grows() -> None:
    log = MemoryLog()
    app_id = service.create_application(log, "Acme", "Developer")
    before = list(log.events)
    service.update_application(log, app_id, notes="hello")
    assert log.events[: len(before)] == before and len(log.events) == len(before) + 1


def test_an_update_for_an_unknown_id_is_refused() -> None:
    with pytest.raises(ValueError, match="no application"):
        service.update_application(MemoryLog(), "nope", notes="x")


def test_a_bad_status_is_refused_before_anything_is_written() -> None:
    log = MemoryLog()
    with pytest.raises(ValueError, match="status must be one of"):
        service.create_application(log, "Acme", "Developer", status="hired")
    assert log.events == []


def test_the_duplicate_check_runs_on_the_in_memory_log() -> None:
    log = MemoryLog()
    app_id = service.create_application(log, "Acme Inc", "Backend Developer")
    service.mark_applied(log, app_id, date.today().isoformat())
    check = service.check_posting(log, "Acme", "Backend Developer")
    assert check.verdict == "duplicate" and check.blocking


def test_record_draft_reuses_the_entry_for_the_same_posting() -> None:
    log = MemoryLog()
    jd = "# Backend Developer\n\n**Company:** Acme\n\n## Requirements\n- C#\n"
    first = service.record_draft(log, jd, documents=("resume",))
    second = service.record_draft(log, jd, documents=("cover_letter",))
    assert first == second
    (app,) = service.load_applications(log)
    assert set(app.documents) == {"resume", "cover_letter"}


def test_the_jsonl_adapter_round_trips_events(tmp_path: Path) -> None:
    log = JsonlApplicationLog(tmp_path / "nested" / "applications.jsonl")
    assert log.read_events() == []
    app_id = service.create_application(log, "Acme", "Developer")
    assert [a.id for a in service.load_applications(log)] == [app_id]


def test_the_jsonl_adapter_names_the_bad_line(tmp_path: Path) -> None:
    path = tmp_path / "applications.jsonl"
    path.write_text('{"op": "create"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"applications\.jsonl line 1 is not a valid event"):
        JsonlApplicationLog(path).read_events()
