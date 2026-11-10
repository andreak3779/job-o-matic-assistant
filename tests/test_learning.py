"""The learning module: matching imports by id, the YAML store, topic rules and both importers."""

from __future__ import annotations

import datetime as dt
import json
import socket
import urllib.request
from pathlib import Path

import pytest

from jobomatic.learning.adapters.mslearn_transcript import (
    MsLearnTranscriptSource,
    fetch_transcript,
    parse_transcript,
    sanitize,
)
from jobomatic.learning.adapters.pluralsight_html import PluralsightHtmlSource
from jobomatic.learning.adapters.pluralsight_json import (
    FORMAT,
    PluralsightJsonSource,
    looks_like_pluralsight_history,
)
from jobomatic.learning.adapters.yaml_store import (
    FileImportArchive,
    YamlLearningStore,
    load_topic_rules,
)
from jobomatic.learning.model import (
    Kind,
    Provider,
    SourceBatch,
    SummarySource,
    TopicRule,
    TopicRules,
    hours_text,
)
from jobomatic.learning.service import LearningError, plan_import, run_import, stats
from tests.learning_fixtures import item, page, row, transcript


def _batch(*items) -> SourceBatch:
    return SourceBatch("test", list(items))


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """No learning test may reach the network, whatever the code under test does."""

    def refuse(*_args, **_kwargs):
        raise AssertionError("a test tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)


# -- matching by id -------------------------------------------------------------------------


def test_a_new_id_with_a_different_title_is_a_new_item() -> None:
    stored = [item("intro-to-sql", title="Intro to SQL")]
    plan = plan_import(_batch(item("advanced-sql", title="Advanced SQL")), stored)
    assert [i.id for i in plan.new] == ["pluralsight:advanced-sql"]
    assert plan.rekeyed == [] and plan.unchanged == 0
    assert plan.absent == ["pluralsight:intro-to-sql"]


def test_the_same_id_with_a_new_title_is_a_change_not_a_new_item() -> None:
    stored = [item("intro-to-sql", title="Intro to SQL")]
    plan = plan_import(_batch(item("intro-to-sql", title="Introduction to SQL")), stored)
    assert plan.new == []
    [change] = plan.changed
    assert [(f.name, f.old, f.new) for f in change.fields] == [
        ("title", "Intro to SQL", "Introduction to SQL")
    ]
    assert plan.merged[0].title == "Introduction to SQL"


def test_a_changed_id_with_the_same_title_and_kind_is_rekeyed_not_duplicated() -> None:
    stored = [
        item("old-link", title="Becoming a Better Communicator", completed=dt.date(2026, 1, 2))
    ]
    incoming = item(
        "new-link", title="Becoming  a better communicator", completed=dt.date(2026, 9, 9)
    )
    plan = plan_import(_batch(incoming), stored)
    assert plan.new == [] and plan.absent == []
    [r] = plan.rekeyed
    assert (r.old_id, r.new_id) == ("pluralsight:old-link", "pluralsight:new-link")
    [only] = plan.merged
    assert only.id == "pluralsight:new-link" and only.completed_on == dt.date(2026, 1, 2)
    assert only.url == "https://example.com/new-link"
    assert plan.has_changes
    again = plan_import(_batch(incoming), plan.merged)
    assert not again.has_changes


def test_rekeying_needs_the_same_provider_kind_and_an_id_not_in_the_import() -> None:
    lab = item("a-lab", title="Same Title", kind=Kind.LAB)
    plan = plan_import(_batch(item("a-course", title="Same Title")), [lab])
    assert [i.id for i in plan.new] == ["pluralsight:a-course"] and plan.rekeyed == []
    both = plan_import(
        _batch(item("x", title="Same Title"), item("old", title="Same Title")),
        [item("old", title="Same Title")],
    )
    assert both.rekeyed == [] and [i.id for i in both.new] == ["pluralsight:x"]


def test_a_second_import_of_the_same_batch_reports_nothing() -> None:
    first = plan_import(_batch(item("a"), item("b")), [])
    again = plan_import(_batch(item("a"), item("b")), first.merged)
    assert not again.has_changes and again.unchanged == 2


def test_a_stored_completion_date_and_topics_are_kept() -> None:
    stored = [item("a", completed=dt.date(2026, 1, 2), topics=["Python 3"])]
    incoming = item("a", completed=dt.date(2026, 9, 9), topics=["Angular"])
    plan = plan_import(_batch(incoming), stored)
    assert not plan.has_changes
    assert plan.merged[0].completed_on == dt.date(2026, 1, 2)
    assert plan.merged[0].topics == ["Python 3"]


def test_a_missing_date_is_filled_in_from_the_import() -> None:
    stored = [item("a", completed=None)]
    plan = plan_import(_batch(item("a", completed=dt.date(2026, 3, 4))), stored)
    assert plan.merged[0].completed_on == dt.date(2026, 3, 4)


def test_hand_and_llm_summaries_survive_but_provider_summaries_refresh() -> None:
    mine = item("a", summary="my words", summary_source=SummarySource.MANUAL)
    theirs = item("b", summary="old text", summary_source=SummarySource.PROVIDER)
    new = SummarySource.PROVIDER
    plan = plan_import(
        _batch(
            item("a", summary="provider text", summary_source=new),
            item("b", summary="new text", summary_source=new),
        ),
        [mine, theirs],
    )
    assert plan.merged[0].summary == "my words"
    assert plan.merged[1].summary == "new text"


def test_stored_items_missing_from_the_import_are_reported_and_kept() -> None:
    stored = [item("a"), item("b"), item("m", provider=Provider.MSLEARN, kind=Kind.MODULE)]
    plan = plan_import(_batch(item("a")), stored)
    assert plan.absent == ["pluralsight:b"]  # the other provider is not judged by this batch
    assert len(plan.merged) == 3


def test_an_id_twice_in_one_import_is_an_error() -> None:
    with pytest.raises(LearningError, match="appears twice"):
        plan_import(_batch(item("a"), item("a")), [])


def test_new_items_get_topics_from_the_rules_and_unmatched_ones_are_reported() -> None:
    rules = TopicRules([TopicRule("Python 3", ("python",))])
    plan = plan_import(
        _batch(item("py", title="Python Basics"), item("zz", title="Quilting")), [], rules
    )
    assert plan.new[0].topics == ["Python 3"]
    assert plan.unclassified == ["pluralsight:zz"]


# -- totals ---------------------------------------------------------------------------------


def test_stats_do_not_count_a_learning_path_twice() -> None:
    module = item("m", provider=Provider.MSLEARN, kind=Kind.MODULE, minutes=60, topics=["Azure"])
    path = item(
        "p", provider=Provider.MSLEARN, kind=Kind.LEARNING_PATH, minutes=60, topics=["Azure"]
    )
    totals = stats([module, path, item("c", minutes=30)])
    assert totals.items == 3 and totals.minutes == 90
    assert totals.by_kind == {"module": 1, "learning_path": 1, "course": 1}
    assert totals.by_topic["Azure"].items == 2 and totals.by_topic["Azure"].minutes == 60
    assert totals.untopiced == 1


def test_hours_text() -> None:
    assert hours_text(3796) == "63 h 16 min"


# -- topic rules ----------------------------------------------------------------------------


def test_rules_match_whole_words_and_the_first_rule_wins() -> None:
    rules = TopicRules([TopicRule("Azure", ("azure",)), TopicRule("SQL", ("sql", "t-sql"))])
    assert rules.classify("Azure SQL Basics") == ["Azure"]
    assert rules.classify("Writing T-SQL") == ["SQL"]
    assert rules.classify("Intro to MySQL") == []
    assert rules.classify("Quilting") == []


def test_default_rules_cover_common_titles() -> None:
    rules = load_topic_rules()
    assert rules.classify("Getting Started with Azure Functions") == ["Microsoft Azure"]
    assert rules.classify("Angular Signals") == ["Angular"]
    assert rules.classify("Building Applications with Claude") == ["Claude"]
    assert rules.classify("Integrating Knowledge Bases for RAGs") == ["RAG & Retrieval"]
    assert rules.classify("Context Indexing and Retrieval") == ["RAG & Retrieval"]
    assert rules.classify("Generative AI Foundations - Agentic AI") == [
        "Generative AI & AI-Assisted Development"
    ]


def test_a_vault_can_replace_the_rules(tmp_path: Path) -> None:
    (tmp_path / "learning").mkdir()
    (tmp_path / "learning" / "topics.yaml").write_text(
        "topics:\n  - topic: Mine\n    keywords: [quilting]\n", encoding="utf-8"
    )
    rules = load_topic_rules(tmp_path)
    assert rules.classify("Quilting 101") == ["Mine"]
    assert rules.classify("Angular Signals") == []


# -- the YAML store and the archive ---------------------------------------------------------


def test_store_round_trip_and_missing_file_is_empty(tmp_path: Path) -> None:
    store = YamlLearningStore(tmp_path)
    assert store.load() == []
    items = [item("a", topics=["Python 3"], summary="s", summary_source=SummarySource.GENERATED)]
    store.save(items)
    assert store.load() == items
    assert "completed_on: 2026-08-15" in store.path.read_text(encoding="utf-8")


def test_store_rejects_duplicate_ids_unknown_keys_and_bad_values(tmp_path: Path) -> None:
    store = YamlLearningStore(tmp_path)
    store.save([item("a")])
    good = store.path.read_text(encoding="utf-8")
    store.path.write_text(good + good.replace("items:\n", ""), encoding="utf-8")
    with pytest.raises(LearningError, match="duplicate ids"):
        store.load()
    store.path.write_text(good.replace("title:", "titel:"), encoding="utf-8")
    with pytest.raises(LearningError, match=r"items\[0\]"):
        store.load()
    store.path.write_text("items: [", encoding="utf-8")
    with pytest.raises(LearningError, match="not valid YAML"):
        store.load()


def test_archive_keeps_each_distinct_export_and_not_repeats(tmp_path: Path) -> None:
    raw = tmp_path / "export.html"
    raw.write_text("one", encoding="utf-8")
    archive = FileImportArchive(tmp_path / "imports", today=dt.date(2026, 10, 31))
    first = archive.store("pluralsight", raw)
    assert first == tmp_path / "imports" / "pluralsight" / "2026-10-31.html"
    assert archive.store("pluralsight", raw) == first
    raw.write_text("two", encoding="utf-8")
    assert archive.store("pluralsight", raw).name == "2026-10-31-2.html"


# -- Pluralsight page -----------------------------------------------------------------------


def _read_html(tmp_path: Path, rows: list[str]) -> SourceBatch:
    path = tmp_path / "export.html"
    path.write_text(page(rows), encoding="utf-8")
    return PluralsightHtmlSource(path).read()


def test_pluralsight_reads_only_completed_rows(tmp_path: Path) -> None:
    batch = _read_html(
        tmp_path,
        [
            row("Learn Things", duration="1h 29m", when="10-15-2026"),
            row("Half Done", percent="42.0%"),
            row("A Lab", entry_type="Lab", duration="45m", href="/hands-on/labs/a-lab"),
        ],
    )
    by_title = {i.title: i for i in batch.items}
    assert "Half Done" not in by_title
    learn = by_title["Learn Things"]
    assert learn.id == "pluralsight:learn-things"  # the shared /library/courses/ prefix is dropped
    assert (learn.kind, learn.duration_minutes) == (Kind.COURSE, 89)
    assert learn.completed_on == dt.date(2026, 10, 15)
    lab = by_title["A Lab"]
    assert (lab.kind, lab.id) == (Kind.LAB, "pluralsight:hands-on/labs/a-lab")
    assert any("not at 100%" in w for w in batch.warnings)


def test_pluralsight_warns_about_a_completed_row_without_a_date(tmp_path: Path) -> None:
    batch = _read_html(tmp_path, [row("No Date", when=None)])
    assert any("no date" in w for w in batch.warnings)
    assert next(i for i in batch.items if i.title == "No Date").completed_on is None


def test_pluralsight_refuses_a_page_it_does_not_recognise(tmp_path: Path) -> None:
    path = tmp_path / "export.html"
    path.write_text("<html><body><p>Nothing here</p></body></html>", encoding="utf-8")
    with pytest.raises(LearningError, match="Nothing was imported") as info:
        PluralsightHtmlSource(path).read()
    assert "export.html" in str(info.value)


def test_pluralsight_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(LearningError, match="cannot read"):
        PluralsightHtmlSource(tmp_path / "nope.html").read()


# -- Pluralsight import file (JSON) ---------------------------------------------------------


def _entry(name: str, **extra: object) -> dict[str, object]:
    slug = name.lower().replace(" ", "-")
    entry: dict[str, object] = {
        "name": name,
        "type": "Course",
        "url": f"https://app.pluralsight.com/library/courses/{slug}",
        "duration": "1h 29m",
        "completion_percentage": "100.0%",
        "completed_date": "Oct 15, 2026",
        "completed_on": "2026-10-15",
    }
    entry.update(extra)
    return entry


def _wrap(*entries: dict[str, object], **top: object) -> dict[str, object]:
    return {
        "format": FORMAT,
        "version": 1,
        "generated_on": "2026-11-10",
        "entries": list(entries),
        **top,
    }


def _read_json(tmp_path: Path, data: object) -> SourceBatch:
    path = tmp_path / "import.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return PluralsightJsonSource(path).read()


def test_json_reads_only_completed_entries_and_matches_the_html_reader(tmp_path: Path) -> None:
    batch = _read_json(
        tmp_path,
        _wrap(
            _entry("Learn Things"),
            _entry("Half Done", completion_percentage="42.0%"),
            _entry(
                "A Lab",
                type="Lab",
                duration="45m",
                url="https://app.pluralsight.com/hands-on/labs/a-lab",
            ),
        ),
    )
    by_title = {i.title: i for i in batch.items}
    assert "Half Done" not in by_title
    learn = by_title["Learn Things"]
    assert learn.id == "pluralsight:learn-things"  # the same id the HTML reader gives
    assert (learn.kind, learn.duration_minutes) == (Kind.COURSE, 89)
    assert learn.completed_on == dt.date(2026, 10, 15)
    lab = by_title["A Lab"]
    assert (lab.kind, lab.id, lab.duration_minutes) == (
        Kind.LAB,
        "pluralsight:hands-on/labs/a-lab",
        45,
    )
    assert any("not at 100%" in w for w in batch.warnings)
    assert not any("bare list" in w for w in batch.warnings)


def test_json_falls_back_to_the_displayed_date_and_warns_when_there_is_none(tmp_path: Path) -> None:
    batch = _read_json(
        tmp_path,
        _wrap(
            _entry("Shown Date", completed_on=None, completed_date="Nov 08, 2026"),
            _entry("No Date", completed_on=None, completed_date=None),
        ),
    )
    by_title = {i.title: i for i in batch.items}
    assert by_title["Shown Date"].completed_on == dt.date(2026, 11, 8)
    assert by_title["No Date"].completed_on is None
    assert any("No Date" in w and "no date" in w for w in batch.warnings)


def test_json_bare_list_from_the_old_template_still_imports_with_a_warning(tmp_path: Path) -> None:
    old = [{k: v for k, v in _entry("Old Shape").items() if k != "completed_on"}]
    batch = _read_json(tmp_path, old)
    assert [i.title for i in batch.items] == ["Old Shape"]
    assert batch.items[0].completed_on == dt.date(2026, 10, 15)
    assert any("bare list" in w for w in batch.warnings)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"format": "something-else", "entries": []}, "not a Pluralsight import file"),
        (_wrap(_entry("X"), version=2), "version 2"),
        (_wrap(), "no entries"),
        ({"format": FORMAT, "version": 1, "entries": "nope"}, "expected a list"),
        (_wrap({"name": "No Link"}), "missing"),
        (_wrap("not an object"), "not an object"),
        (_wrap(_entry("Odd", type="Webinar")), "type 'webinar'"),
    ],
)
def test_json_refuses_a_file_it_does_not_recognise(
    tmp_path: Path, data: object, message: str
) -> None:
    with pytest.raises(LearningError, match=message):
        _read_json(tmp_path, data)


