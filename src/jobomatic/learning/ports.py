"""What the learning use cases need from the outside world. Adapters implement these."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from jobomatic.learning.model import Enrichment, LearningItem, SourceBatch


class LearningSource(Protocol):
    """Reads one provider's export into completed items. Reading must not touch the network."""

    def read(self) -> SourceBatch: ...


class LearningRepository(Protocol):
    """Where the imported items are kept (the vault's ``profile/learning/items.yaml``)."""

    def load(self) -> list[LearningItem]: ...

    def save(self, items: list[LearningItem]) -> None: ...


class LearningEnricher(Protocol):
    """Fills gaps from a public page. Returns ``None`` when no page can confirm the item."""

    def enrich(self, item: LearningItem) -> Enrichment | None: ...


class ImportArchive(Protocol):
    """Keeps a copy of each raw export so an import can be replayed."""

    def store(self, provider: str, raw: Path) -> Path: ...
