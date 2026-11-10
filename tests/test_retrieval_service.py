"""Building the index incrementally, and the optional rationale.

``search``/``gather`` need the scoring function; those tests are in test_retrieval_search.py.
"""

from __future__ import annotations

import math

import pytest

from jobomatic.retrieval import service
from jobomatic.retrieval.adapters.sqlite_index import SqliteIndex
from jobomatic.retrieval.model import Chunk, Hit, RetrievalError
from tests.retrieval_fakes import FakeEmbedder, sample_chunks


@pytest.fixture
def store(tmp_path):
    return SqliteIndex(tmp_path / "evidence.sqlite")


def test_first_build_embeds_everything(store):
    embedder = FakeEmbedder()
    report = service.build_index(sample_chunks(), embedder, store)
    assert (report.added, report.updated, report.removed, report.unchanged) == (4, 0, 0, 0)
    assert embedder.calls == [(4, False)]
    assert not report.rebuilt and report.embedded == 4 and report.total == 4


def test_second_build_embeds_nothing(store):
    service.build_index(sample_chunks(), FakeEmbedder(), store)
    embedder = FakeEmbedder()
    report = service.build_index(sample_chunks(), embedder, store)
    assert embedder.calls == []
    assert (report.added, report.updated, report.unchanged) == (0, 0, 4)


def test_only_changed_text_is_re_embedded_and_removed_chunks_go(store):
    service.build_index(sample_chunks(), FakeEmbedder(), store)
    chunks = sample_chunks()
    chunks[1] = Chunk("course:1", "course", "RabbitMQ by Example", "RabbitMQ by Example. New.")
    chunks.pop()  # the experience bullet is gone
    chunks.append(Chunk("course:9", "course", "Terraform", "Terraform. Provisioning."))
    embedder = FakeEmbedder()
    report = service.build_index(chunks, embedder, store)
    assert embedder.calls == [(2, False)]
    assert (report.added, report.updated, report.removed, report.unchanged) == (1, 1, 1, 2)
    assert set(store.hashes()) == {"course:0", "course:1", "project:p", "course:9"}


def test_changing_only_metadata_keeps_the_vector(store):
    service.build_index(sample_chunks(), FakeEmbedder(), store)
    chunks = sample_chunks()
    chunks[0] = Chunk(
        chunks[0].id, "course", chunks[0].title, chunks[0].text, status="complete", url="https://x"
    )
    embedder = FakeEmbedder()
    service.build_index(chunks, embedder, store)
    assert embedder.calls == []
    assert next(c for c in store.chunks() if c.id == "course:0").url == "https://x"


def test_a_different_embedding_model_rebuilds_everything(store):
    service.build_index(sample_chunks(), FakeEmbedder("old"), store)
    embedder = FakeEmbedder("new")
    report = service.build_index(sample_chunks(), embedder, store)
    assert report.rebuilt and embedder.calls == [(4, False)]
    assert store.fingerprint() == ("new", 64)


def test_stored_vectors_are_unit_length(store):
    service.build_index(sample_chunks(), FakeEmbedder(), store)
    for _chunk, similarity in store.nearest(service.normalize([1.0] * 64), limit=4):
        assert -1.0 <= similarity <= 1.0
    assert math.isclose(sum(x * x for x in service.normalize([3.0, 4.0])), 1.0)


def test_repeated_chunk_ids_are_rejected(store):
    chunks = sample_chunks()
    chunks.append(chunks[0])
    with pytest.raises(RetrievalError, match="unique"):
        service.build_index(chunks, FakeEmbedder(), store)


# ── rationale ────────────────────────────────────────────────────────────────


def _hits() -> list[Hit]:
    return [Hit(c, 0.9, 0.9, 0.0) for c in sample_chunks()]


def _no_pii(_text: str) -> list[str]:
    return []


def test_cloud_safe_hits_exclude_private_prose():
    assert all(not h.chunk.local_only for h in service.cloud_safe_hits(_hits()))
    assert len(service.cloud_safe_hits(_hits())) == 3


def test_explain_sends_only_cloud_safe_text_and_accepts_valid_citations():
    seen: list[str] = []

    def chat(prompt):
        seen.append(prompt)
        return "The course covers query tuning [1]."

    rationale, note = service.explain("tuning queries", _hits(), chat, _no_pii)
    assert rationale == "The course covers query tuning [1]." and note is None
    assert "Reduced database query time" not in seen[0]  # the resume bullet never leaves
    assert "Understanding Query Optimization" in seen[0]
    assert "(course, complete)" in seen[0]
    assert "never as work experience" in seen[0]


@pytest.mark.parametrize(
    ("reply", "fragment"),
    [("Covers it fully.", "cited no evidence"), ("Covers it [9].", "not provided")],
)
def test_explain_discards_ungrounded_replies(reply, fragment):
    rationale, note = service.explain("x", _hits(), lambda _p: reply, _no_pii)
    assert rationale is None and fragment in note


def test_explain_accepts_no_direct_evidence():
    rationale, note = service.explain("x", _hits(), lambda _p: "No direct evidence.", _no_pii)
    assert rationale == "No direct evidence." and note is None


def test_explain_reports_service_errors():
    def boom(_prompt):
        raise RetrievalError("unauthorized")

    rationale, note = service.explain("x", _hits(), boom, _no_pii)
    assert rationale is None and "unauthorized" in note


def test_explain_blocks_prompts_the_scan_flags():
    called: list[str] = []
    rationale, note = service.explain(
        "x", _hits(), lambda p: called.append(p) or "ok [1]", lambda _t: ["email"]
    )
    assert rationale is None and "personal-data" in note and called == []


def test_explain_with_only_private_hits_does_nothing():
    local = [h for h in _hits() if h.chunk.local_only]
    called: list[str] = []
    rationale, note = service.explain("x", local, lambda p: called.append(p) or "", _no_pii)
    assert rationale is None and "no cloud-safe" in note and called == []


def test_render_markdown_shows_hits_status_and_empty_results():
    from jobomatic.retrieval.model import SkillEvidence

    text = service.render_markdown(
        [
            SkillEvidence("slow queries", "course", hits=_hits()[:1]),
            SkillEvidence("quantum chromodynamics", "gap"),
        ]
    )
    assert "fit engine: course" in text
    assert "(course, complete; score 0.90)" in text
    assert "No evidence found above the score cutoff." in text
    assert "not changed by this list" in text