def test_json_unreadable_or_missing_file_is_an_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(LearningError, match="not readable JSON"):
        PluralsightJsonSource(bad).read()
    with pytest.raises(LearningError, match="cannot read"):
        PluralsightJsonSource(tmp_path / "nope.json").read()


def test_a_completed_entry_with_no_link_has_no_id(tmp_path: Path) -> None:
    with pytest.raises(LearningError, match="no stable id"):
        _read_json(tmp_path, _wrap(_entry("Linkless", url=None)))


def test_json_is_told_apart_from_a_learn_transcript() -> None:
    assert looks_like_pluralsight_history(_wrap(_entry("A")))
    assert looks_like_pluralsight_history([_entry("A")])
    assert not looks_like_pluralsight_history(transcript())
    assert not looks_like_pluralsight_history([])


# -- Microsoft Learn transcript -------------------------------------------------------------


def test_transcript_maps_modules_paths_and_credentials() -> None:
    batch = parse_transcript(transcript(modules=2, paths=1), "t.json")
    modules = [i for i in batch.items if i.kind is Kind.MODULE]
    [path] = [i for i in batch.items if i.kind is Kind.LEARNING_PATH]
    assert modules[0].id == "mslearn:learn.example.module-0"
    assert modules[0].url == "https://learn.microsoft.com/training/modules/module-0/"
    assert modules[0].summary == "Learn how to do a thing with care."
    assert modules[0].summary_source is SummarySource.PROVIDER
    assert modules[0].completed_on == dt.date(2026, 4, 20)
    assert path.url is None
    assert {(c.kind, c.code) for c in batch.credentials} == {
        ("certification", None),
        ("exam", "EX-100"),
        ("applied_skill", None),
    }
    assert batch.warnings == []


