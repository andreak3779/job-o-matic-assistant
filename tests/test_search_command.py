"""The evidence search as a command that returns a result (ADR 0028)."""

from __future__ import annotations

import pytest

from jobomatic import bootstrap
from jobomatic.commands import search
from jobomatic.results import console
from jobomatic.retrieval import scoring
from jobomatic.retrieval.model import EmbeddingUnavailable, SkillEvidence
from tests.retrieval_fakes import FakeEmbedder


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeEmbedder:
    embedder = FakeEmbedder()
    monkeypatch.setattr(bootstrap, "retrieval_embedder", lambda model=None: embedder)
    return embedder


def test_search_returns_the_evidence_as_data_and_logs_the_index_sync(
    fake: FakeEmbedder, capsys: pytest.CaptureFixture[str]
) -> None:
    result = search.search("message broker routing", min_score=0.0)
    assert result.status == "ok"
    assert isinstance(result.data, SkillEvidence)
    assert result.data.skill == "message broker routing"
    assert [m.level for m in result.messages] == ["log"]
    assert result.messages[0].text.startswith(("Index up to date:", "Rebuilt the index:"))
    assert capsys.readouterr() == ("", "")


def test_the_index_note_goes_to_stderr_and_the_evidence_to_stdout(fake: FakeEmbedder) -> None:
    text = console(search.search("message broker routing", min_score=0.0), search.render)
    assert "Message Queues in Practice" in text.stdout
    assert text.stderr.startswith(("Index up to date:", "Rebuilt the index:"))


def test_the_default_cutoff_is_read_when_the_search_runs(
    fake: FakeEmbedder, monkeypatch: pytest.MonkeyPatch
) -> None:
    strict = search.search("message broker routing")
    monkeypatch.setattr(scoring, "DEFAULT_MIN_SCORE", 0.0)
    lenient = search.search("message broker routing")
    assert strict.data is not None and lenient.data is not None
    assert len(lenient.data.hits) >= len(strict.data.hits)


def test_the_kinds_limit_what_is_searched(fake: FakeEmbedder) -> None:
    only_projects = search.search(
        "message broker routing", min_score=0.0, kinds=frozenset({"project"})
    )
    assert only_projects.data is not None
    assert {hit.chunk.kind for hit in only_projects.data.hits} <= {"project"}


def test_keyword_search_needs_an_index_and_says_so(fake: FakeEmbedder) -> None:
    result = search.search("Redis", keyword_only=True)
    assert result.status == "error"
    assert console(result).stderr == "No index yet; run `index build` first.\n"


def test_a_stopped_embedding_service_is_an_error_that_says_how_to_start_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Down:
        model = "fake-embed"

        def embed(self, *args, **kwargs):
            raise EmbeddingUnavailable("cannot reach http://localhost:11434/api/embed")

    monkeypatch.setattr(bootstrap, "retrieval_embedder", lambda model=None: Down())
    result = search.search("terraform", embed_model="fake-embed")
    assert result.status == "error" and result.exit_code == 1
    stderr = console(result).stderr
    assert stderr.startswith("Evidence search skipped: cannot reach")
    assert "ollama pull fake-embed" in stderr
    assert "Fit ratings and documents do not need it." in stderr
