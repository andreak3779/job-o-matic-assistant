"""Public Microsoft Learn learning-path pages: confirm a path's link and list its modules.

A path page is accepted only if its ``<meta name="uid">`` equals the uid we hold, so a wrong
guess at the address can never attach the wrong page. Pages are cached, and uncached requests are
spaced out. Nothing here needs a sign-in.
"""

from __future__ import annotations

import re
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

from jobomatic.learning.model import Enrichment, LearningItem

_SITE = "https://learn.microsoft.com"
_UID = re.compile(r'<meta\s+name="uid"\s+content="([^"]+)"', re.IGNORECASE)
_MODULE_LINK = re.compile(r'href="(?:\.\./)*(?:/[a-z-]+)?/?(?:training/)?modules/([a-z0-9-]+)/?"')


def path_slug(uid: str) -> str:
    """``learn.wwl.get-started-c-sharp-part-1`` -> ``get-started-c-sharp-part-1``."""
    return uid.removeprefix("learn.").split(".")[-1]


def fetch_page(url: str) -> str | None:
    """Download one public page; ``None`` when it does not exist."""
    request = urllib.request.Request(url, headers={"User-Agent": "job-o-matic-assistant"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return str(response.read().decode("utf-8", errors="replace"))
    except OSError:
        return None


class MsLearnPageEnricher:
    """``LearningEnricher`` for learning paths."""

    def __init__(
        self,
        cache_dir: Path,
        fetch: Callable[[str], str | None] = fetch_page,
        pause: float = 1.0,
    ) -> None:
        self._cache = cache_dir
        self._fetch = fetch
        self._pause = pause
        self._fetched_any = False

    def enrich(self, item: LearningItem) -> Enrichment | None:
        if not item.id.startswith("mslearn:learn."):
            return None
        uid = item.id.removeprefix("mslearn:")
        slug = path_slug(uid)
        html = self._page(uid, f"{_SITE}/en-us/training/paths/{slug}/")
        if html is None:
            return None
        found = _UID.search(html)
        if not found or found.group(1) != uid:
            return None  # a page, but not this path
        modules = list(dict.fromkeys(_MODULE_LINK.findall(html)))
        return Enrichment(
            url=f"{_SITE}/training/paths/{slug}/",
            module_paths=[f"/training/modules/{m}/" for m in modules],
        )

    def _page(self, uid: str, url: str) -> str | None:
        cached = self._cache / f"{uid}.html"
        if cached.is_file():
            return cached.read_text(encoding="utf-8")
        if self._fetched_any and self._pause:
            time.sleep(self._pause)
        self._fetched_any = True
        html = self._fetch(url)
        if html is not None:
            self._cache.mkdir(parents=True, exist_ok=True)
            cached.write_text(html, encoding="utf-8")
        return html
