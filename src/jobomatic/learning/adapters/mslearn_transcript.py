"""The Microsoft Learn transcript (the share link's JSON), read into completed learning items.

Reading a saved file never touches the network. Only ``fetch_transcript`` does, and the CLI calls
it only for an explicit ``learning import --mslearn``.

The endpoint is undocumented, so the response is validated against a JSON Schema and reading
fails loudly if its shape changes (ADR 0007). Owner fields (name, contact email) are dropped
by ``sanitize`` and must never be stored.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import urllib.request
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema

from jobomatic.learning.model import (
    Credential,
    Kind,
    LearningItem,
    Provider,
    SourceBatch,
    SummarySource,
)
from jobomatic.learning.service import LearningError

_ENDPOINT = "https://learn.microsoft.com/api/profiles/transcript/share/{share_id}"
_SITE = "https://learn.microsoft.com"
OWNER_FIELDS = ("userName", "contactEmail")


def _schema() -> dict[str, Any]:
    text = resources.files("jobomatic.learning").joinpath("mslearn_transcript.schema.json")
    return dict(json.loads(text.read_text("utf-8")))


def sanitize(data: dict[str, Any]) -> dict[str, Any]:
    """A copy of the transcript without the owner's name and contact email."""
    return {k: v for k, v in data.items() if k not in OWNER_FIELDS}


def fetch_transcript(share_id: str, opener: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Download the transcript. The only network call in the learning module.

    ``opener`` is looked up when called, not when defined, so tests can replace it.
    """
    opener = opener or urllib.request.urlopen
    if not re.fullmatch(r"[A-Za-z0-9_-]+", share_id):
        raise LearningError("the Microsoft Learn share id has unexpected characters")
    request = urllib.request.Request(
        _ENDPOINT.format(share_id=share_id), headers={"Accept": "application/json"}
    )
    try:
        with opener(request, timeout=30) as response:
            data = json.load(response)
    except (OSError, ValueError) as exc:
        raise LearningError(f"could not fetch the Microsoft Learn transcript: {exc}") from exc
    if not isinstance(data, dict):
        raise LearningError("the Microsoft Learn transcript is not a JSON object")
    return data


class MsLearnTranscriptSource:
    """``LearningSource`` for a saved transcript file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> SourceBatch:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise LearningError(f"cannot read {self._path}: {exc}") from exc
        return parse_transcript(data, self._path.name)


def parse_transcript(data: Any, source: str) -> SourceBatch:
    errors = sorted(
        jsonschema.Draft202012Validator(_schema()).iter_errors(data), key=lambda e: list(e.path)
    )
    if errors:
        lines = [
            f"  {'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in errors[:8]
        ]
        raise LearningError(
            f"{source}: this does not look like the Microsoft Learn transcript I know how to "
            "read (Microsoft may have changed it). Nothing was imported.\n" + "\n".join(lines)
        )

    items: list[LearningItem] = []
    warnings: list[str] = []
    for key, kind in (
        ("modulesCompleted", Kind.MODULE),
        ("learningPathsCompleted", Kind.LEARNING_PATH),
    ):
        for raw in data[key]:
            items.append(
                LearningItem(
                    id=f"mslearn:{raw['uid']}",
                    provider=Provider.MSLEARN,
                    kind=kind,
                    title=raw["title"].strip(),
                    url=_absolute(raw.get("url")),
                    completed_on=_date(raw["completedOn"]),
                    duration_minutes=raw["durationInMinutes"],
                    summary=_text(raw.get("description")),
                    summary_source=SummarySource.PROVIDER if raw.get("description") else None,
                    source=source,
                )
            )
    for total_key, key in (
        ("totalModulesCompleted", "modulesCompleted"),
        ("totalLearningPathsCompleted", "learningPathsCompleted"),
    ):
        if total_key in data and data[total_key] != len(data[key]):
            warnings.append(f"{total_key} says {data[total_key]} but {len(data[key])} are listed")
    return SourceBatch(source, items, _credentials(data), warnings)


def _credentials(data: dict[str, Any]) -> list[Credential]:
    found: list[Credential] = []
    cert_data = data.get("certificationData") or {}
    for key in ("activeCertifications", "historicalCertifications"):
        for raw in cert_data.get(key, []):
            found.append(
                Credential(
                    kind="certification", title=raw["name"], earned_on=_date(raw.get("dateEarned"))
                )
            )
    for raw in cert_data.get("passedExams", []):
        found.append(
            Credential(
                kind="exam",
                title=raw["examTitle"],
                code=raw["examNumber"],
                earned_on=_date(raw.get("examDateTaken")),
            )
        )
    for raw in (data.get("appliedSkillsData") or {}).get("appliedSkillsCredentials", []):
        found.append(
            Credential(
                kind="applied_skill", title=raw["title"], earned_on=_date(raw.get("awardedOn"))
            )
        )
    return found


def _absolute(url: str | None) -> str | None:
    if not url:
        return None
    return url if url.startswith("http") else _SITE + url


def _text(description: str | None) -> str | None:
    if not description:
        return None
    return re.sub(r"\s+", " ", html.unescape(description)).strip() or None


def _date(stamp: str | None) -> dt.date | None:
    if not stamp:
        return None
    try:
        return dt.date.fromisoformat(stamp[:10])
    except ValueError:
        return None