def test_transcript_totals_that_disagree_are_a_warning() -> None:
    data = transcript()
    data["totalModulesCompleted"] = 5
    assert any("totalModulesCompleted" in w for w in parse_transcript(data, "t").warnings)


def test_a_changed_transcript_shape_fails_loudly() -> None:
    data = transcript()
    del data["modulesCompleted"][0]["uid"]
    with pytest.raises(LearningError, match="Nothing was imported"):
        parse_transcript(data, "t.json")
    with pytest.raises(LearningError, match="Microsoft may have changed it"):
        parse_transcript({"something": "else"}, "t.json")


def test_owner_fields_are_dropped_before_anything_is_saved() -> None:
    clean = sanitize(transcript())
    assert "userName" not in clean and "contactEmail" not in clean
    assert "Sarah Ashford" not in json.dumps(clean)
    assert clean["modulesCompleted"]


def test_reading_a_saved_transcript_never_touches_the_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a, **_k):
        raise AssertionError("network used")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)
    path = tmp_path / "t.json"
    path.write_text(json.dumps(sanitize(transcript())), encoding="utf-8")
    store = YamlLearningStore(tmp_path / "profile")
    run_import(MsLearnTranscriptSource(path), store, load_topic_rules(), apply=True)
    assert len(store.load()) == 3


