"""A file the browser sent, held in memory between a preview and the click that applies it (ADR 0025).

The import page shows a dry run first and applies only on a second, deliberate click. The second
request cannot carry a file path (no path ever comes from the browser), so the first stores the text
here under an id the server issued, and the Apply form carries only that id. Nothing touches the disk
until the command is called, and an entry is gone after it is used.
"""

from __future__ import annotations

import secrets
import threading
from collections import OrderedDict

MAX_HELD = 8  # a person previews a handful of files at most; older ones are dropped


class Uploads:
    def __init__(self) -> None:
        self._held: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()

    def hold(self, text: str) -> str:
        upload_id = secrets.token_urlsafe(16)
        with self._lock:
            self._held[upload_id] = text
            while len(self._held) > MAX_HELD:
                self._held.popitem(last=False)
        return upload_id

    def take(self, upload_id: str) -> str | None:
        """The held text, once: it is removed, so a second Apply with the same id finds nothing."""
        with self._lock:
            return self._held.pop(upload_id, None)
