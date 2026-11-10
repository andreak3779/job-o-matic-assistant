"""What the applications use cases need from storage: an append-only list of events."""

from __future__ import annotations

from typing import Any, Protocol


class ApplicationLog(Protocol):
    """An append-only event log. Lines are only ever added, never rewritten (ADR 0010)."""

    def read_events(self) -> list[dict[str, Any]]:
        """Every event, in file order. A malformed line raises ``ValueError`` naming the line."""
        ...

    def append(self, event: dict[str, Any]) -> None:
        """Add one event."""
        ...
