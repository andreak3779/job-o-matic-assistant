"""The SQLite index: storing, nearest-neighbour search, incremental updates, a changed model."""

from __future__ import annotations

import sqlite3

import pytest

from jobomatic.retrieval.adapters.sqlite_index import SqliteIndex
from jobomatic.retrieval.model import Chunk, RetrievalError
from jobomatic.retrieval.ports import IndexEntry


def _entry(chunk_id: str, vector, kind="course", text="t", title="T", **extra) -> IndexEntry:
    chunk = Chunk(chunk_id, kind, title, text, **extra)
    return IndexEntry(chunk, f"hash-{text}", vector)


@pytest.fixture
def store(tmp_path):
    return SqliteIndex(tmp_path / "index" / "evidence.sqlite")


def _fill(store: SqliteIndex) -> None:
    store.apply(
        [
            _entry("a", [1.0, 0.0, 0.0], text="alpha"),
            _entry("b", [0.0, 1.0, 0.0], kind="project", text="beta"),
            _entry("c", [0.6, 0.8, 0.0], text="gamma", local_only=True),
        ],
        [],
        model="m1",
        dimensions=3,
        reset=False,
    )


def test_an_index_that_does_not_exist_is_empty_and_not_created(store):
    assert store.fingerprint() is None
    assert store.hashes() == {}
    assert store.chunks() == []
    assert store.nearest([1.0, 0.0, 0.0], limit=5) == []
    assert not store.path.exists()


def test_apply_stores_chunks_hashes_and_fingerprint(store):
    _fill(store)
    assert store.fingerprint() == ("m1", 3)
    assert store.hashes() == {"a": "hash-alpha", "b": "hash-beta", "c": "hash-gamma"}
    assert [c.id for c in store.chunks()] == ["a", "b", "c"]
    assert [c.id for c in store.chunks(frozenset({"project"}))] == ["b"]
    assert next(c for c in store.chunks() if c.id == "c").local_only is True


def test_nearest_returns_cosine_similarity_best_first(store):
    _fill(store)
    found = store.nearest([1.0, 0.0, 0.0], limit=3)
    assert [c.id for c, _ in found] == ["a", "c", "b"]
    assert found[0][1] == pytest.approx(1.0, abs=1e-6)
    assert found[1][1] == pytest.approx(0.6, abs=1e-6)
    assert found[2][1] == pytest.approx(0.0, abs=1e-6)


def test_nearest_respects_limit_and_kinds(store):
    _fill(store)
    assert len(store.nearest([1.0, 0.0, 0.0], limit=2)) == 2
    only_project = store.nearest([1.0, 0.0, 0.0], limit=3, kinds=frozenset({"project"}))
    assert [c.id for c, _ in only_project] == ["b"]


def test_a_vectorless_entry_keeps_the_stored_vector_but_updates_metadata(store):
    _fill(store)
    store.apply(
        [
            IndexEntry(
                Chunk("a", "course", "Renamed", "alpha", status="complete"), "hash-alpha", None
            )
        ],
        [],
        model="m1",
        dimensions=3,
        reset=False,
    )
    top = store.nearest([1.0, 0.0, 0.0], limit=1)[0]
    assert top[0].title == "Renamed" and top[0].status == "complete"
    assert top[1] == pytest.approx(1.0, abs=1e-6)


def test_a_new_vector_replaces_the_old_one(store):
    _fill(store)
    store.apply(
        [_entry("a", [0.0, 0.0, 1.0], text="alpha two")], [], model="m1", dimensions=3, reset=False
    )
    assert store.nearest([0.0, 0.0, 1.0], limit=1)[0][0].id == "a"
    assert store.hashes()["a"] == "hash-alpha two"


def test_remove_drops_chunks_and_vectors(store):
    _fill(store)
    store.apply([], ["b"], model="m1", dimensions=3, reset=False)
    assert [c.id for c in store.chunks()] == ["a", "c"]
    assert "b" not in [c.id for c, _ in store.nearest([0.0, 1.0, 0.0], limit=5)]


def test_reset_starts_again_with_the_new_vector_size(store):
    _fill(store)
    store.apply([_entry("z", [1.0, 0.0], text="zed")], [], model="m2", dimensions=2, reset=True)
    assert store.fingerprint() == ("m2", 2)
    assert [c.id for c in store.chunks()] == ["z"]


def test_a_new_chunk_without_a_vector_is_an_error_and_changes_nothing(store):
    _fill(store)
    with pytest.raises(RetrievalError, match="no vector"):
        store.apply(
            [IndexEntry(Chunk("n", "course", "N", "n"), "h", None)],
            ["a"],
            model="m1",
            dimensions=3,
            reset=False,
        )
    assert "a" in store.hashes() and "n" not in store.hashes()  # rolled back as a whole


def test_the_keyword_table_is_kept_in_step(store):
    _fill(store)
    with sqlite3.connect(store.path) as conn:
        rows = conn.execute(
            "select rowid from chunks_fts where chunks_fts match 'gamma'"
        ).fetchall()
    assert len(rows) == 1
