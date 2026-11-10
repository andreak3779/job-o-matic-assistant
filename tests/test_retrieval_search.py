"""Searching the index end to end with a fake embedder (needs ``scoring`` to be written)."""

from __future__ import annotations

import pytest

from jobomatic.retrieval import service
from jobomatic.retrieval.adapters.sqlite_index import SqliteIndex
from tests.retrieval_fakes import FakeEmbedder, sample_chunks


@pytest.fixture
def store(tmp_path):
    index = SqliteIndex(tmp_path / "evidence.sqlite")
    service.build_index(sample_chunks(), FakeEmbedder(), index)
    return index


def test_the_relevant_chunk_ranks_first(store):
    hits = service.search(store, "slow database queries indexes", FakeEmbedder(), min_score=0.0)
    assert hits[0].chunk.id in {"course:0", "experience:j:0"}
    assert hits[0].score >= hits[-1].score


def test_nothing_above_the_cutoff_returns_nothing(store):
    assert service.search(store, "quantum chromodynamics", FakeEmbedder(), min_score=0.5) == []


def test_keyword_only_search_never_calls_the_embedder(store):
    embedder = FakeEmbedder()
    hits = service.search(store, "RabbitMQ", embedder, semantic=False, min_score=1e-9)
    assert embedder.calls == []
    assert [h.chunk.id for h in hits] == ["course:1"]


def test_kinds_filter(store):
    hits = service.search(
        store, "queries indexes", FakeEmbedder(), min_score=0.0, kinds=frozenset({"course"})
    )
    assert hits and all(h.chunk.kind == "course" for h in hits)


def test_search_of_an_empty_index_is_empty(tmp_path):
    empty = SqliteIndex(tmp_path / "none.sqlite")
    assert service.search(empty, "anything", FakeEmbedder(), min_score=0.0) == []


def test_gather_adds_a_rationale_only_when_asked(store):
    skills = [("slow queries indexes", "course"), ("quantum chromodynamics", "gap")]
    plain = service.gather(skills, store, FakeEmbedder(), min_score=0.4)
    assert plain[0].hits and plain[1].hits == []
    assert all(item.rationale is None for item in plain)

    explained = service.gather(
        skills,
        store,
        FakeEmbedder(),
        min_score=0.4,
        chat=lambda _p: "It covers query tuning [1].",
        pii_scan=lambda _t: [],
    )
    assert explained[0].rationale == "It covers query tuning [1]."
    assert explained[1].rationale is None
