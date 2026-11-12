"""``learning`` subcommands: import completed learning, list it, look it up, and total it.

A thin driving adapter over ``jobomatic.learning``; wiring comes from ``jobomatic.bootstrap``.
Only ``learning import --mslearn`` ever contacts Microsoft, and only when you ask for it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import tempfile
from pathlib import Path

from jobomatic import bootstrap
from jobomatic.commands import learning_import
from jobomatic.learning.adapters.mslearn_transcript import (
    fetch_transcript,
    sanitize,
)
from jobomatic.learning.adapters.pluralsight_json import (
    looks_like_pluralsight_history,
)
from jobomatic.learning.model import (
    LearningItem,
    SummarySource,
    hours_text,
)
from jobomatic.learning.service import LearningError, stats
from jobomatic.results import emit

COMMAND = "learning"
_SHOWN = 12  # how many new items to list before summarising


def register(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    learning = subparsers.add_parser("learning", help="Completed courses, labs and modules")
    sub = learning.add_subparsers(dest="learning_command", required=True)

    imp = sub.add_parser("import", help="Import an export; a dry run unless --apply is given")
    imp.add_argument(
        "file",
        nargs="?",
        type=Path,
        help="A Pluralsight .html or import .json, or a Learn transcript .json",
    )
    imp.add_argument("--provider", choices=("auto", "pluralsight", "mslearn"), default="auto")
    imp.add_argument(
        "--mslearn",
        action="store_true",
        help="Fetch a fresh Microsoft Learn transcript (the only command that uses the network)",
    )
    imp.add_argument("--apply", action="store_true", help="Write the result (default: dry run)")

    ls = sub.add_parser("list", help="List imported items")
    ls.add_argument("--provider", choices=("pluralsight", "mslearn"))
    ls.add_argument("--kind", choices=("course", "lab", "module", "learning_path"))
    ls.add_argument("--topic")

    lookup = sub.add_parser("lookup", help="Find items by title (case-insensitive, partial)")
    lookup.add_argument("titles", nargs="+")

    sub.add_parser("stats", help="Totals and per-topic hours, computed from the items")

    summ = sub.add_parser("summarize", help="Items that have no summary yet")
    summ.add_argument("--missing", action="store_true", required=True)
    summ.add_argument(
        "--from-json",
        type=Path,
        help="Save summaries from a JSON file {id: text}, marked as generated (not provider text)",
    )

    sub.add_parser(
        "enrich",
        help="Link learning paths and tie modules to their path, from public Learn pages "
        "(fetches pages that are not cached yet)",
    )

    seturl = sub.add_parser("set-url", help="Save a confirmed link for an item")
    seturl.add_argument("item_id")
    seturl.add_argument("url")

    setdate = sub.add_parser(
        "set-date",
        help="Correct an item's completion date (an import never overwrites a stored date)",
    )
    setdate.add_argument("item_id")
    setdate.add_argument("date", help="YYYY-MM-DD")


def run(args: argparse.Namespace) -> int:
    try:
        command = args.learning_command
        if command == "import":
            return _import(args)
        if command == "list":
            return _list(args)
        if command == "lookup":
            return _lookup(args.titles)
        if command == "stats":
            return _stats()
        if command == "enrich":
            return _enrich()
        if command == "summarize":
            return _summarize(args.from_json)
        if command == "set-date":
            return _set_date(args.item_id, args.date)
        return _set_url(args.item_id, args.url)
    except LearningError as exc:
        print(f"[ERROR] {exc}")
        return 1


# -- import -----------------------------------------------------------------------------------


def _import(args: argparse.Namespace) -> int:
    if args.mslearn == (args.file is not None):
        raise LearningError("give either an export file or --mslearn, not both and not neither")
    with tempfile.TemporaryDirectory() as scratch:
        provider, raw = _prepare(args, Path(scratch))
        result = learning_import.run(raw, provider, apply=args.apply)
        return emit(result, learning_import.render)


def _json_provider(path: Path) -> str:
    """A .json export is a Pluralsight import file or a Learn transcript; tell them apart."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LearningError(f"{path}: not readable JSON: {exc}") from exc
    return "pluralsight" if looks_like_pluralsight_history(data) else "mslearn"


