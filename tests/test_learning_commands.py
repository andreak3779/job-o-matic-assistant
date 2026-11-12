"""The learning import and the learning plan as commands that return a result (ADR 0028)."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from jobomatic import paths
from jobomatic.commands import learning_import, learning_plan
from jobomatic.learning.adapters.yaml_store import YamlLearningStore
from jobomatic.results import console
from tests.command_cases import REPO

ENTRY = {
    "name": "Learn Azure Things",
    "type": "Course",
    "url": "https://app.pluralsight.com/library/courses/learn-azure-things",
    "duration": "1h 30m",
    "completion_percentage": "100.0%",
    "completed_on": "2026-11-08",
}


def _export(tmp_path: Path, *entries: dict[str, object]) -> Path:
    path = tmp_path / "pluralsight_import_2026-11-10.json"
    path.write_text(
        json.dumps(
            {"format": "jobomatic-pluralsight-history", "version": 1, "entries": list(entries)}
        ),
        encoding="utf-8",
    )
    return path


def _stored() -> int:
    return len(YamlLearningStore(paths.profile_dir()).load())


def test_a_dry_run_returns_the_plan_and_saves_nothing(
    tmp_vault: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = learning_import.run(_export(tmp_path, ENTRY), "pluralsight")
    assert result.status == "ok"
    assert result.data is not None
    assert [item.title for item in result.data.plan.new] == ["Learn Azure Things"]
    assert result.data.applied is False and result.data.kept is None
    assert result.written == ()
    assert "Dry run: nothing was saved" in learning_import.render(result.data)
    assert capsys.readouterr() == ("", "")
    assert not (paths.profile_dir() / "learning" / "items.yaml").exists()


def test_applying_saves_the_items_and_keeps_the_export(tmp_vault: Path, tmp_path: Path) -> None:
    result = learning_import.run(_export(tmp_path, ENTRY), "pluralsight", apply=True)
    assert result.data is not None and result.data.kept is not None
    assert result.data.kept.exists()
    assert _stored() == 1
    assert f"the export is kept as {result.data.kept}" in learning_import.render(result.data)


def test_applying_the_same_export_again_has_nothing_to_save(
    tmp_vault: Path, tmp_path: Path
) -> None:
    export = _export(tmp_path, ENTRY)
    learning_import.run(export, "pluralsight", apply=True)
    again = learning_import.run(export, "pluralsight", apply=True)
    assert again.data is not None and again.data.kept is None
    assert learning_import.render(again.data).endswith("Nothing to save.")
    assert _stored() == 1


def test_an_export_that_cannot_be_read_is_reported_as_the_learning_commands_always_have(
    tmp_vault: Path, tmp_path: Path
) -> None:
    broken = tmp_path / "pluralsight_import_x.json"
    broken.write_text("{not json", encoding="utf-8")
    result = learning_import.run(broken, "pluralsight")
    assert result.status == "error"
    assert console(result).stdout.startswith("[ERROR] ")


def test_two_callers_applying_the_same_export_save_one_item(
    tmp_vault: Path, tmp_path: Path
) -> None:
    """Applying reads the stored items and then writes them, so it holds the write lock."""
    export = _export(tmp_path, ENTRY)
    callers = [
        threading.Thread(target=lambda: learning_import.run(export, "pluralsight", apply=True))
        for _ in range(2)
    ]
    for caller in callers:
        caller.start()
    for caller in callers:
        caller.join()
    assert _stored() == 1


# -- the learning plan -------------------------------------------------------------------------


def _role_config(tmp_path: Path, **changes: object) -> Path:
    config = json.loads((REPO / "templates" / "roles" / "_example.json").read_text("utf-8"))
    config["output"] = str(tmp_path / "plan.pdf")
    config.update(changes)
    path = tmp_path / "role.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_the_plan_is_rendered_and_the_pdf_is_what_was_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = learning_plan.run(_role_config(tmp_path))
    assert result.status == "ok"
    assert result.written == (tmp_path / "plan.pdf",)
    assert result.data is not None and result.data.pdf.read_bytes().startswith(b"%PDF")
    assert capsys.readouterr() == ("", "")


def test_a_missing_config_is_an_error_that_names_it(tmp_path: Path) -> None:
    result = learning_plan.run(tmp_path / "nope.json")
    assert result.status == "error"
    assert result.messages[-1].text == f"config file not found: {tmp_path / 'nope.json'}"


def test_a_config_that_is_not_json_says_where(tmp_path: Path) -> None:
    config = tmp_path / "role.json"
    config.write_text("{not json", encoding="utf-8")
    result = learning_plan.run(config)
    assert result.status == "error"
    assert result.messages[-1].text.startswith(f"JSON parse error in {config}")


def test_an_invalid_config_is_an_error_and_writes_nothing(tmp_path: Path) -> None:
    result = learning_plan.run(_role_config(tmp_path, plan="not a list"))
    assert result.status == "error" and result.written == ()
    assert not (tmp_path / "plan.pdf").exists()