def test_fetch_uses_the_share_id_and_validates_it() -> None:
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, *_):
            return json.dumps(transcript()).encode()

    def opener(request, timeout):
        seen["url"] = request.full_url
        return Response()

    data = fetch_transcript("abc-123_X", opener)
    assert seen["url"].endswith("/transcript/share/abc-123_X")
    assert "modulesCompleted" in data
    with pytest.raises(LearningError, match="unexpected characters"):
        fetch_transcript("../../etc", opener)


def test_fetch_failure_is_an_error() -> None:
    def opener(request, timeout):
        raise OSError("offline")

    with pytest.raises(LearningError, match="could not fetch"):
        fetch_transcript("abc", opener)


# -- the use case ---------------------------------------------------------------------------


def test_import_writes_only_when_applied_and_a_rerun_is_quiet(tmp_path: Path) -> None:
    html = tmp_path / "export.html"
    html.write_text(page([row("Learn Things")]), encoding="utf-8")
    store = YamlLearningStore(tmp_path / "profile")
    rules = load_topic_rules()

    _, dry = run_import(PluralsightHtmlSource(html), store, rules, apply=False)
    assert dry.has_changes and store.load() == []

    _, applied = run_import(PluralsightHtmlSource(html), store, rules, apply=True)
    assert len(store.load()) == len(applied.new)

    _, again = run_import(PluralsightHtmlSource(html), store, rules, apply=True)
    assert not again.has_changes


