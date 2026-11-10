"""Shared fakes for the retrieval tests: no test reaches Ollama or the real vault."""

from __future__ import annotations

import hashlib
import re

from jobomatic.retrieval.model import Chunk

DIMS = 64


class FakeEmbedder:
    """Deterministic bag-of-words vectors: texts sharing words are close.

    Independent of ``scoring`` on purpose, so the store and service tests do not depend on it.
    """

    def __init__(self, model: str = "fake-embed") -> None:
        self.model = model
        self.calls: list[tuple[int, bool]] = []

    def embed(self, texts, *, query):
        self.calls.append((len(texts), query))
        out = []
        for text in texts:
            vec = [0.0] * DIMS
            for word in set(re.findall(r"[a-z0-9]+", text.lower())):
                vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMS] += 1.0
            out.append(vec)
        return out


def sample_chunks() -> list[Chunk]:
    return [
        Chunk(
            "course:0",
            "course",
            "Understanding Query Optimization in SQL Server",
            "Understanding Query Optimization in SQL Server. Tune slow queries with indexes.",
            status="complete",
        ),
        Chunk(
            "course:1",
            "course",
            "RabbitMQ by Example",
            "RabbitMQ by Example. Message broker routing and durability.",
            status="complete",
        ),
        Chunk(
            "project:p",
            "project",
            "MoviesApp",
            "MoviesApp. ASP.NET Core API with Docker. Stack: C#, Docker",
        ),
        Chunk(
            "experience:j:0",
            "experience",
            "Acme — Developer",
            "Reduced database query time using indexes and tuning.",
            local_only=True,
        ),
    ]
