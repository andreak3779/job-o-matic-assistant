"""Record real embeddings once and replay them, so CI can run the demo evaluation offline."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def _key(text: str, query: bool) -> str:
    return ("query:" if query else "doc:") + text


class RecordingEmbedder:
    """Wraps a real embedder and remembers every vector it returns."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.model = inner.model
        self.vectors: dict[str, list[float]] = {}

    def embed(self, texts: Sequence[str], *, query: bool) -> list[list[float]]:
        vectors = self.inner.embed(texts, query=query)
        for text, vector in zip(texts, vectors, strict=True):
            self.vectors[_key(text, query)] = [round(x, 4) for x in vector]
        return vectors

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"model": self.model, "vectors": self.vectors}, separators=(",", ":")),
            encoding="utf-8",
        )


class ReplayEmbedder:
    """Returns recorded vectors; a text that was never recorded is an error, not a guess."""

    def __init__(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        self.model: str = data["model"]
        self.vectors: dict[str, list[float]] = data["vectors"]

    def embed(self, texts: Sequence[str], *, query: bool) -> list[list[float]]:
        missing = [t for t in texts if _key(t, query) not in self.vectors]
        if missing:
            raise KeyError(f"no recorded vector for {missing[0]!r}; re-record with --record")
        return [self.vectors[_key(t, query)] for t in texts]
