"""Find evidence in the courses, labs, projects and resume for a skill or requirement (ADR 0028).

Retrieval is advisory (ADR 0012, 0019): it never changes a fit rating, and when the embedding
service is not running this says so and stops. ``sync_index`` and ``describe_report`` are shared
with the ``index build`` and ``evidence`` commands in the command line module.
"""

from __future__ import annotations

from jobomatic import bootstrap
from jobomatic.results import CommandResult, Message, guarded, ok
from jobomatic.retrieval import scoring, service
from jobomatic.retrieval.adapters.ollama import DEFAULT_EMBED_MODEL
from jobomatic.retrieval.model import BuildReport, EmbeddingUnavailable, SkillEvidence


def describe_report(report: BuildReport) -> str:
    if report.rebuilt:
        return f"Rebuilt the index: {report.total} chunks embedded."
    return (
        f"Index up to date: {report.total} chunks "
        f"({report.added} new, {report.updated} changed, {report.removed} removed, "
        f"{report.unchanged} unchanged)."
    )


def sync_index(embed_model: str, *, rebuild: bool = False) -> BuildReport:
    """Embed new or changed evidence and keep the rest (``rebuild`` starts again)."""
    index = bootstrap.retrieval_index()
    if rebuild:
        index.path.unlink(missing_ok=True)
    return service.build_index(
        bootstrap.retrieval_chunks(), bootstrap.retrieval_embedder(embed_model), index
    )


def unavailable(exc: EmbeddingUnavailable, embed_model: str) -> Message:
    """The note for a stopped embedding service, as the command line has always said it."""
    return Message(
        "log",
        f"Evidence search skipped: {exc}\n"
        f"Start Ollama and pull the model (ollama pull {embed_model}), or use --keyword-only with "
        "`search`. Fit ratings and documents do not need it.",
    )


def search(
    query: str,
    *,
    k: int = 3,
    min_score: float | None = None,
    embed_model: str = DEFAULT_EMBED_MODEL,
    kinds: frozenset[str] | None = None,
    keyword_only: bool = False,
) -> CommandResult[SkillEvidence]:
    """The closest evidence for ``query``. ``kinds`` limits what is searched (course, lab, module,
    learning_path, project, experience, story); ``keyword_only`` ranks on words alone and needs
    only an index that was built before."""
    return guarded(lambda: _search(query, k, min_score, embed_model, kinds, keyword_only))


def _search(
    query: str,
    k: int,
    min_score: float | None,
    embed_model: str,
    kinds: frozenset[str] | None,
    keyword_only: bool,
) -> CommandResult[SkillEvidence]:
    try:
        embedder = bootstrap.retrieval_embedder(embed_model)
        index = bootstrap.retrieval_index()
        messages: tuple[Message, ...] = ()
        if keyword_only:
            if not index.hashes():
                return CommandResult(
                    "error", messages=(Message("log", "No index yet; run `index build` first."),)
                )
        else:
            messages = (Message("log", describe_report(sync_index(embed_model))),)
        hits = service.search(
            index,
            query,
            embedder,
            k=k,
            min_score=scoring.DEFAULT_MIN_SCORE if min_score is None else min_score,
            semantic=not keyword_only,
            kinds=kinds,
        )
    except EmbeddingUnavailable as exc:
        return CommandResult("error", messages=(unavailable(exc, embed_model),))
    return ok(SkillEvidence(skill=query, hits=hits), messages=messages)


def render(item: SkillEvidence) -> str:
    return service.render_markdown([item])
