"""What the retrieval core needs from the outside world (ADR 0016, 0019)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from jobomatic.retrieval.model import Chunk


class Embedder(Protocol):
    model: str

    def embed(self, texts: Sequence[str], *, query: bool) -> list[list[float]]:
        """One vector per text. ``query`` is True for a search phrase, False for a document."""
        ...


# A prompt in, the model's reply out.
ChatFn = Callable[[str], str]


@dataclass(frozen=True)
class IndexEntry:
    """A chunk to store. ``vector`` is None when the stored vector is still right."""

    chunk: Chunk
    text_hash: str
    vector: list[float] | None


class IndexStore(Protocol):
    """A rebuildable index of chunks. Never the source of truth: the profile is."""

    def fingerprint(self) -> tuple[str, int] | None:
        """The ``(embedding model, vector size)`` the stored vectors came from, or None if empty."""
        ...

    def hashes(self) -> dict[str, str]:
        """Chunk id to the hash of the text that was embedded."""
        ...

    def apply(
        self,
        entries: Sequence[IndexEntry],
        remove: Sequence[str],
        *,
        model: str,
        dimensions: int,
        reset: bool,
    ) -> None:
        """Store ``entries`` and drop ``remove`` in one transaction; ``reset`` clears it first."""
        ...

    def chunks(self, kinds: frozenset[str] | None = None) -> list[Chunk]:
        """Every stored chunk, optionally only of the given kinds."""
        ...

    def nearest(
        self, vector: list[float], limit: int, kinds: frozenset[str] | None = None
    ) -> list[tuple[Chunk, float]]:
        """Up to ``limit`` chunks with their cosine similarity to ``vector``, best first."""
        ...
