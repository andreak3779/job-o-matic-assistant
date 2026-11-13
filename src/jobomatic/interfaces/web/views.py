"""Helpers the pages share: turning a ``CommandResult`` into what a template shows (ADR 0025).

A page never reads printed text. It takes the typed ``data`` of a result and its messages, and the
template decides how they look. Messages are split by level the way the other interfaces split them:
what went wrong or was worked around is an alert, advice is a note, how the run went is a log.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jobomatic.results import CommandResult, Message


@dataclass(frozen=True)
class Shown:
    """One command's result, ready for a template."""

    status: str
    data: Any
    alerts: tuple[Message, ...]
    notes: tuple[Message, ...]
    logs: tuple[Message, ...]
    info: tuple[Message, ...]
    override: str | None
    written: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def refused(self) -> bool:
        return self.status == "refused"


def show(result: CommandResult[Any]) -> Shown:
    by_level: dict[str, list[Message]] = {
        "info": [],
        "note": [],
        "log": [],
        "warning": [],
        "error": [],
    }
    for message in result.messages:
        by_level[message.level].append(message)
    return Shown(
        status=result.status,
        data=result.data,
        alerts=tuple(by_level["error"] + by_level["warning"]),
        notes=tuple(by_level["note"]),
        logs=tuple(by_level["log"]),
        info=tuple(by_level["info"]),
        override=result.override,
        written=tuple(str(p) for p in result.written),
    )