# -- learning-path pages ---------------------------------------------------------------------

_PAGE = Path(__file__).parent / "fixtures" / "mslearn-path-page.html"


def _path_and_modules():
    from jobomatic.learning.model import LearningItem

    path = item("learn.example.path-0", provider=Provider.MSLEARN, kind=Kind.LEARNING_PATH)
    path = path.model_copy(update={"url": None})
    modules = [
        item(f"learn.example.module-{n}", provider=Provider.MSLEARN, kind=Kind.MODULE).model_copy(
            update={"url": f"https://learn.microsoft.com/training/modules/module-{n}/"}
        )
        for n in range(3)
    ]
    assert isinstance(path, LearningItem)
    return [path, *modules]


def _enricher(tmp_path: Path, pages: dict[str, str | None]):
    from jobomatic.learning.adapters.mslearn_page import MsLearnPageEnricher

    asked: list[str] = []

    def fetch(url: str) -> str | None:
        asked.append(url)
        return pages.get(url)

    return MsLearnPageEnricher(tmp_path / "pages", fetch, pause=0), asked


def test_a_path_page_gives_the_link_and_ties_its_modules_to_it(tmp_path: Path) -> None:
    from jobomatic.learning.service import enrich_paths

    url = "https://learn.microsoft.com/en-us/training/paths/path-0/"
    enricher, asked = _enricher(tmp_path, {url: _PAGE.read_text(encoding="utf-8")})
    result = enrich_paths(_path_and_modules(), enricher)
    by_id = {i.id: i for i in result.items}
    path = by_id["mslearn:learn.example.path-0"]
    assert path.url == "https://learn.microsoft.com/training/paths/path-0/"
    assert by_id["mslearn:learn.example.module-0"].parent_id == path.id
    assert by_id["mslearn:learn.example.module-1"].parent_id == path.id
    assert by_id["mslearn:learn.example.module-2"].parent_id is None  # not on the page
    assert result.parented_modules == 2
    assert result.modules_without_parent == ["mslearn:learn.example.module-2"]
    assert asked == [url]


