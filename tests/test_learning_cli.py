"""The ``learning`` commands, run against a throwaway vault."""

from __future__ import annotations

import json
import socket
import urllib.request
from pathlib import Path

import pytest

from jobomatic import paths
from jobomatic.interfaces.cli.main import main
from jobomatic.learning.adapters.yaml_store import YamlLearningStore
from tests.learning_fixtures import page, row, transcript


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """No learning test may reach the network, whatever the code under test does."""

    def refuse(*_args, **_kwargs):
        raise AssertionError("a test tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture
def vault(tmp_vault: Path) -> Path:
    return tmp_vault


def _export(tmp_path: Path, *rows: str) -> Path:
    path = tmp_path / "ps.html"
    path.write_text(page(list(rows)), encoding="utf-8")
    return path


def _items(vault: Path):
    return YamlLearningStore(paths.profile_dir()).load()


def test_dry_run_shows_the_plan_and_saves_nothing(
    vault: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = _export(tmp_path, row("Learn Azure Things"))
    assert main(["learning", "import", str(export)]) == 0
    out = capsys.readouterr().out
    assert "+ Learn Azure Things" in out and "Microsoft Azure" in out
    assert "Dry run" in out
    assert _items(vault) == []
    assert not (vault / "imports").exists() or not any((vault / "imports").rglob("*.html"))


def test_apply_saves_items_and_keeps_the_export_and_a_rerun_is_quiet(
    vault: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = _export(tmp_path, row("Learn Azure Things"))
    assert main(["learning", "import", str(export), "--apply"]) == 0
    assert any(i.title == "Learn Azure Things" for i in _items(vault))
    assert list((vault / "imports" / "pluralsight").glob("*.html"))
    capsys.readouterr()
    assert main(["learning", "import", str(export), "--apply"]) == 0
    assert "Nothing to save" in capsys.readouterr().out


def test_microsoft_learn_file_is_cleaned_of_owner_fields_before_it_is_kept(
    vault: Path, tmp_path: Path
) -> None:
    raw = tmp_path / "transcript.json"
    raw.write_text(json.dumps(transcript()), encoding="utf-8")
    assert main(["learning", "import", str(raw), "--apply"]) == 0
    [kept] = list((vault / "imports" / "mslearn").glob("*.json"))
    text = kept.read_text(encoding="utf-8")
    assert "Sarah Ashford" not in text and "contactEmail" not in text
    assert len(_items(vault)) == 3


def test_a_page_it_cannot_read_is_an_error_and_nothing_is_saved(
    vault: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.html"
    bad.write_text("<html></html>", encoding="utf-8")
    assert main(["learning", "import", str(bad), "--apply"]) == 1
    assert "Nothing was imported" in capsys.readouterr().out
    assert _items(vault) == []


def test_import_needs_exactly_one_of_a_file_or_mslearn(vault: Path, tmp_path: Path) -> None:
    assert main(["learning", "import"]) == 1
    assert main(["learning", "import", str(_export(tmp_path)), "--mslearn"]) == 1


def test_mslearn_flag_needs_a_share_id_in_the_vault(
    vault: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_JOBS_PRIVATE_DIR", str(vault / "private"))
    assert main(["learning", "import", "--mslearn"]) == 1
    assert "mslearn_share_id" in capsys.readouterr().out


def test_mslearn_flag_fetches_cleans_and_saves(
    vault: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CLAUDE_JOBS_PRIVATE_DIR", str(vault / "private"))
    (vault / "private" / "sources.yaml").write_text("mslearn_share_id: abc123\n", encoding="utf-8")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, *_):
            return json.dumps(transcript()).encode()

    urls = []

    def fake_urlopen(request, timeout):
        urls.append(request.full_url)
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert main(["learning", "import", "--mslearn", "--apply"]) == 0
    assert urls == ["https://learn.microsoft.com/api/profiles/transcript/share/abc123"]
    assert len(_items(vault)) == 3
    [kept] = list((vault / "imports" / "mslearn").glob("*.json"))
    assert "Sarah Ashford" not in kept.read_text(encoding="utf-8")


def test_nothing_but_the_mslearn_flag_uses_the_network(
    vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a, **_k):
        raise AssertionError("the network was used")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)
    raw = tmp_path / "t.json"
    raw.write_text(json.dumps(transcript()), encoding="utf-8")
    html = _export(tmp_path, row("Learn Things"))
    for argv in (
        ["import", str(raw), "--apply"],
        ["import", str(html), "--apply"],
        ["list"],
        ["lookup", "learn"],
        ["stats"],
        ["summarize", "--missing"],
    ):
        assert main(["learning", *argv]) == 0, argv


def test_list_lookup_and_stats(
    vault: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = _export(tmp_path, row("Learn Azure Things", duration="2h"), row("Angular Signals"))
    main(["learning", "import", str(export), "--apply"])
    capsys.readouterr()

    main(["learning", "list", "--topic", "Angular"])
    assert "Angular Signals" in capsys.readouterr().out

    assert main(["learning", "lookup", "azure things"]) == 0
    assert "Learn Azure Things" in capsys.readouterr().out
    assert main(["learning", "lookup", "no such course"]) == 1

    main(["learning", "stats"])
    out = capsys.readouterr().out
    assert "completed items" in out and "Microsoft Azure" in out


def test_summaries_are_added_but_never_overwritten(vault: Path, tmp_path: Path) -> None:
    raw = tmp_path / "t.json"
    raw.write_text(json.dumps(transcript(modules=1, paths=0)), encoding="utf-8")
    html = _export(tmp_path, row("Learn Things"))
    main(["learning", "import", str(raw), "--apply"])
    main(["learning", "import", str(html), "--apply"])
    items = {i.id: i for i in _items(vault)}
    mine = "pluralsight:learn-things"
    theirs = "mslearn:learn.example.module-0"
    notes = tmp_path / "notes.json"
    notes.write_text(
        json.dumps({mine: "my paraphrase", theirs: "should not win"}), encoding="utf-8"
    )
    assert main(["learning", "summarize", "--missing", "--from-json", str(notes)]) == 0
    after = {i.id: i for i in _items(vault)}
    assert (
        after[mine].summary == "my paraphrase" and after[mine].summary_source.value == "generated"
    )
    assert after[theirs].summary == items[theirs].summary  # the provider's text stays
    notes.write_text(json.dumps({"pluralsight:nope": "x"}), encoding="utf-8")
    assert main(["learning", "summarize", "--missing", "--from-json", str(notes)]) == 1


def test_set_url_saves_a_confirmed_link_only(vault: Path, tmp_path: Path) -> None:
    main(["learning", "import", str(_export(tmp_path, row("Learn Things"))), "--apply"])
    item_id = "pluralsight:learn-things"
    assert main(["learning", "set-url", item_id, "http://insecure.example.com"]) == 1
    assert main(["learning", "set-url", "pluralsight:nope", "https://example.com/x"]) == 1
    assert main(["learning", "set-url", item_id, "https://example.com/x"]) == 0
    assert next(i for i in _items(vault) if i.id == item_id).url == "https://example.com/x"


def _import_file(tmp_path: Path, *entries: dict[str, object]) -> Path:
    path = tmp_path / "pluralsight_import.json"
    path.write_text(
        json.dumps(
            {"format": "jobomatic-pluralsight-history", "version": 1, "entries": list(entries)}
        ),
        encoding="utf-8",
    )
    return path


def _json_entry(name: str, percent: str = "100.0%") -> dict[str, object]:
    return {
        "name": name,
        "type": "Course",
        "url": f"https://app.pluralsight.com/library/courses/{name.lower().replace(' ', '-')}",
        "duration": "1h 30m",
        "completion_percentage": percent,
        "completed_on": "2026-11-08",
    }


def test_an_import_file_is_read_as_pluralsight_and_a_rerun_is_quiet(
    vault: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = _import_file(tmp_path, _json_entry("Learn Azure Things"), _json_entry("Half", "40.0%"))
    assert main(["learning", "import", str(export)]) == 0
    out = capsys.readouterr().out
    assert (
        "(pluralsight)" in out
        and "+ Learn Azure Things" in out
        and "Half" not in out.split("warning")[0]
    )
    assert _items(vault) == []  # a dry run saves nothing

    assert main(["learning", "import", str(export), "--apply"]) == 0
    assert [i.title for i in _items(vault)] == ["Learn Azure Things"]
    assert list((vault / "imports" / "pluralsight").glob("*.json"))
    capsys.readouterr()

    assert main(["learning", "import", str(export), "--apply"]) == 0
    assert "0 new, 0 changed" in capsys.readouterr().out


def test_an_unrecognised_json_file_is_refused_and_saves_nothing(
    vault: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "pluralsight_import.json"
    bad.write_text(json.dumps({"format": "jobomatic-pluralsight-history", "version": 9}), "utf-8")
    assert main(["learning", "import", str(bad), "--apply"]) == 1
    assert "Nothing was imported" in capsys.readouterr().out
    assert _items(vault) == []


def test_set_date_corrects_one_item_and_refuses_bad_input(vault: Path, tmp_path: Path) -> None:
    export = _export(tmp_path, row("Learn Azure Things", when="03-26-2026"), row("Other Course"))
    assert main(["learning", "import", str(export), "--apply"]) == 0
    item_id = next(i.id for i in _items(vault) if i.title == "Learn Azure Things")
    assert main(["learning", "set-date", item_id, "26/03/2026"]) == 1
    assert main(["learning", "set-date", item_id, "2999-01-01"]) == 1
    assert main(["learning", "set-date", "pluralsight:nope", "2026-10-05"]) == 1
    assert main(["learning", "set-date", item_id, "2026-10-05"]) == 0
    by_title = {i.title: i for i in _items(vault)}
    assert str(by_title["Learn Azure Things"].completed_on) == "2026-10-05"
    assert str(by_title["Other Course"].completed_on) == "2026-08-15"  # untouched
    # a later import never undoes the correction
    assert main(["learning", "import", str(export), "--apply"]) == 0
    assert (
        str({i.title: i for i in _items(vault)}["Learn Azure Things"].completed_on) == "2026-10-05"
    )
