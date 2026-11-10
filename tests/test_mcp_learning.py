"""The ``learning_import`` MCP tool: a dry run by default, bounded inputs, nothing else writable."""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from jobomatic import paths
from jobomatic.interfaces.mcp import server
from jobomatic.interfaces.mcp.server import learning_import
from jobomatic.learning.adapters.yaml_store import YamlLearningStore
from tests.learning_fixtures import page, row, transcript


@pytest.fixture
def vault(tmp_vault: Path) -> Path:
    return tmp_vault


def _entry(name: str, percent: str = "100.0%") -> dict[str, object]:
    return {
        "name": name,
        "type": "Course",
        "url": f"https://app.pluralsight.com/library/courses/{name.lower().replace(' ', '-')}",
        "duration": "1h 30m",
        "completion_percentage": percent,
        "completed_on": "2026-11-08",
    }


def _import_text(*entries: dict[str, object]) -> str:
    return json.dumps(
        {"format": "jobomatic-pluralsight-history", "version": 1, "entries": list(entries)}
    )


def _import_file(tmp_path: Path, *entries: dict[str, object]) -> Path:
    path = tmp_path / "pluralsight_import_2026-11-10.json"
    path.write_text(_import_text(*entries), encoding="utf-8")
    return path


def _items(vault: Path):
    return YamlLearningStore(paths.profile_dir()).load()


def test_the_default_is_a_dry_run() -> None:
    assert inspect.signature(learning_import).parameters["apply"].default is False


def test_a_dry_run_shows_the_plan_and_saves_nothing(vault: Path, tmp_path: Path) -> None:
    file = _import_file(tmp_path, _entry("Learn Azure Things"), _entry("Half Done", "40.0%"))
    out = learning_import(file=str(file))
    assert "+ Learn Azure Things" in out and "Dry run" in out
    assert _items(vault) == []
    assert not list((vault / "imports").rglob("*.json"))


def test_apply_saves_the_items_keeps_the_export_and_a_rerun_is_quiet(
    vault: Path, tmp_path: Path
) -> None:
    file = _import_file(tmp_path, _entry("Learn Azure Things"))
    out = learning_import(file=str(file), apply=True)
    assert "Saved 1 new item" in out and "index build" in out
    assert [i.title for i in _items(vault)] == ["Learn Azure Things"]
    assert list((vault / "imports" / "pluralsight").glob("*.json"))

    again = learning_import(file=str(file), apply=True)
    assert "0 new, 0 changed" in again and "Nothing to save" in again
    assert "index build" not in again  # nothing was saved, so no follow-up to suggest


def test_content_is_accepted_for_a_small_import_file(vault: Path) -> None:
    out = learning_import(content=_import_text(_entry("From Pasted Text")), apply=True)
    assert "Saved 1 new item" in out
    [item] = _items(vault)
    assert item.title == "From Pasted Text"
    assert item.source.startswith("pluralsight_import_") and item.source.endswith(".json")


def test_content_may_be_a_saved_history_page(vault: Path) -> None:
    out = learning_import(content=page([row("Learn Page Things")]), apply=True)
    assert "Saved" in out
    assert any(i.title == "Learn Page Things" for i in _items(vault))


def test_exactly_one_of_file_and_content(tmp_path: Path) -> None:
    file = _import_file(tmp_path, _entry("X"))
    with pytest.raises(ToolError, match="exactly one"):
        learning_import()
    with pytest.raises(ToolError, match="exactly one"):
        learning_import(file=str(file), content=_import_text(_entry("X")))


def test_a_file_outside_the_readable_directories_is_refused() -> None:
    outside = Path.home() / ".jobomatic-test-import.json"  # need not exist: the policy runs first
    with pytest.raises(ToolError, match="outside the directories"):
        learning_import(file=str(outside))


def test_only_export_file_types_can_be_imported(vault: Path) -> None:
    secret = vault / "profile" / "identity.yaml"
    secret.write_text("headline: private\n", encoding="utf-8")
    with pytest.raises(ToolError, match=r"must be \.html"):
        learning_import(file=str(secret))
    assert _items(vault) == []


def test_a_missing_file_is_a_clear_error(vault: Path) -> None:
    with pytest.raises(ToolError, match="not found"):
        learning_import(file=str(vault / "imports" / "nope.json"))


def test_a_microsoft_learn_transcript_is_refused_and_saves_nothing(
    vault: Path, tmp_path: Path
) -> None:
    path = tmp_path / "transcript.json"
    path.write_text(json.dumps(transcript()), encoding="utf-8")
    with pytest.raises(ToolError, match="Nothing was imported"):
        learning_import(file=str(path), apply=True)
    assert _items(vault) == []


def test_an_unrecognised_file_is_refused_and_saves_nothing(vault: Path) -> None:
    bad = json.dumps({"format": "jobomatic-pluralsight-history", "version": 9, "entries": []})
    with pytest.raises(ToolError, match="Nothing was imported"):
        learning_import(content=bad, apply=True)
    assert _items(vault) == []


def test_oversized_content_is_refused(vault: Path) -> None:
    with pytest.raises(ToolError, match="too large"):
        learning_import(content="[" + " " * (2 * 1024 * 1024 + 1) + "]")
    assert _items(vault) == []


def test_the_throwaway_copy_of_content_is_removed(vault: Path) -> None:
    import tempfile

    before = set(Path(tempfile.gettempdir()).glob("pluralsight-import-*"))
    learning_import(content=_import_text(_entry("Cleanup Check")))
    assert set(Path(tempfile.gettempdir()).glob("pluralsight-import-*")) == before


def test_a_json_import_file_passed_as_content_survives_the_mcp_argument_parsing(
    vault: Path,
) -> None:
    """The framework turns a string that looks like JSON into an object before the tool runs;
    calling the function directly (as the tests above do) skips that, so go through the server."""
    text = _import_text(_entry("Through The Protocol"))
    result = asyncio.run(server.mcp.call_tool("learning_import", {"content": text}))
    assert "+ Through The Protocol" in str(result)
    assert _items(vault) == []  # still a dry run

    asyncio.run(server.mcp.call_tool("learning_import", {"content": text, "apply": True}))
    assert [i.title for i in _items(vault)] == ["Through The Protocol"]


def test_content_given_as_an_already_parsed_object_is_accepted(vault: Path) -> None:
    parsed = json.loads(_import_text(_entry("Parsed Object")))
    assert "Saved 1 new item" in learning_import(content=parsed, apply=True)
    assert [i.title for i in _items(vault)] == ["Parsed Object"]
    with pytest.raises(ToolError, match="Nothing was imported"):
        learning_import(content={})  # an empty object is not an import file
