"""``index build``, ``search`` and ``evidence``: the evidence index and the commands that use it.

A thin driving adapter over ``jobomatic.retrieval``; wiring comes from ``jobomatic.bootstrap``.
Retrieval is advisory (ADR 0012, 0019). When the embedding service is not running these commands
say so and stop; the fit rating and the document generators never depend on it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from jobomatic import bootstrap
from jobomatic.learning.service import LearningError
from jobomatic.privacy.guard import DEFAULT_PII_PATTERNS
from jobomatic.profile.service import ProfileError
from jobomatic.retrieval import scoring, service
from jobomatic.retrieval.adapters.ollama import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_EMBED_MODEL,
    ollama_chat,
)
from jobomatic.retrieval.model import (
    BuildReport,
    EmbeddingUnavailable,
    RetrievalError,
    SkillEvidence,
)

COMMANDS = ("index", "search", "evidence")


def register(subparsers: Any) -> None:
    index = subparsers.add_parser("index", help="The evidence index (rebuildable, advisory)")
    index_sub = index.add_subparsers(dest="index_command", required=True)
    build = index_sub.add_parser("build", help="Embed new or changed evidence; keep the rest")
    build.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL)
    build.add_argument("--rebuild", action="store_true", help="discard the index and start again")

    search = subparsers.add_parser("search", help="Find evidence for a phrase")
    search.add_argument("query", help="a skill or requirement, in quotes")
    _shared_options(search)
    search.add_argument(
        "--kind",
        action="append",
        help="only this kind (course, lab, module, learning_path, project, experience, story); "
        "repeat for several",
    )
    search.add_argument(
        "--keyword-only", action="store_true", help="rank on words alone; no embedding service"
    )

    evidence = subparsers.add_parser(
        "evidence",
        help="Find the closest evidence in your courses, projects and resume for a skill or JD",
    )
    evidence.add_argument(
        "target",
        help="a skill or requirement in quotes, or the path to a job description markdown file",
    )
    _shared_options(evidence)
    evidence.add_argument(
        "--all",
        action="store_true",
        help="for a JD, also show requirements the fit engine already grounds",
    )
    evidence.add_argument(
        "--explain",
        action="store_true",
        help="add a model-written rationale (sends only course/project text to the chat model)",
    )
    evidence.add_argument("--chat-model", default=DEFAULT_CHAT_MODEL)


def _shared_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--k", type=int, default=3, help="results per requirement (default 3)")
    parser.add_argument(
        "--min-score",
        type=float,
        default=scoring.DEFAULT_MIN_SCORE,
        help=f"drop matches scoring below this (default {scoring.DEFAULT_MIN_SCORE})",
    )
    parser.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL)


def _describe(report: BuildReport) -> str:
    if report.rebuilt:
        head = f"Rebuilt the index: {report.total} chunks embedded."
    else:
        head = (
            f"Index up to date: {report.total} chunks "
            f"({report.added} new, {report.updated} changed, {report.removed} removed, "
            f"{report.unchanged} unchanged)."
        )
    return head


def _sync(embed_model: str, *, rebuild: bool = False) -> BuildReport:
    index = bootstrap.retrieval_index()
    if rebuild:
        index.path.unlink(missing_ok=True)
    return service.build_index(
        bootstrap.retrieval_chunks(), bootstrap.retrieval_embedder(embed_model), index
    )


def _pii_scan(text: str) -> list[str]:
    return [name for name, pattern in DEFAULT_PII_PATTERNS.items() if pattern.search(text)]


def _skills_for(target: str, include_all: bool) -> list[tuple[str, str]]:
    path = Path(target).expanduser()
    if not path.is_file():
        return [(target.strip(), "")]
    from jobomatic.fit.parser import parse_jd

    parsed = parse_jd(path.read_text(encoding="utf-8"))
    try:
        profile = bootstrap.load_profile()
    except ProfileError as exc:
        print(f"[note] fit engine not used ({exc}); listing every requirement", file=sys.stderr)
        return [(s, "") for s in parsed.required_for_rating]
    from jobomatic.fit.engine import rate_parsed_jd

    fit = rate_parsed_jd(parsed, profile)
    matches = fit.required if include_all else fit.ungrounded_required
    return [(m.skill, m.status) for m in matches]


def run(args: argparse.Namespace) -> int:
    try:
        if args.command == "index":
            report = _sync(args.embed_model, rebuild=args.rebuild)
            print(_describe(report))
            return 0
        if args.command == "search":
            return _search(args)
        return _evidence(args)
    except EmbeddingUnavailable as exc:
        print(f"Evidence search skipped: {exc}", file=sys.stderr)
        print(
            "Start Ollama and pull the model (ollama pull "
            f"{getattr(args, 'embed_model', DEFAULT_EMBED_MODEL)}), or use --keyword-only with "
            "`search`. Fit ratings and documents do not need it.",
            file=sys.stderr,
        )
        return 1
    except (RetrievalError, ProfileError, LearningError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _search(args: argparse.Namespace) -> int:
    embedder = bootstrap.retrieval_embedder(args.embed_model)
    index = bootstrap.retrieval_index()
    if args.keyword_only:
        if not index.hashes():
            print("No index yet; run `index build` first.", file=sys.stderr)
            return 1
    else:
        print(_describe(_sync(args.embed_model)), file=sys.stderr)
    hits = service.search(
        index,
        args.query,
        embedder,
        k=args.k,
        min_score=args.min_score,
        semantic=not args.keyword_only,
        kinds=frozenset(args.kind) if args.kind else None,
    )
    item = SkillEvidence(skill=args.query, hits=hits)
    print(service.render_markdown([item]))
    return 0


def _evidence(args: argparse.Namespace) -> int:
    embedder = bootstrap.retrieval_embedder(args.embed_model)
    print(_describe(_sync(args.embed_model)), file=sys.stderr)
    skills = _skills_for(args.target, args.all)
    if not skills:
        print("No requirements to look up (the fit engine already grounds them all; use --all).")
        return 0
    chat = ollama_chat(args.chat_model) if args.explain else None
    results = service.gather(
        skills,
        bootstrap.retrieval_index(),
        embedder,
        k=args.k,
        min_score=args.min_score,
        chat=chat,
        pii_scan=_pii_scan,
    )
    print(service.render_markdown(results))
    return 0
