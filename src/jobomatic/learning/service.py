"""Learning use cases: compare an import with what is stored, merge it, and compute totals.

Depends only on the model and ports: no files, no network.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from jobomatic.learning.model import (
    EnrichResult,
    FieldChange,
    ImportPlan,
    ItemChange,
    Kind,
    LearningItem,
    Rekeyed,
    SourceBatch,
    SummarySource,
    TopicRules,
)
from jobomatic.learning.ports import LearningEnricher, LearningRepository, LearningSource

# Fields the provider's export is allowed to refresh on an item already stored.
_REFRESHED = ("title", "url", "duration_minutes", "parent_id")


class LearningError(Exception):
    """An import or the stored data cannot be used (ADR 0007: fail loud)."""


def plan_import(
    batch: SourceBatch, stored: list[LearningItem], rules: TopicRules | None = None
) -> ImportPlan:
    """Work out what importing ``batch`` would do. Items are matched by id, never by title.

    * An id not stored yet is new. Its topics come from the rules when the source gave none.
    * An id already stored keeps its completion date, its topics and any summary a person or an
      LLM wrote. The provider may refresh the title, link, duration and parent.
    * A stored item the batch no longer lists is reported as absent and kept.
    * One exception to "never by title": an incoming id that is not stored, and a stored item
      of the same provider and kind with the same title whose own id the batch does not
      contain, are treated as one item whose id changed. Providers do change the link a
      course is listed under. It is reported as re-keyed and never silent.
    """
    seen: set[str] = set()
    for item in batch.items:
        if item.id in seen:
            raise LearningError(f"{batch.source}: the id {item.id!r} appears twice")
        seen.add(item.id)

    by_id = {i.id: i for i in stored}
    rekeyed: list[Rekeyed] = []
    claimed: set[str] = set()
    new: list[LearningItem] = []
    changed: list[ItemChange] = []
    unchanged = 0
    unclassified: list[str] = []
    merged = list(stored)
    position = {i.id: n for n, i in enumerate(merged)}

    for incoming in batch.items:
        current = by_id.get(incoming.id)
        if current is None:
            bridged = _same_title(incoming, stored, seen, claimed)
            if bridged is not None:
                claimed.add(bridged.id)
                rekeyed.append(Rekeyed(bridged.id, incoming.id, bridged.title))
                renamed = bridged.model_copy(update={"id": incoming.id})
                merged[position[bridged.id]] = renamed
                position[incoming.id] = position[bridged.id]
                current = renamed
        if current is None:
            item = incoming
            if not item.topics and rules is not None:
                item = item.model_copy(update={"topics": rules.classify(item.title)})
            if not item.topics:
                unclassified.append(item.id)
            new.append(item)
            continue
        updated, fields = _merge(current, incoming)
        if fields:
            changed.append(ItemChange(current.id, current.title, fields))
            merged[position[current.id]] = updated
        else:
            unchanged += 1

    providers = {i.provider for i in batch.items}
    absent = [
        i.id for i in stored if i.provider in providers and i.id not in seen and i.id not in claimed
    ]
    return ImportPlan(new, changed, unchanged, absent, unclassified, merged + new, rekeyed)


def _norm_title(title: str) -> str:
    return " ".join(title.lower().split())


def _same_title(
    incoming: LearningItem, stored: list[LearningItem], in_batch: set[str], claimed: set[str]
) -> LearningItem | None:
    for candidate in stored:
        if (
            candidate.provider is incoming.provider
            and candidate.kind is incoming.kind
            and candidate.id not in in_batch
            and candidate.id not in claimed
            and _norm_title(candidate.title) == _norm_title(incoming.title)
        ):
            return candidate
    return None


def _merge(stored: LearningItem, incoming: LearningItem) -> tuple[LearningItem, list[FieldChange]]:
    updates: dict[str, object] = {}
    for name in _REFRESHED:
        new_value = getattr(incoming, name)
        if new_value is not None and new_value != getattr(stored, name):
            updates[name] = new_value
    if stored.completed_on is None and incoming.completed_on is not None:
        updates["completed_on"] = incoming.completed_on
    if not stored.topics and incoming.topics:
        updates["topics"] = incoming.topics
    written_by_us = stored.summary and stored.summary_source in (
        SummarySource.MANUAL,
        SummarySource.GENERATED,
    )
    if incoming.summary and not written_by_us and incoming.summary != stored.summary:
        updates["summary"] = incoming.summary
        updates["summary_source"] = incoming.summary_source
    fields = [
        FieldChange(n, getattr(stored, n), v) for n, v in updates.items() if n != "summary_source"
    ]
    return (stored.model_copy(update=updates) if updates else stored), fields


def run_import(
    source: LearningSource,
    repo: LearningRepository,
    rules: TopicRules | None,
    *,
    apply: bool,
) -> tuple[SourceBatch, ImportPlan]:
    """Read ``source`` and compare it with the store; write the result only when ``apply``."""
    batch = source.read()
    plan = plan_import(batch, repo.load(), rules)
    if apply and plan.has_changes:
        repo.save(plan.merged)
    return batch, plan


@dataclass
class TopicTotals:
    items: int = 0
    minutes: int = 0


@dataclass
class Stats:
    items: int = 0
    minutes: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    by_topic: dict[str, TopicTotals] = field(default_factory=dict)
    untopiced: int = 0


def stats(items: list[LearningItem]) -> Stats:
    """Totals computed from the items; never stored.

    Learning paths are counted as items but add no minutes, because a path's duration is the
    sum of its modules and would be counted twice.
    """
    result = Stats()
    kinds: dict[str, int] = defaultdict(int)
    for item in items:
        minutes = 0 if item.kind is Kind.LEARNING_PATH else (item.duration_minutes or 0)
        result.items += 1
        result.minutes += minutes
        kinds[item.kind.value] += 1
        for topic in item.topics or ["(no topic)"]:
            totals = result.by_topic.setdefault(topic, TopicTotals())
            totals.items += 1
            totals.minutes += minutes
        if not item.topics:
            result.untopiced += 1
    result.by_kind = dict(kinds)
    return result


def enrich_paths(items: list[LearningItem], enricher: LearningEnricher) -> EnrichResult:
    """Give learning paths their link and tell each module which path it belongs to.

    A path the enricher cannot confirm is left alone and reported. A module claimed by two
    paths keeps the first and is reported. Nothing is guessed (ADR 0017).
    """
    by_id = {i.id: i for i in items}
    linked: list[str] = []
    unresolved: list[str] = []
    claims: dict[str, str] = {}  # module id -> path id
    conflicts: list[str] = []
    module_by_path = {_module_path(i.url): i.id for i in items if i.kind is Kind.MODULE and i.url}
    for path in [i for i in items if i.kind is Kind.LEARNING_PATH]:
        found = enricher.enrich(path)
        if found is None:
            unresolved.append(path.id)
            continue
        if path.url != found.url:
            by_id[path.id] = path.model_copy(update={"url": found.url})
            linked.append(path.id)
        for module_path in found.module_paths:
            module_id = module_by_path.get(module_path)
            if module_id is None:
                continue
            if module_id in claims and claims[module_id] != path.id:
                conflicts.append(f"{module_id} is in both {claims[module_id]} and {path.id}")
                continue
            claims[module_id] = path.id
    for module_id, path_id in claims.items():
        module = by_id[module_id]
        if module.parent_id != path_id:
            by_id[module_id] = module.model_copy(update={"parent_id": path_id})
    orphans = [
        i.id for i in items if i.kind is Kind.MODULE and i.id not in claims and not i.parent_id
    ]
    updated = [by_id[i.id] for i in items]
    return EnrichResult(updated, linked, len(claims), unresolved, orphans, conflicts)


def _module_path(url: str) -> str:
    """``https://learn.microsoft.com/training/modules/x/`` -> ``/training/modules/x/``."""
    marker = "/training/modules/"
    index = url.find(marker)
    return url[index:] if index >= 0 else url
