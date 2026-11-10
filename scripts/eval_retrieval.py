#!/usr/bin/env python3
"""Evaluate evidence retrieval on a hand-labelled query set: keyword, semantic and hybrid.

Usage:
  python scripts/eval_retrieval.py                 # your real vault (needs Ollama running)
  python scripts/eval_retrieval.py --demo          # the fictional demo vault (needs Ollama)
  python scripts/eval_retrieval.py --demo --record # also (re)write the recorded demo vectors

The recorded vectors (tests/fixtures/retrieval/demo-vectors.json) let CI re-run the demo
evaluation without an embedding service (tests/test_retrieval_eval.py). Re-record them when the
demo vault, its queries or the embedding model change.

For each method the table shows recall@1 and recall@k: the share of queries whose correct
evidence is the top result, or among the top k. A cutoff sweep for the hybrid method follows,
so the default ``min_score`` can be chosen from data (ADR 0012).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

DEMO = ROOT / "demo-vault"
DEMO_QUERIES = ROOT / "tests" / "fixtures" / "retrieval" / "demo_eval_queries.json"
REAL_QUERIES = ROOT / "tests" / "fixtures" / "evidence_eval_queries.json"
RECORDED = ROOT / "tests" / "fixtures" / "retrieval" / "demo-vectors.json"


# The labelled queries name courses, labs and modules, so only those are scored. Resume bullets
# and projects are in the index too, but nothing labels them, so a good match there would count
# as a miss. This also keeps the numbers comparable with the baseline in ADR 0012.
LEARNING_KINDS = frozenset({"course", "lab", "module", "learning_path"})


def correct(title: str, expected: list[str]) -> bool:
    return any(e.lower() in title.lower() for e in expected)


def evaluate(store, embedder, cases, k: int = 3) -> dict[str, tuple[int, int]]:
    """``{method: (recall@1, recall@k)}`` over ``cases`` for keyword, semantic and hybrid."""
    from jobomatic.retrieval import service

    methods = {
        "keyword only": dict(semantic=False, keyword_weight=0.0, min_score=1e-9),
        "semantic only": dict(keyword_weight=0.0, min_score=-1.0),
        "hybrid": dict(min_score=-1.0),
    }
    out: dict[str, tuple[int, int]] = {}
    for name, kw in methods.items():
        r1 = rk = 0
        for case in cases:
            hits = service.search(store, case["query"], embedder, k=k, kinds=LEARNING_KINDS, **kw)
            r1 += bool(hits) and correct(hits[0].chunk.title, case["expected"])
            rk += any(correct(h.chunk.title, case["expected"]) for h in hits)
        out[name] = (r1, rk)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--demo", action="store_true", help="use the fictional demo vault")
    parser.add_argument("--record", action="store_true", help="with --demo: write the vectors")
    args = parser.parse_args(argv)

    scratch = None
    if args.demo:
        os.environ["JOBOMATIC_VAULT"] = str(DEMO)
        cases_file = DEMO_QUERIES
        scratch = tempfile.TemporaryDirectory()
        index_path = Path(scratch.name) / "evidence.sqlite"
    else:
        cases_file = REAL_QUERIES
        index_path = None

    from jobomatic import bootstrap
    from jobomatic.retrieval import service
    from jobomatic.retrieval.adapters.sqlite_index import SqliteIndex

    cases = json.loads(cases_file.read_text(encoding="utf-8"))["queries"]
    embedder = bootstrap.retrieval_embedder()
    if args.record:
        from tests.retrieval_recorded import RecordingEmbedder

        embedder = RecordingEmbedder(embedder)
    store = SqliteIndex(index_path) if index_path else bootstrap.retrieval_index()
    chunks = bootstrap.retrieval_chunks()
    report = service.build_index(chunks, embedder, store)
    print(f"{report.total} chunks, {len(cases)} labelled queries, k={args.k}\n")
    if args.record:
        for case in cases:  # the queries too, before any scoring
            embedder.embed([case["query"]], query=True)
        embedder.save(RECORDED)  # type: ignore[attr-defined]
        print(f"Recorded vectors written to {RECORDED.relative_to(ROOT)}\n")

    results = evaluate(store, embedder, cases, args.k)
    print(f"| Method | Recall@1 | Recall@{args.k} |")
    print("| --- | --- | --- |")
    for name, (r1, rk) in results.items():
        print(f"| {name} | {r1}/{len(cases)} | {rk}/{len(cases)} |")

    print("\nHybrid cutoff sweep (queries answered; share of returned items that are correct)")
    print(f"| Cutoff | Queries answered | Precision of returned items | Recall@{args.k} |")
    print("| --- | --- | --- | --- |")
    for cutoff in (0.50, 0.55, 0.60, 0.65, 0.70):
        answered = returned = right = rk = 0
        for case in cases:
            hits = service.search(
                store, case["query"], embedder, k=args.k, min_score=cutoff, kinds=LEARNING_KINDS
            )
            answered += bool(hits)
            returned += len(hits)
            ok = [correct(h.chunk.title, case["expected"]) for h in hits]
            right += sum(ok)
            rk += any(ok)
        precision = f"{right}/{returned}" if returned else "n/a"
        print(f"| {cutoff:.2f} | {answered}/{len(cases)} | {precision} | {rk}/{len(cases)} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
