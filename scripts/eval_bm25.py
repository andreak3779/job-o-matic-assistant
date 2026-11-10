#!/usr/bin/env python3
"""Experiment: does BM25 beat the keyword-overlap term in hybrid search?

Usage:
  python scripts/eval_bm25.py --demo      # fictional demo vault, recorded embeddings (no Ollama)
  python scripts/eval_bm25.py             # your real vault (needs Ollama running)
  python scripts/eval_bm25.py --per-query # also list, for each query, the methods that miss

The production scoring (``jobomatic.retrieval.scoring``) is NOT changed by this script. It only
compares ways of ranking the same candidates on the same labelled queries (learning items only,
as in ``eval_retrieval.py``), so the numbers line up with the 21/24 baseline in ADR 0012:

* semantic only        cosine similarity alone
* overlap hybrid       the current rule: similarity + 0.15 * share of query words found
* bm25 only            FTS5 BM25 alone
* bm25 blend (w)       similarity + w * BM25 (BM25 divided by the best BM25 for that query,
                       so it runs 0..1 like the overlap share it would replace)
* rrf                  reciprocal rank fusion of the semantic ranking and the BM25 ranking

BM25 comes from SQLite FTS5 with the ``porter`` stemmer, over a scratch copy of the chunk text,
so the production index schema is untouched. Every method sees the same candidates.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "src", ROOT / "scripts"):
    sys.path.insert(0, str(extra))

import eval_retrieval as base  # noqa: E402  (labelled queries, ``correct``, LEARNING_KINDS)

from jobomatic.retrieval import scoring  # noqa: E402
from jobomatic.retrieval.model import Chunk  # noqa: E402

RRF_K = 60  # the constant from the original reciprocal rank fusion paper; it damps the top ranks
BLEND_WEIGHTS = (0.05, 0.10, 0.15, 0.25, 0.50)

Candidates = list[tuple[Chunk, float]]  # (chunk, cosine similarity), every learning chunk
Method = Callable[[str, Candidates, dict[str, float]], list[str]]  # -> chunk ids, best first


class Bm25:
    """BM25 over the candidate chunks' text, using an in-memory FTS5 table."""

    def __init__(self, chunks: Sequence[Chunk]) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "create virtual table docs using fts5(id unindexed, text, tokenize='porter unicode61')"
        )
        self.conn.executemany(
            "insert into docs(id, text) values (?, ?)", [(c.id, c.text) for c in chunks]
        )

    def scores(self, query: str) -> dict[str, float]:
        """``{chunk id: relevance}`` (higher is better) for the chunks that match any query word."""
        words = sorted(scoring.tokens(query))
        if not words:
            return {}
        # Quote each word (FTS5 would read c# or .net as syntax) and OR them: a chunk needs only
        # one of the words, and BM25 rewards the rare ones, which is the point of the experiment.
        match = " OR ".join('"' + w.replace('"', '""') + '"' for w in words)
        rows = self.conn.execute("select id, -bm25(docs) from docs where docs match ?", (match,))
        return {chunk_id: float(score) for chunk_id, score in rows}  # FTS5 BM25 is lower = better


