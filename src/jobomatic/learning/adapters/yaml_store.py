"""Learning items kept as YAML in the vault, plus the archive of raw exports and topic rules."""

from __future__ import annotations

import shutil
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter, ValidationError

from jobomatic import yamlio
from jobomatic.learning.model import LearningItem, TopicRule, TopicRules
from jobomatic.learning.service import LearningError

ITEMS_FILE = "items.yaml"
TOPICS_FILE = "topics.yaml"


class YamlLearningStore:
    """``LearningRepository`` backed by ``<profile>/learning/items.yaml``.

    A missing file means nothing has been imported yet, so it reads as empty: the store is
    rebuilt by importing the raw exports again, which are archived.
    """

    def __init__(self, profile_dir: Path) -> None:
        self._dir = profile_dir / "learning"

    @property
    def path(self) -> Path:
        return self._dir / ITEMS_FILE

    def load(self) -> list[LearningItem]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        try:
            data = yamlio.load(text) or {}
        except yaml.YAMLError as exc:
            raise LearningError(f"{self.path}: not valid YAML: {exc}") from exc
        if not isinstance(data, dict) or set(data) - {"items"}:
            raise LearningError(f"{self.path}: expected a mapping with only the key 'items'")
        try:
            items = TypeAdapter(list[LearningItem]).validate_python(data.get("items", []))
        except ValidationError as exc:
            lines = [f"{self.path}: invalid"]
            for err in exc.errors():
                where = "items" + "".join(
                    f"[{p}]" if isinstance(p, int) else f".{p}" for p in err["loc"]
                )
                lines.append(f"  {where}: {err['msg']}")
            raise LearningError("\n".join(lines)) from exc
        ids = [i.id for i in items]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise LearningError(f"{self.path}: duplicate ids {dupes}")
        return items

    def save(self, items: list[LearningItem]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        rows = [yamlio.plain(i.model_dump(exclude_defaults=True)) for i in items]
        self.path.write_text(yamlio.dump({"items": rows}), encoding="utf-8")


class FileImportArchive:
    """``ImportArchive``: copies a raw export to ``imports/<provider>/<date>.<ext>``."""

    def __init__(self, imports_dir: Path, today: date | None = None) -> None:
        self._dir = imports_dir
        self._today = today

    def folder(self, provider: str) -> Path:
        """Where this provider's raw exports (and cached pages) are kept."""
        return self._dir / provider

    def store(self, provider: str, raw: Path) -> Path:
        folder = self._dir / provider
        folder.mkdir(parents=True, exist_ok=True)
        content = raw.read_bytes()
        for kept in sorted(folder.glob(f"*{raw.suffix}")):
            if kept.read_bytes() == content:
                return kept  # this exact export is already kept, under whatever date
        stamp = (self._today or date.today()).isoformat()
        target = folder / f"{stamp}{raw.suffix}"
        n = 1
        while target.exists():
            n += 1
            target = folder / f"{stamp}-{n}{raw.suffix}"
        shutil.copyfile(raw, target)
        return target


def load_topic_rules(profile_dir: Path | None = None) -> TopicRules:
    """The topic rules: the vault's ``learning/topics.yaml`` if there is one, else the default."""
    override = (profile_dir / "learning" / TOPICS_FILE) if profile_dir else None
    if override is not None and override.is_file():
        text, origin = override.read_text(encoding="utf-8"), str(override)
    else:
        text = resources.files("jobomatic.learning").joinpath(TOPICS_FILE).read_text("utf-8")
        origin = "the default topics.yaml"
    try:
        data: Any = yamlio.load(text)
        rules = [TopicRule(r["topic"], tuple(r["keywords"])) for r in data["topics"]]
    except (yaml.YAMLError, KeyError, TypeError) as exc:
        raise LearningError(f"{origin}: expected 'topics: [{{topic, keywords}}]': {exc}") from exc
    return TopicRules(rules)
