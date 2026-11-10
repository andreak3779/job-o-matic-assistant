"""Evidence retrieval types: what is indexed (``Chunk``) and what a search returns (``Hit``).

Pure domain code (ADR 0016, 0019): no file access, no network, no knowledge of where a chunk came
from. ``jobomatic.corpus`` turns the profile and the learning history into chunks.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class RetrievalError(RuntimeError):
    """The index or a model service is unusable. The message says what to do about it."""


class EmbeddingUnavailable(RetrievalError):
    """The embedding service cannot be reached or returned something unusable."""


@dataclass(frozen=True)
class Chunk:
    """One retrievable piece of evidence, with a citation back to where it came from."""

    id: str  # stable and unique, for example ``pluralsight:<path>`` or ``project:<name>``
    kind: str  # course | lab | module | learning_path | project | experience | story
    title: str
    text: str  # what is embedded and keyword-matched
    status: str = ""  # "complete" or "" when not applicable
    url: str = ""
    # Private prose (resume bullets, interview stories). It can be retrieved and shown on this
    # machine but is never put in a prompt sent to a cloud model.
    local_only: bool = False


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float
    semantic: float
    keyword: float


@dataclass
class SkillEvidence:
    skill: str
    engine_status: str = ""  # status from the fit engine, when known
    hits: list[Hit] = field(default_factory=list)
    rationale: str | None = None
    rationale_note: str | None = None


@dataclass(frozen=True)
class BuildReport:
    """What ``build_index`` did, so the caller can say it."""

    added: int
    updated: int  # text changed, so re-embedded
    removed: int
    unchanged: int
    rebuilt: bool  # the whole index was discarded (a new embedding model or vector size)

    @property
    def embedded(self) -> int:
        return self.added + self.updated

    @property
    def total(self) -> int:
        return self.added + self.updated + self.unchanged