def _by_score(scores: dict[str, float]) -> list[str]:
    return [i for i, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def semantic_only(query: str, cands: Candidates, bm25: dict[str, float]) -> list[str]:
    return _by_score({c.id: sim for c, sim in cands})


def overlap_hybrid(query: str, cands: Candidates, bm25: dict[str, float]) -> list[str]:
    hits = scoring.rank(query, cands, k=len(cands), min_score=-1.0)
    return [h.chunk.id for h in hits]


def bm25_only(query: str, cands: Candidates, bm25: dict[str, float]) -> list[str]:
    return _by_score({c.id: bm25.get(c.id, 0.0) for c, _ in cands})


def blend(weight: float) -> Method:
    def method(query: str, cands: Candidates, bm25: dict[str, float]) -> list[str]:
        best = max(bm25.values(), default=0.0)
        norm = {i: s / best for i, s in bm25.items()} if best > 0 else {}
        return _by_score({c.id: sim + weight * norm.get(c.id, 0.0) for c, sim in cands})

    return method


def rrf(query: str, cands: Candidates, bm25: dict[str, float]) -> list[str]:
    semantic_rank = {i: r for r, i in enumerate(_by_score({c.id: s for c, s in cands}), start=1)}
    bm25_rank = {i: r for r, i in enumerate(_by_score(bm25), start=1)}
    fused = {
        i: 1 / (RRF_K + r) + (1 / (RRF_K + bm25_rank[i]) if i in bm25_rank else 0.0)
        for i, r in semantic_rank.items()
    }
    return _by_score(fused)


def methods() -> dict[str, Method]:
    out: dict[str, Method] = {
        "semantic only": semantic_only,
        "overlap hybrid (current)": overlap_hybrid,
        "bm25 only": bm25_only,
    }
    for weight in BLEND_WEIGHTS:
        out[f"bm25 blend w={weight:.2f}"] = blend(weight)
    out["rrf (semantic + bm25)"] = rrf
    return out


def evaluate(
    cases: list[dict], candidates: dict[str, Candidates], bm25: Bm25, k: int
) -> tuple[dict[str, tuple[int, int]], dict[str, list[str]]]:
    """Recall@1 and recall@k per method, plus the queries each method misses at k."""
    results: dict[str, tuple[int, int]] = {}
    misses: dict[str, list[str]] = {}
    for name, method in methods().items():
        r1 = rk = 0
        missed: list[str] = []
        for case in cases:
            cands = candidates[case["query"]]
            titles = {c.id: c.title for c, _ in cands}
            ranked = method(case["query"], cands, bm25.scores(case["query"]))
            ok = [base.correct(titles[i], case["expected"]) for i in ranked[:k]]
            r1 += bool(ok) and ok[0]
            rk += any(ok)
            if not any(ok):
                missed.append(case["query"])
        results[name] = (r1, rk)
        misses[name] = missed
    return results, misses


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--demo", action="store_true", help="use the fictional demo vault")
    parser.add_argument("--per-query", action="store_true", help="list each method's misses")
    args = parser.parse_args(argv)

    if args.demo:
        os.environ["JOBOMATIC_VAULT"] = str(base.DEMO)
    from jobomatic import bootstrap
    from jobomatic.retrieval import service
    from jobomatic.retrieval.adapters.sqlite_index import SqliteIndex

    cases = json.loads((base.DEMO_QUERIES if args.demo else base.REAL_QUERIES).read_text())[
        "queries"
    ]
    if args.demo:  # recorded vectors, so no embedding service is needed
        from tests.retrieval_recorded import ReplayEmbedder

        embedder = ReplayEmbedder(base.RECORDED)
        store = SqliteIndex(Path(tempfile.mkdtemp()) / "evidence.sqlite")
    else:
        embedder = bootstrap.retrieval_embedder()
        store = bootstrap.retrieval_index()
    service.build_index(bootstrap.retrieval_chunks(), embedder, store)

    everything = 10**6  # exhaustive: every learning chunk, so each method ranks the same pool
    candidates: dict[str, Candidates] = {}
    for case in cases:  # embed each query once and share the result between methods
        hits = service.search(
            store, case["query"], embedder, k=everything, min_score=-1.0, keyword_weight=0.0,
            kinds=base.LEARNING_KINDS,
        )  # fmt: skip
        candidates[case["query"]] = [(h.chunk, h.semantic) for h in hits]
    pool = [c for c, _ in next(iter(candidates.values()))]

    results, misses = evaluate(cases, candidates, Bm25(pool), args.k)
    print(f"{len(pool)} learning chunks, {len(cases)} labelled queries, k={args.k}\n")
    print(f"| Method | Recall@1 | Recall@{args.k} |")
    print("| --- | --- | --- |")
    for name, (r1, rk) in results.items():
        print(f"| {name} | {r1}/{len(cases)} | {rk}/{len(cases)} |")
    if args.per_query:
        print("\nQueries missed at k, by method")
        for name, missed in misses.items():
            print(f"- {name}: {len(missed)} missed")
            for query in missed:
                print(f"    {query}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
