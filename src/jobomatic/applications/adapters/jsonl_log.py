"""The applications log as a JSON-lines file (one event per line), tracked in git.

Append-only is what makes it safe across two laptops: each machine only ever adds lines, so git's
``merge=union`` attribute keeps both machines' lines and the fold gives the same answer
everywhere. No line is ever rewritten.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from jobomatic import paths
from jobomatic.applications.model import event_problem


class JsonlApplicationLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read_events(self) -> list[dict[str, Any]]:
        """Read every event; a malformed line raises ``ValueError`` naming the line."""
        if not self.path.is_file():
            return []
        events: list[dict[str, Any]] = []
        name = self.path.name
        for number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{name} line {number} is not valid JSON: {exc}") from exc
            problem = event_problem(event)
            if problem:
                raise ValueError(f"{name} line {number} {problem}")
            events.append(event)
        return events

    def append(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # O_APPEND makes a single small write atomic with respect to other appenders.
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)


def open_log(path: Path | None = None) -> JsonlApplicationLog:
    """The vault's applications log, or the file at ``path`` (for tests and other locations)."""
    return JsonlApplicationLog(path or paths.applications_log())
