"""The recall floor: retrieval quality must not silently get worse.

Runs the labelled demo queries against the fictional demo vault with recorded embeddings, so it
needs no embedding service. The real-vault floor (hybrid recall@3 of 21/24) is checked by hand
with ``scripts/eval_retrieval.py`` because it needs Ollama and the private learning history.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from jobomatic import bootstrap
from jobomatic.retrieval import service
from jobomatic.retrieval.adapters.sqlite_index import SqliteIndex
from tests.retrieval_recorded import ReplayEmbedder

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "retrieval"

# Measured when the demo vectors were recorded; raise it when retrieval improves, never lower it.
HYBRID_RECALL_AT_3_FLOOR = 18


def _evaluate():
    spec = importlib.util.spec_from_file_location(
        "eval_retrieval", ROOT / "scripts" / "eval_retrieval.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def evaluated(tmp_path):
    cases = json.loads((FIXTURES / "demo_eval_queries.json").read_text(encoding="utf-8"))["queries"]
    embedder = ReplayEmbedder(FIXTURES / "demo-vectors.json")
    store = SqliteIndex(tmp_path / "evidence.sqlite")
    service.build_index(bootstrap.retrieval_chunks(), embedder, store)
    return _evaluate().evaluate(store, embedder, cases, 3), len(cases)


def test_hybrid_retrieval_meets_the_recall_floor(evaluated):
    results, total = evaluated
    assert results["hybrid"][1] >= HYBRID_RECALL_AT_3_FLOOR, (results, total)


def test_hybrid_is_no_worse_than_keywords_alone(evaluated):
    results, _ = evaluated
    assert results["hybrid"][1] >= results["keyword only"][1]
    assert results["hybrid"][1] >= results["semantic only"][1] - 1
