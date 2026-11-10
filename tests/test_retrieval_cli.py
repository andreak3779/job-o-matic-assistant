"""The ``index``, ``search`` and ``evidence`` commands, on the demo vault and a fake embedder."""

from __future__ import annotations

import argparse

import pytest

from jobomatic import bootstrap
from jobomatic.interfaces.cli import retrieval_cli
from jobomatic.retrieval.model import EmbeddingUnavailable
from tests.retrieval_fakes import FakeEmbedder


@pytest.fixture
def fake(monkeypatch):
    embedder = FakeEmbedder()
    monkeypatch.setattr(bootstrap, "retrieval_embedder", lambda model=None: embedder)
    return embedder


def _args(command, **over):
    base = dict(
        command=command,
        k=3,
        min_score=0.0,
        embed_model="fake-embed",
        chat_model="m",
        all=False,
        explain=False,
        rebuild=False,
        kind=None,
        keyword_only=False,
    )
    base.update(over)
    return argparse.Namespace(**base)


def test_index_build_then_again_embeds_nothing_the_second_time(fake, capsys):
    assert retrieval_cli.run(_args("index", index_command="build")) == 0
    first = capsys.readouterr().out
    assert "new" in first and "0 unchanged" in first
    calls = len(fake.calls)

    assert retrieval_cli.run(_args("index", index_command="build")) == 0
    assert "0 new, 0 changed, 0 removed" in capsys.readouterr().out
    assert len(fake.calls) == calls  # nothing was embedded


def test_index_build_rebuild_starts_again(fake, capsys):
    retrieval_cli.run(_args("index", index_command="build"))
    capsys.readouterr()
    assert retrieval_cli.run(_args("index", index_command="build", rebuild=True)) == 0
    assert "new" in capsys.readouterr().out


def test_search_prints_ranked_evidence(fake, capsys):
    assert retrieval_cli.run(_args("search", query="slow sql query tuning indexes")) == 0
    out = capsys.readouterr().out
    assert "## slow sql query tuning indexes" in out and "Practical SQL Query Tuning" in out


def test_search_keyword_only_needs_an_index_but_not_the_embedder(fake, capsys):
    assert retrieval_cli.run(_args("search", query="Redis", keyword_only=True, min_score=1e-9)) == 1
    assert "index build" in capsys.readouterr().err

    retrieval_cli.run(_args("index", index_command="build"))
    calls = len(fake.calls)
    assert retrieval_cli.run(_args("search", query="Redis", keyword_only=True, min_score=1e-9)) == 0
    assert "Caching with Redis" in capsys.readouterr().out
    assert len(fake.calls) == calls


def test_evidence_for_a_free_text_requirement(fake, capsys):
    assert retrieval_cli.run(_args("evidence", target="message broker routing")) == 0
    assert "Message Queues in Practice" in capsys.readouterr().out


def test_evidence_for_a_job_description_file(fake, capsys, tmp_path):
    jd = tmp_path / "jd.md"
    jd.write_text(
        "# Platform Engineer\n\n**Company:** Acme\n\n## Required Skills\n- Terraform\n- RabbitMQ\n",
        encoding="utf-8",
    )
    assert retrieval_cli.run(_args("evidence", target=str(jd), all=True)) == 0
    assert "## terraform" in capsys.readouterr().out


def test_a_stopped_embedding_service_is_skipped_with_a_clear_message(monkeypatch, capsys):
    class Down:
        model = "fake-embed"

        def embed(self, *a, **k):
            raise EmbeddingUnavailable("cannot reach http://localhost:11434/api/embed")

    monkeypatch.setattr(bootstrap, "retrieval_embedder", lambda model=None: Down())
    assert retrieval_cli.run(_args("evidence", target="anything")) == 1
    err = capsys.readouterr().err
    assert "Evidence search skipped" in err and "cannot reach" in err
    assert "ollama pull" in err and "Fit ratings and documents do not need it" in err


def test_the_fit_rating_does_not_need_the_embedding_service(monkeypatch):
    """Retrieval is advisory: the rating is computed with no embedder anywhere."""

    def boom(*a, **k):
        raise AssertionError("the fit engine must not touch retrieval")

    monkeypatch.setattr(bootstrap, "retrieval_embedder", boom)
    monkeypatch.setattr(bootstrap, "retrieval_index", boom)
    from jobomatic.fit.engine import rate_parsed_jd
    from jobomatic.fit.parser import parse_jd

    parsed = parse_jd("# Dev\n\n**Company:** Acme\n\n## Required Skills\n- C#\n- Docker\n")
    assert rate_parsed_jd(parsed, bootstrap.load_profile()) is not None