def _prepare(args: argparse.Namespace, scratch: Path) -> tuple[str, Path]:
    """Return (provider, file to read). Microsoft Learn data is cleaned of owner fields first."""
    if args.mslearn:
        data = sanitize(fetch_transcript(bootstrap.mslearn_share_id()))
        raw = scratch / "transcript.json"
        raw.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return "mslearn", raw
    path: Path = args.file
    if not path.is_file():
        raise LearningError(f"{path}: no such file")
    provider = args.provider
    if provider == "auto":
        suffix = path.suffix.lower()
        provider = (
            _json_provider(path)
            if suffix == ".json"
            else "pluralsight"
            if suffix in (".html", ".htm")
            else ""
        )
        if not provider:
            raise LearningError(f"{path}: cannot tell the provider from the name; use --provider")
    if provider == "mslearn":
        try:
            data = sanitize(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise LearningError(f"{path}: not readable JSON: {exc}") from exc
        raw = scratch / path.name
        raw.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return provider, raw
    return provider, path


# -- reading ------------------------------------------------------------------------------------


def _list(args: argparse.Namespace) -> int:
    for item in bootstrap.learning_store().load():
        if args.provider and item.provider.value != args.provider:
            continue
        if args.kind and item.kind.value != args.kind:
            continue
        if args.topic and args.topic not in item.topics:
            continue
        print(_line(item))
    return 0


def _line(item: LearningItem) -> str:
    when = item.completed_on.isoformat() if item.completed_on else "          "
    minutes = f"{item.duration_minutes:>4} min" if item.duration_minutes is not None else "       ?"
    return f"{when}  {minutes}  {item.kind.value:<13} {item.title}  [{', '.join(item.topics)}]"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _lookup(titles: list[str]) -> int:
    items = bootstrap.learning_store().load()
    missing = 0
    for wanted in titles:
        hits = [i for i in items if _norm(wanted) in _norm(i.title)]
        if not hits:
            print(f"not found: {wanted}")
            missing += 1
        for item in hits:
            print(_line(item))
    return 1 if missing == len(titles) else 0


def _stats() -> int:
    items = bootstrap.learning_store().load()
    totals = stats(items)
    print(f"{totals.items} completed items, {hours_text(totals.minutes)} of learning time")
    print("  " + ", ".join(f"{n} {kind}" for kind, n in sorted(totals.by_kind.items())))
    print("\nBy topic:")
    ranked = sorted(totals.by_topic.items(), key=lambda kv: (-kv[1].items, kv[0]))
    for topic, t in ranked:
        print(f"  {t.items:>4}  {hours_text(t.minutes):>11}  {topic}")
    return 0


# -- summaries and links ---------------------------------------------------------------------------


def _summarize(from_json: Path | None) -> int:
    store = bootstrap.learning_store()
    items = store.load()
    if from_json is None:
        missing = [i for i in items if not i.summary]
        for item in missing:
            print(f"{item.id}\t{item.title}")
        print(f"{len(missing)} item(s) without a summary")
        return 0
    try:
        written = json.loads(from_json.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LearningError(f"{from_json}: not readable JSON: {exc}") from exc
    known = {i.id for i in items}
    unknown = sorted(set(written) - known)
    if unknown:
        raise LearningError(f"unknown item ids in {from_json.name}: {unknown}")
    updated = []
    for item in items:
        text = written.get(item.id)
        if text and not item.summary:  # never overwrite a provider, manual or earlier summary
            item = item.model_copy(
                update={"summary": str(text), "summary_source": SummarySource.GENERATED}
            )
        updated.append(item)
    store.save(updated)
    print(f"Saved {sum(1 for i in items if written.get(i.id) and not i.summary)} summaries")
    return 0


def _enrich() -> int:
    from jobomatic.learning.adapters.mslearn_page import MsLearnPageEnricher
    from jobomatic.learning.service import enrich_paths

    store = bootstrap.learning_store()
    items = store.load()
    cache = bootstrap.import_archive().folder("mslearn") / "pages"
    result = enrich_paths(items, MsLearnPageEnricher(cache))
    store.save(result.items)
    print(
        f"{len(result.linked_paths)} path(s) linked, {result.parented_modules} module(s) "
        "tied to a path"
    )
    for path_id in result.unresolved_paths:
        print(f"  could not confirm a page for {path_id}")
    for conflict in result.conflicts:
        print(f"  conflict: {conflict}")
    if result.modules_without_parent:
        print(f"{len(result.modules_without_parent)} module(s) are in none of the linked paths:")
        for module_id in result.modules_without_parent[:_SHOWN]:
            print(f"  ? {module_id}")
        if len(result.modules_without_parent) > _SHOWN:
            print(f"  ... and {len(result.modules_without_parent) - _SHOWN} more")
    return 0


def _set_url(item_id: str, url: str) -> int:
    if not url.startswith("https://"):
        raise LearningError("the link must start with https://")
    store = bootstrap.learning_store()
    items = store.load()
    if item_id not in {i.id for i in items}:
        raise LearningError(f"no item with id {item_id!r}")
    store.save([i.model_copy(update={"url": url}) if i.id == item_id else i for i in items])
    print(f"Saved the link for {item_id}")
    return 0


def _set_date(item_id: str, text: str) -> int:
    try:
        when = dt.date.fromisoformat(text)
    except ValueError as exc:
        raise LearningError(f"{text!r} is not a date; use YYYY-MM-DD") from exc
    if when > dt.date.today():
        raise LearningError(f"{text} is in the future")
    store = bootstrap.learning_store()
    items = store.load()
    current = next((i for i in items if i.id == item_id), None)
    if current is None:
        raise LearningError(f"no item with id {item_id!r}")
    store.save(
        [i.model_copy(update={"completed_on": when}) if i.id == item_id else i for i in items]
    )
    print(f"{current.title}: completed {current.completed_on or 'with no date'} -> {when}")
    return 0
