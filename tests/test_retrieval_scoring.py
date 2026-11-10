"""The contract for ``jobomatic.retrieval.scoring`` (the module the author writes).

These tests describe behaviour, not an implementation: any function that meets the spec in the
module docstring passes them.
"""

from __future__ import annotations

import pytest

from jobomatic.retrieval import scoring
from jobomatic.retrieval.model import Chunk


def _chunk(chunk_id: str, text: str, kind: str = "course") -> Chunk:
    return Chunk(chunk_id, kind, chunk_id, text)


# ── tokens ───────────────────────────────────────────────────────────────────


def test_tokens_lowercase_drop_filler_and_fold_plurals():
    assert scoring.tokens("Experience with SQL Queries and Indexes") == {"sql", "query", "index"}


def test_tokens_keep_language_and_framework_names_whole():
    assert {"c#", "c++", "asp.net"} <= scoring.tokens("C#, C++ and ASP.NET")


def test_tokens_keep_a_leading_dot_but_drop_a_sentence_ending_dot():
    found = scoring.tokens("Built on .NET and Node.js. Used ASP.NET.")
    assert {".net", "node.js", "asp.net"} <= found
    assert "net" not in found and "node.j" not in found


def test_tokens_ignore_words_made_only_of_dots():
    assert scoring.tokens("... . ..") == set()


def test_tokens_of_nothing_is_empty():
    assert scoring.tokens("") == set()
    assert scoring.tokens("the and with") == set()


# ── keyword_score ────────────────────────────────────────────────────────────


def test_keyword_score_is_the_share_of_query_terms_found():
    assert (
        scoring.keyword_score(scoring.tokens("sql queries"), scoring.tokens("SQL query tuning"))
        == 1.0
    )
    assert (
        scoring.keyword_score(scoring.tokens("sql kafka"), scoring.tokens("SQL query tuning"))
        == 0.5
    )
    assert scoring.keyword_score({"x"}, {"y"}) == 0.0


def test_keyword_score_of_an_empty_query_is_zero():
    assert scoring.keyword_score(set(), {"a"}) == 0.0


# ── rank ─────────────────────────────────────────────────────────────────────


def test_rank_combines_similarity_and_weighted_keyword_overlap():
    hits = scoring.rank(
        "sql queries",
        [(_chunk("a", "SQL query tuning"), 0.50)],
        k=3,
        min_score=0.0,
        keyword_weight=0.2,
    )
    assert len(hits) == 1
    assert hits[0].semantic == pytest.approx(0.50)
    assert hits[0].keyword == pytest.approx(1.0)
    assert hits[0].score == pytest.approx(0.50 + 0.2 * 1.0)


def test_rank_orders_best_first_and_keeps_at_most_k():
    candidates = [
        (_chunk("low", "unrelated words"), 0.40),
        (_chunk("high", "unrelated words"), 0.90),
        (_chunk("mid", "unrelated words"), 0.60),
    ]
    hits = scoring.rank("zzz", candidates, k=2, min_score=0.0, keyword_weight=0.15)
    assert [h.chunk.id for h in hits] == ["high", "mid"]


def test_a_keyword_match_can_lift_a_slightly_less_similar_chunk():
    candidates = [
        (_chunk("close", "nothing in common"), 0.70),
        (_chunk("literal", "rabbitmq routing"), 0.65),
    ]
    hits = scoring.rank("rabbitmq", candidates, k=2, min_score=0.0, keyword_weight=0.15)
    assert [h.chunk.id for h in hits] == ["literal", "close"]


def test_rank_drops_everything_under_the_cutoff_so_empty_means_no_evidence():
    candidates = [(_chunk("a", "words"), 0.30), (_chunk("b", "words"), 0.59)]
    assert scoring.rank("zzz", candidates, k=3, min_score=0.60, keyword_weight=0.15) == []


def test_a_score_exactly_at_the_cutoff_is_kept():
    hits = scoring.rank("zzz", [(_chunk("a", "words"), 0.60)], k=3, min_score=0.60)
    assert [h.chunk.id for h in hits] == ["a"]


def test_keyword_only_mode_ignores_similarity():
    candidates = [
        (_chunk("sim", "nothing in common"), 0.99),
        (_chunk("word", "rabbitmq routing"), 0.0),
    ]
    hits = scoring.rank("rabbitmq", candidates, k=3, min_score=1e-9, semantic=False)
    assert [h.chunk.id for h in hits] == ["word"]
    assert hits[0].score == pytest.approx(1.0)


def test_ties_do_not_depend_on_the_order_of_the_input():
    a, b = _chunk("a", "same words"), _chunk("b", "same words")
    forward = scoring.rank("zzz", [(a, 0.8), (b, 0.8)], k=2, min_score=0.0)
    backward = scoring.rank("zzz", [(b, 0.8), (a, 0.8)], k=2, min_score=0.0)
    assert [h.chunk.id for h in forward] == [h.chunk.id for h in backward]


def test_rank_of_no_candidates_is_empty():
    assert scoring.rank("anything", [], k=3) == []
