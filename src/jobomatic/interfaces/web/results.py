"""Results held between a form post and the page that shows them (ADR 0025).

A form that ran a command answers with a redirect, and the result page is an ordinary GET. Then a
reload of the result page shows the same result again, and does not ask the browser to send the form
a second time: that would run the fit check again, or write a second set of documents. The first
request keeps what the page needs here, under an id the server issued, and the redirect carries only
that id. Nothing is written to disk. The newest few are kept; an older one is gone, and its page says
so and asks for the form to be sent again.
"""

from __future__ import annotations

import secrets
import threading
from collections import OrderedDict
from typing import Any

MAX_HELD = 16  # one person; far more than the number of result pages open at once


class Results:
    def __init__(self) -> None:
        self._held: OrderedDict[str, tuple[str, dict[str, Any]]] = OrderedDict()
        self._lock = threading.Lock()

    def hold(self, kind: str, context: dict[str, Any]) -> str:
        """Keep ``context`` for the page of this ``kind``; return the id to redirect to."""
        result_id = secrets.token_urlsafe(16)
        with self._lock:
            self._held[result_id] = (kind, context)
            while len(self._held) > MAX_HELD:
                self._held.popitem(last=False)
        return result_id

    def get(self, kind: str, result_id: str) -> dict[str, Any] | None:
        """The held context, or ``None`` if the id is unknown, gone, or for another page."""
        with self._lock:
            held = self._held.get(result_id)
        return held[1] if held is not None and held[0] == kind else None
