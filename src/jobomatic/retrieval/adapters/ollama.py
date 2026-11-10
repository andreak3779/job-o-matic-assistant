"""Embeddings and chat through a local Ollama server, using only ``urllib``."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

from jobomatic.retrieval.model import EmbeddingUnavailable, RetrievalError
from jobomatic.retrieval.ports import ChatFn

DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_CHAT_MODEL = "gemma4:cloud"
DEFAULT_OLLAMA_URL = "http://localhost:11434"


def _base_url(base_url: str | None) -> str:
    url = (base_url or os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_URL).rstrip("/")
    return url if url.startswith("http") else "http://" + url


def _post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise EmbeddingUnavailable(f"{url} returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise EmbeddingUnavailable(f"cannot reach {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise EmbeddingUnavailable(f"{url} returned invalid JSON") from exc
    if not isinstance(body, dict):
        raise EmbeddingUnavailable(f"{url} returned an unexpected response")
    if body.get("error"):
        raise EmbeddingUnavailable(f"{url}: {body['error']}")
    return body


class OllamaEmbedder:
    """Local embeddings through Ollama's ``/api/embed``.

    ``nomic-embed-text`` expects task prefixes, so documents and queries are embedded with
    different ones. A different model gets no prefix.
    """

    def __init__(
        self,
        model: str = DEFAULT_EMBED_MODEL,
        base_url: str | None = None,
        batch_size: int = 32,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = _base_url(base_url)
        self.batch_size = batch_size
        self.timeout = timeout

    def _prefix(self, query: bool) -> str:
        if not self.model.startswith("nomic-embed-text"):
            return ""
        return "search_query: " if query else "search_document: "

    def embed(self, texts: Sequence[str], *, query: bool) -> list[list[float]]:
        prefix = self._prefix(query)
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = [prefix + t for t in texts[start : start + self.batch_size]]
            body = _post_json(
                f"{self.base_url}/api/embed",
                {"model": self.model, "input": batch},
                self.timeout,
            )
            embeddings = body.get("embeddings")
            if not isinstance(embeddings, list) or len(embeddings) != len(batch):
                raise EmbeddingUnavailable("embedding response did not match the request")
            vectors.extend([float(x) for x in vec] for vec in embeddings)
        return vectors


def ollama_chat(model: str = DEFAULT_CHAT_MODEL, base_url: str | None = None) -> ChatFn:
    """A ``prompt -> reply`` function over Ollama's ``/api/chat`` (cloud or local model)."""
    url = _base_url(base_url)

    def chat(prompt: str) -> str:
        body = _post_json(
            f"{url}/api/chat",
            {
                "model": model,
                "stream": False,
                "options": {"temperature": 0},
                "messages": [{"role": "user", "content": prompt}],
            },
            180.0,
        )
        message = body.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise RetrievalError("chat model returned no text")
        return content.strip()

    return chat