def test_pages_are_cached_so_a_second_run_asks_nobody(tmp_path: Path) -> None:
    from jobomatic.learning.service import enrich_paths

    url = "https://learn.microsoft.com/en-us/training/paths/path-0/"
    enricher, asked = _enricher(tmp_path, {url: _PAGE.read_text(encoding="utf-8")})
    enrich_paths(_path_and_modules(), enricher)
    again, asked_again = _enricher(tmp_path, {})
    result = enrich_paths(_path_and_modules(), again)
    assert asked_again == [] and result.linked_paths


def test_a_page_for_a_different_path_is_never_accepted(tmp_path: Path) -> None:
    from jobomatic.learning.service import enrich_paths

    url = "https://learn.microsoft.com/en-us/training/paths/path-0/"
    other = _PAGE.read_text(encoding="utf-8").replace("learn.example.path-0", "learn.example.other")
    enricher, _ = _enricher(tmp_path, {url: other})
    result = enrich_paths(_path_and_modules(), enricher)
    assert result.unresolved_paths == ["mslearn:learn.example.path-0"]
    assert all(i.parent_id is None and (i.url or "").find("/paths/") < 0 for i in result.items)


def test_a_missing_page_is_reported_not_guessed(tmp_path: Path) -> None:
    from jobomatic.learning.service import enrich_paths

    enricher, _ = _enricher(tmp_path, {})
    result = enrich_paths(_path_and_modules(), enricher)
    assert result.unresolved_paths and not result.linked_paths


def test_a_module_in_two_paths_keeps_the_first_and_is_reported(tmp_path: Path) -> None:
    from jobomatic.learning.service import enrich_paths

    items = _path_and_modules()
    second = item("learn.example.path-1", provider=Provider.MSLEARN, kind=Kind.LEARNING_PATH)
    page = _PAGE.read_text(encoding="utf-8")
    pages = {
        "https://learn.microsoft.com/en-us/training/paths/path-0/": page,
        "https://learn.microsoft.com/en-us/training/paths/path-1/": page.replace(
            "learn.example.path-0", "learn.example.path-1"
        ),
    }
    enricher, _ = _enricher(tmp_path, pages)
    result = enrich_paths([*items, second], enricher)
    by_id = {i.id: i for i in result.items}
    assert by_id["mslearn:learn.example.module-0"].parent_id == "mslearn:learn.example.path-0"
    assert len(result.conflicts) == 2
