"""Pluralsight's course-history page, saved as HTML, read into completed learning items.

Ported from the earlier parser. The structure checks are kept: if Pluralsight changes the
page, reading fails loudly instead of returning a partial list (ADR 0007). Nothing is merged or
written here; matching against what is stored is the use case's job.

Needs the optional ``parser`` extra (beautifulsoup4 and lxml).
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from urllib.parse import urlparse

from jobomatic.learning.model import Kind, LearningItem, Provider, SourceBatch
from jobomatic.learning.service import LearningError

_MIN_STRUCTURAL_ROWS = 10
_COURSE_PATH = "library/courses/"


class PluralsightHtmlSource:
    """``LearningSource`` for a saved Pluralsight history page."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> SourceBatch:
        try:
            from bs4 import BeautifulSoup
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise LearningError(
                "reading a Pluralsight export needs beautifulsoup4 and lxml: "
                "pip install -e '.[parser]'"
            ) from exc
        try:
            content = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            raise LearningError(f"cannot read {self._path}: {exc}") from exc
        soup = BeautifulSoup(content, "lxml")
        _validate_structure(soup, self._path.name)

        items: list[LearningItem] = []
        warnings: list[str] = []
        skipped = in_progress = 0
        for row in soup.find_all("tr", {"role": "row"}):
            cells = row.find_all("td", {"role": "gridcell"})
            if len(cells) < 8:
                continue
            link = cells[1].find("a")
            title = re.sub(r"\s+", " ", link.get_text(strip=True)) if link else ""
            if not link or not title:
                skipped += 1
                continue
            percent = _percentage(cells[6])
            if percent != 100.0:
                in_progress += 1
                continue
            type_span = cells[2].find("span")
            label = type_span.get_text(strip=True) if type_span else "Course"
            url = _normalize_url(str(link.get("href") or ""))
            identifier = item_id(url, title)
            completed = _date(cells[7])
            if completed is None:
                warnings.append(f"{title}: completed, but the export gives no date")
            items.append(
                LearningItem(
                    id=identifier,
                    provider=Provider.PLURALSIGHT,
                    kind=Kind.LAB if label.lower() == "lab" else Kind.COURSE,
                    title=title,
                    url=url,
                    completed_on=completed,
                    duration_minutes=_minutes(cells[5]),
                    source=self._path.name,
                )
            )
        if skipped:
            warnings.append(f"{skipped} rows had no title link and were skipped")
        if in_progress:
            warnings.append(f"{in_progress} entries are not at 100% and were left out")
        return SourceBatch(self._path.name, items, [], warnings)


def _validate_structure(soup: object, name: str) -> None:
    problems: list[str] = []
    rows = soup.find_all("tr", {"role": "row"})  # type: ignore[attr-defined]
    if not rows:
        problems.append("no <tr role='row'> elements: the table structure is missing")
    valid = [r for r in rows if len(r.find_all("td", {"role": "gridcell"})) >= 8]
    if len(valid) < _MIN_STRUCTURAL_ROWS:
        problems.append(
            f"only {len(valid)} rows with 8+ gridcell columns (expected "
            f"{_MIN_STRUCTURAL_ROWS}+): the format may have changed or the export was filtered"
        )
    if not soup.find("span", string="Course") and not soup.find("span", string="Lab"):  # type: ignore[attr-defined]
        problems.append(
            "no <span>Course</span> or <span>Lab</span>: the type column may have changed"
        )
    dated = [
        t
        for t in soup.find_all("time")  # type: ignore[attr-defined]
        if re.match(r"^\d{2}-\d{2}-\d{4}$", t.get("datetime", ""))
    ]
    if not dated:
        problems.append("no <time datetime='MM-DD-YYYY'>: the date column may have changed")
    if problems:
        raise LearningError(
            f"{name}: this does not look like the Pluralsight history page I know how to read. "
            "Nothing was imported.\n  - " + "\n  - ".join(problems)
        )


def _normalize_url(href: str) -> str | None:
    if not href:
        return None
    if href.startswith("https://"):
        return href
    if href.startswith("/"):
        return f"https://app.pluralsight.com{href}"
    return href


def item_id(url: str | None, title: str) -> str:
    """``pluralsight:<url path>``, without the ``library/courses/`` every course shares."""
    path = urlparse(url).path.strip("/") if url else ""
    if not path:
        raise LearningError(f"{title!r} has no link, so it has no stable id")
    return "pluralsight:" + path.removeprefix(_COURSE_PATH)


def _percentage(cell: object) -> float | None:
    text = cell.get_text(strip=True)  # type: ignore[attr-defined]
    return float(text.rstrip("%")) if re.match(r"^\d+\.?\d*%$", text) else None


def _minutes(cell: object) -> int | None:
    text = cell.get_text(strip=True)  # type: ignore[attr-defined]
    hours = re.search(r"(\d+)\s*h", text)
    minutes = re.search(r"(\d+)\s*m", text)
    if not (hours or minutes):
        return None
    return (int(hours.group(1)) * 60 if hours else 0) + (int(minutes.group(1)) if minutes else 0)


def _date(cell: object) -> dt.date | None:
    element = cell.find("time")  # type: ignore[attr-defined]
    stamp = element.get("datetime", "") if element else ""
    match = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", stamp)
    if not match:
        return None
    month, day, year = (int(g) for g in match.groups())
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None
