"""Import completed learning from an export file into the vault (ADR 0017, 0028).

A dry run unless ``apply`` is given: it reads the export, compares it with what is stored and
reports what is new, changed or re-keyed. The caller supplies the file and says which provider it is
from; fetching a Microsoft Learn transcript from the network, and working out the provider from a
file name, stay in the command line, so this never contacts anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jobomatic import bootstrap
from jobomatic.commands.support import vault_write_lock
from jobomatic.learning.adapters.mslearn_transcript import MsLearnTranscriptSource
from jobomatic.learning.adapters.pluralsight_html import PluralsightHtmlSource
from jobomatic.learning.adapters.pluralsight_json import PluralsightJsonSource
from jobomatic.learning.model import ImportPlan, SourceBatch
from jobomatic.learning.ports import LearningSource
from jobomatic.learning.service import LearningError, run_import
from jobomatic.profile.service import ProfileError
from jobomatic.results import CommandResult, Message, guarded, ok

SHOWN = 12  # how many new items to list before summarising


@dataclass(frozen=True)
class ImportData:
    provider: str
    batch: SourceBatch
    plan: ImportPlan
    credential_lines: tuple[str, ...]  # what the transcript's credentials say about the profile
    applied: bool
    kept: Path | None  # where the raw export was kept, when it was saved


def source_for(provider: str, raw: Path) -> LearningSource:
    if provider == "mslearn":
        return MsLearnTranscriptSource(raw)
    if raw.suffix.lower() == ".json":
        return PluralsightJsonSource(raw)
    return PluralsightHtmlSource(raw)


def run(raw: Path, provider: str, *, apply: bool = False) -> CommandResult[ImportData]:
    """Read ``raw`` (an export from ``provider``) and report the plan; save it when ``apply``.

    Items are matched by link, never title, and a stored date, topics or summary are never
    overwritten. Saving writes the learning items and keeps a copy of the export, so a run that
    applies holds the vault write lock.
    """

    def body() -> CommandResult[ImportData]:
        try:
            return _run(raw, provider, apply)
        except LearningError as exc:
            # The learning commands have always reported this as "[ERROR] ..." on stdout.
            return CommandResult("error", messages=(Message("info", f"[ERROR] {exc}"),))

    if not apply:
        return guarded(body)
    with vault_write_lock():
        return guarded(body)


def _run(raw: Path, provider: str, apply: bool) -> CommandResult[ImportData]:
    store = bootstrap.learning_store()
    batch, plan = run_import(source_for(provider, raw), store, bootstrap.topic_rules(), apply=apply)
    kept: Path | None = None
    if apply and plan.has_changes:
        kept = bootstrap.import_archive().store(provider, raw)
    return ok(ImportData(provider, batch, plan, _credential_lines(batch), apply, kept))


def _credential_lines(batch: SourceBatch) -> tuple[str, ...]:
    """Compare certifications in the transcript with the profile. Reported, never written."""
    if not batch.credentials:
        return ()
    lines = [f"\nCredentials in the transcript: {len(batch.credentials)}"]
    try:
        certs = {c.code: c for c in bootstrap.profile_repository().load().certifications}
    except ProfileError:
        return (*lines, "  (profile not readable, so no comparison)")
    for credential in batch.credentials:
        if credential.kind != "exam" or not credential.code:
            continue
        cert = certs.get(credential.code)
        if cert is None:
            lines.append(
                f"  note: passed exam {credential.code} is not in the profile's certifications"
            )
        elif cert.status.value != "certified":
            lines.append(
                f"  note: {credential.code} was passed but the profile says {cert.status.value!r}"
            )
    return tuple(lines)


def render(data: ImportData) -> str:
    """The plan, then what was saved, or that nothing was (a dry run)."""
    batch, plan = data.batch, data.plan
    lines = [f"Source: {batch.source} ({data.provider}), {len(batch.items)} completed item(s) read"]
    lines += [f"  warning: {warning}" for warning in batch.warnings]
    if plan.new:
        lines.append(f"\nNew ({len(plan.new)}):")
        for item in plan.new[:SHOWN]:
            when = item.completed_on.isoformat() if item.completed_on else "no date"
            lines.append(
                f"  + {item.title}  [{item.kind.value}, {when}, {', '.join(item.topics) or '?'}]"
            )
        if len(plan.new) > SHOWN:
            lines.append(f"  ... and {len(plan.new) - SHOWN} more")
    if plan.rekeyed:
        lines.append(
            f"\nSame title, different id ({len(plan.rekeyed)}), kept as one item with the new id:"
        )
        lines += [f"  = {r.title}: {r.old_id} -> {r.new_id}" for r in plan.rekeyed[:SHOWN]]
        if len(plan.rekeyed) > SHOWN:
            lines.append(f"  ... and {len(plan.rekeyed) - SHOWN} more")
    if plan.changed:
        lines.append(f"\nChanged ({len(plan.changed)}):")
        for change in plan.changed:
            lines += [
                f"  ~ {change.title}: {f.name}: {f.old!r} -> {f.new!r}" for f in change.fields
            ]
    lines.append(
        f"\n{len(plan.new)} new, {len(plan.changed)} changed, {len(plan.rekeyed)} re-keyed, "
        f"{plan.unchanged} unchanged"
        + (f", {len(plan.absent)} stored but not in this export" if plan.absent else "")
    )
    if plan.unclassified:
        lines.append(f"{len(plan.unclassified)} new item(s) matched no topic rule:")
        lines += [f"  ? {item_id}" for item_id in plan.unclassified]
    lines += data.credential_lines
    if data.applied and data.kept is not None:
        lines.append(f"Saved {len(plan.new)} new item(s); the export is kept as {data.kept}")
    elif data.applied:
        lines.append("Nothing to save.")
    else:
        lines.append("\nDry run: nothing was saved. Run again with --apply to save.")
    return "\n".join(lines)
