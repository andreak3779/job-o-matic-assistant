"""The Ollama client, with the network call replaced."""

from __future__ import annotations

import pytest

from jobomatic.retrieval.adapters import ollama
from jobomatic.retrieval.model import EmbeddingUnavailable, RetrievalError


def test_embedder_prefixes_batches_and_validates(monkeypatch):
    sent = []

    def fake_post(url, payload, timeout):
        sent.append((url, payload))
        return {"embeddings": [[1.0, 0.0]] * len(payload["input"])}

    monkeypatch.setattr(ollama, "_post_json", fake_post)
    embedder = ollama.OllamaEmbedder(batch_size=2, base_url="localhost:11434")
    assert len(embedder.embed(["a", "b", "c"], query=False)) == 3
    assert [len(p["input"]) for _, p in sent] == [2, 1]
    assert sent[0][0] == "http://localhost:11434/api/embed"
    assert sent[0][1]["input"][0] == "search_document: a"
    embedder.embed(["q"], query=True)
    assert sent[-1][1]["input"] == ["search_query: q"]

    other = ollama.OllamaEmbedder(model="bge-m3")
    other.embed(["a"], query=True)
    assert sent[-1][1]["input"] == ["a"]  # only nomic-embed-text takes task prefixes

    monkeypatch.setattr(ollama, "_post_json", lambda *a, **k: {"embeddings": []})
    with pytest.raises(EmbeddingUnavailable):
        embedder.embed(["a"], query=False)


def test_chat_returns_text_and_rejects_empty(monkeypatch):
    monkeypatch.setattr(ollama, "_post_json", lambda *a, **k: {"message": {"content": " hi "}})
    assert ollama.ollama_chat("m")("p") == "hi"
    monkeypatch.setattr(ollama, "_post_json", lambda *a, **k: {"message": {"content": ""}})
    with pytest.raises(RetrievalError):
        ollama.ollama_chat("m")("p")


def test_post_json_surfaces_service_errors(monkeypatch):
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"error": "unauthorized"}'

    monkeypatch.setattr(ollama.urllib.request, "urlopen", lambda *a, **k: Resp())
    with pytest.raises(EmbeddingUnavailable, match="unauthorized"):
        ollama._post_json("http://x/api/embed", {}, 1.0)


def test_an_unreachable_server_is_embedding_unavailable(monkeypatch):
    def refuse(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(ollama.urllib.request, "urlopen", refuse)
    with pytest.raises(EmbeddingUnavailable, match="cannot reach"):
        ollama._post_json("http://localhost:1/api/embed", {}, 1.0)
