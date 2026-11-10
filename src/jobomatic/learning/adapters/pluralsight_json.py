"""Pluralsight history as JSON, read into completed learning items.

Two shapes are accepted:

* The **import file** written by ``templates/pluralsight_import_template.html``::

      {"format": "jobomatic-pluralsight-history", "version": 1, "generated_on": "2026-11-10",
       "entries": [{"name": ..., "type": "Course", "url": ..., "duration": "1h 30m",
                    "completion_percentage": "100.0%", "completed_date": "Nov 08, 2026",
                    "completed_on": "2026-11-08"}, ...]}

* The older bare list of the same entries (no wrapper). It still imports, with a warning, because
  nothing marks it as Pluralsight data.

Like the HTML reader, a file that does not look right fails loudly instead of returning a partial
list (ADR 0007), only entries at 100% are kept, and nothing here touches the network or the
store. The page structure checks of the HTML reader do not apply; these checks are on the keys.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from jobomatic.learning.adapters.pluralsight_html import item_id
from jobomatic.learning.model import Kind, LearningItem, Provider, SourceBatch
from jobomatic.learning.service import LearningError

FORMAT = "jobomatic-pluralsight-history"
VERSION = 1

_REQUIRED = ("name", "type", "url", "completion_percentage")
_MONTHS = {
    m: n
    for n, m in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1
    )
}


def looks_like_pluralsight_history(data: object) -> bool:
    """True for the import file or the older bare list; false for e.g. a Learn transcript."""
    if isinstance(data, dict):
        return data.get("format") == FORMAT
    return (
        isinstance(data, list)
        and bool(data)
        and all(isinstance(e, dict) and "name" in e and "completion_percentage" in e for e in data)
    )


class PluralsightJsonSource:
    """``LearningSource`` for a Pluralsight import file (or the older bare list)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> SourceBatch:
        name = self._path.name
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise LearningError(f"cannot read {self._path}: {exc}") from exc
        except ValueError as exc:
            raise LearningError(f"{name}: not readable JSON: {exc}") from exc

        warnings: list[str] = []
        entries = _entries(data, name, warnings)

        items: list[LearningItem] = []
        in_progress = skipped = 0
        for position, entry in enumerate(entries, 1):
            _check_entry(entry, position, name)
            title = re.sub(r"\s+", " ", str(entry["name"])).strip()
            if not title:
                skipped += 1
                continue
            if _percentage(entry["completion_percentage"]) != 100.0:
                in_progress += 1
                continue
            label = str(entry["type"]).strip().lower()
            if label not in ("course", "lab"):
                raise LearningError(f"{name}: entry {position} ({title!r}) has type {label!r}")
            url = _normalize_url(entry["url"])
            completed = _date(entry)
            if completed is None:
                warnings.append(f"{title}: completed, but the file gives no date")
            items.append(
                LearningItem(
                    id=item_id(url, title),
                    provider=Provider.PLURALSIGHT,
                    kind=Kind.LAB if label == "lab" else Kind.COURSE,
                    title=title,
                    url=url,
                    completed_on=completed,
                    duration_minutes=_minutes(entry.get("duration")),
                    source=name,
                )
            )
        if skipped:
            warnings.append(f"{skipped} entries had no title and were skipped")
        if in_progress:
            warnings.append(f"{in_progress} entries are not at 100% and were left out")
        return SourceBatch(name, items, [], warnings)


def _entries(data: Any, name: str, warnings: list[str]) -> list[Any]:
    if isinstance(data, dict):
        if data.get("format") != FORMAT:
            raise LearningError(
                f"{name}: this is not a Pluralsight import file (expected "
                f'"format": "{FORMAT}"). Nothing was imported.'
            )
        if data.get("version") != VERSION:
            raise LearningError(
                f"{name}: import file version {data.get('version')!r}; this importer reads "
                f"version {VERSION}. Regenerate it with the current template. "
                "Nothing was imported."
            )
        entries = data.get("entries")
    else:
        entries = data
        warnings.append(
            "a bare list with no format marker; accepted as Pluralsight history. "
            "Regenerate it with the current template to get the versioned file"
        )
    if not isinstance(entries, list):
        raise LearningError(f"{name}: expected a list of entries. Nothing was imported.")
    if not entries:
        raise LearningError(f"{name}: the file has no entries. Nothing was imported.")
    return entries


def _check_entry(entry: Any, position: int, name: str) -> None:
    if not isinstance(entry, dict):
        raise LearningError(f"{name}: entry {position} is not an object. Nothing was imported.")
    missing = [k for k in _REQUIRED if k not in entry]
    if missing:
        raise LearningError(
            f"{name}: entry {position} is missing {', '.join(missing)}: the format may have "
            "changed. Nothing was imported."
        )


def _normalize_url(href: object) -> str | None:
    if not isinstance(href, str) or not href:
        return None
    if href.startswith("/"):
        return f"https://app.pluralsight.com{href}"
    return href


def _percentage(value: object) -> float | None:
    text = str(value or "").strip()
    return float(text.rstrip("%")) if re.match(r"^\d+\.?\d*%$", text) else None


def _minutes(value: object) -> int | None:
    text = str(value or "")
    hours = re.search(r"(\d+)\s*h", text)
    minutes = re.search(r"(\d+)\s*m", text)
    if not (hours or minutes):
        return None
    return (int(hours.group(1)) * 60 if hours else 0) + (int(minutes.group(1)) if minutes else 0)


def _date(entry: dict[str, Any]) -> dt.date | None:
    """``completed_on`` (ISO) when present, else ``completed_date`` as ``Nov 08, 2026``."""
    iso = entry.get("completed_on")
    if isinstance(iso, str):
        try:
            return dt.date.fromisoformat(iso)
        except ValueError:
            return None
    text = str(entry.get("completed_date") or "")
    match = re.match(r"^([A-Za-z]{3})\w*\s+(\d{1,2}),\s*(\d{4})$", text)
    if not match or match.group(1).lower() not in _MONTHS:
        return None
    try:
        return dt.date(int(match.group(3)), _MONTHS[match.group(1).lower()], int(match.group(2)))
    except ValueError:
        return None
