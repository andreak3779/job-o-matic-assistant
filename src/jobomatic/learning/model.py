"""Learning history: one ``LearningItem`` per completed course, lab, module or learning path.

Pure domain code (ADR 0016, 0017): no file access, no network. Importers build items from a
provider's export; the store keeps them; ``service`` compares and merges them.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Provider(str, Enum):
    PLURALSIGHT = "pluralsight"
    MSLEARN = "mslearn"


class Kind(str, Enum):
    COURSE = "course"
    LAB = "lab"
    MODULE = "module"
    LEARNING_PATH = "learning_path"


class SummarySource(str, Enum):
    PROVIDER = "provider"  # the provider's own wording
    GENERATED = "generated"  # an LLM paraphrase
    MANUAL = "manual"  # written by hand


class LearningItem(BaseModel):
    """One completed piece of learning."""

    model_config = ConfigDict(extra="forbid")

    # Stable and namespaced by provider, so two providers can never collide:
    # ``pluralsight:<url path>`` or ``mslearn:<catalog uid>``.
    id: str
    provider: Provider
    kind: Kind
    title: str
    url: str | None = None
    completed_on: dt.date | None = None
    duration_minutes: int | None = Field(default=None, ge=0)
    topics: list[str] = Field(default_factory=list)
    summary: str | None = None
    summary_source: SummarySource | None = None
    parent_id: str | None = None  # a module's learning path
    source: str = ""  # the import it first came from, for traceability


class Credential(BaseModel):
    """A certification, exam or applied skill reported by a provider."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["certification", "exam", "applied_skill"]
    title: str
    code: str | None = None  # an exam number such as AZ-900
    earned_on: dt.date | None = None


@dataclass(frozen=True)
class SourceBatch:
    """What a source read: the completed items, any credentials, and anything odd it noticed."""

    source: str
    items: list[LearningItem]
    credentials: list[Credential] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Enrichment:
    """What a public course page told us about a learning path."""

    url: str
    module_paths: list[str]  # the modules' links, as ``/training/modules/<slug>/``


@dataclass(frozen=True)
class EnrichResult:
    items: list[LearningItem]
    linked_paths: list[str]  # path ids that got a link
    parented_modules: int
    unresolved_paths: list[str]  # path ids no page could confirm
    modules_without_parent: list[str]  # module ids no path claimed
    conflicts: list[str]  # modules claimed by more than one path


@dataclass(frozen=True)
class FieldChange:
    name: str
    old: object
    new: object


@dataclass(frozen=True)
class ItemChange:
    item_id: str
    title: str
    fields: list[FieldChange]


@dataclass(frozen=True)
class Rekeyed:
    """A stored item whose id is not in the import but whose title and kind are the same."""

    old_id: str
    new_id: str
    title: str


@dataclass(frozen=True)
class ImportPlan:
    """What importing a batch would do. Nothing is written until the plan is applied."""

    new: list[LearningItem]
    changed: list[ItemChange]
    unchanged: int
    absent: list[str]  # stored items from this provider that the batch did not contain
    unclassified: list[str]  # ids of new items no topic rule matched
    merged: list[LearningItem]  # the full item list after applying
    rekeyed: list[Rekeyed] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.new or self.changed or self.rekeyed)


@dataclass(frozen=True)
class TopicRule:
    topic: str
    keywords: tuple[str, ...]


class TopicRules:
    """Keyword rules that assign a topic from a title. The first matching rule wins.

    A keyword matches as a whole word or phrase, ignoring case, so ``sql`` does not match
    ``mysql`` but does match ``T-SQL``.
    """

    def __init__(self, rules: list[TopicRule]) -> None:
        self._rules = [
            (
                rule.topic,
                [
                    re.compile(rf"(?<![a-z0-9]){re.escape(k.lower())}(?![a-z0-9])")
                    for k in rule.keywords
                ],
            )
            for rule in rules
        ]

    def classify(self, title: str) -> list[str]:
        lowered = title.lower()
        for topic, patterns in self._rules:
            if any(p.search(lowered) for p in patterns):
                return [topic]
        return []


def hours_text(minutes: int) -> str:
    """``3796`` -> ``63 h 16 min``."""
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest:02d} min"
