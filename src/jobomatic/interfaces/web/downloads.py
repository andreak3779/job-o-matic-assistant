"""Downloads are served by an id the server issued, never by a name the request supplies (ADR 0025).

A command's result lists the files it wrote. The page registers those paths here and links to
``/download/<id>``. Nothing in a request can name a path, so there is nothing to traverse.
"""

from __future__ import annotations

import secrets
import threading
from pathlib import Path


class Downloads:
    def __init__(self) -> None:
        self._paths: dict[str, Path] = {}
        self._lock = threading.Lock()

    def issue(self, path: Path) -> str:
        """An unguessable id for ``path``, which a result said it wrote."""
        download_id = secrets.token_urlsafe(16)
        with self._lock:
            self._paths[download_id] = path
        return download_id

    def get(self, download_id: str) -> Path | None:
        """The registered file, or ``None`` for an unknown id or a file that is gone."""
        with self._lock:
            path = self._paths.get(download_id)
        return path if path is not None and path.is_file() else None
