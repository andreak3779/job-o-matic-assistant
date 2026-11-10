"""Evidence retrieval use cases: build the index, search it, explain a result.

Advisory only (ADR 0012, 0019): nothing here changes the fit rating. The core talks to the
embedding model and the index through ports, so it runs against fakes in tests.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable, Sequence

from jobomatic.retrieval import scoring
from jobomatic.retrieval.model import (
    BuildReport,
    Chunk,
    Hit,
    RetrievalError,
    SkillEvidence,
)
from jobomatic.retrieval.ports import ChatFn, Embedder, IndexEntry, IndexStore

# ── index ────────────────────────────────────────────────────────────────────


def normalize(vector: Sequence[float]) -> list[float]:
    """Scale to unit length, so a dot product is the cosine similarity."""
    length = math.sqrt(sum(x * x for x in vector))
    return [x / length for x in vector] if length else list(vector)


def text_hash(chunk: Chunk) -> str:
    """What decides whether a stored vector is still right: the embedded text only."""
    return hashlib.sha256(chunk.text.encode()).hexdigest()


def build_index(chunks: Sequence[Chunk], embedder: Embedder, store: IndexStore) -> BuildReport:
    """Bring the index in line with ``chunks``, embedding only the text that changed.

    A chunk whose text hash is unchanged keeps its vector (its title, status and link are still
    refreshed). Stored chunks that are no longer in ``chunks`` are removed. If the embedding model
    or the vector size changed, every stored vector is wrong, so the index starts again.
    """
    ids = [c.id for c in chunks]
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise RetrievalError(f"chunk ids must be unique; repeated: {dupes[:5]}")

    stored = store.hashes()
    fingerprint = store.fingerprint()
    model_changed = fingerprint is not None and fingerprint[0] != embedder.model
    if model_changed:
        stored = {}

    hashes = {c.id: text_hash(c) for c in chunks}
    need_vector = [c for c in chunks if stored.get(c.id) != hashes[c.id]]
    vectors: dict[str, list[float]] = {}
    if need_vector:
        embedded = embedder.embed([c.text for c in need_vector], query=False)
        if len(embedded) != len(need_vector):
            raise RetrievalError("the embedding service returned the wrong number of vectors")
        vectors = {c.id: normalize(v) for c, v in zip(need_vector, embedded, strict=True)}

    dimensions = len(next(iter(vectors.values()))) if vectors else (fingerprint or ("", 0))[1]
    size_changed = bool(vectors) and fingerprint is not None and fingerprint[1] != dimensions
    reset = model_changed or size_changed
    if reset and len(vectors) != len(chunks):
        # Only some vectors were computed, so keeping the rest would mix two models.
        raise RetrievalError("the embedding model changed; rebuild the whole index")

    entries = [IndexEntry(c, hashes[c.id], vectors.get(c.id)) for c in chunks]
    remove = [] if reset else [i for i in stored if i not in hashes]
    # Always applied: it is cheap, and it keeps titles, statuses and links current.
    store.apply(entries, remove, model=embedder.model, dimensions=dimensions, reset=reset)

    added = sum(1 for c in need_vector if c.id not in stored)
    updated = len(need_vector) - added
    return BuildReport(
        added=added,
        updated=updated,
        removed=len(remove),
        unchanged=len(chunks) - len(need_vector),
        rebuilt=reset,
    )


# ── search ───────────────────────────────────────────────────────────────────


def search(
    store: IndexStore,
    query: str,
    embedder: Embedder,
    *,
    k: int = 3,
    keyword_weight: float = scoring.DEFAULT_KEYWORD_WEIGHT,
    min_score: float = scoring.DEFAULT_MIN_SCORE,
    semantic: bool = True,
    kinds: frozenset[str] | None = None,
) -> list[Hit]:
    """Top ``k`` chunks for ``query``.

    The store supplies the vector neighbours (every chunk, in order of closeness: at a few
    hundred chunks an exhaustive search is exact and fast) and ``scoring.rank`` decides the order
    and the cutoff. ``semantic=False`` skips the embedding call and ranks on keywords alone.
    """
    if semantic:
        vector = normalize(embedder.embed([query], query=True)[0])
        candidates = store.nearest(vector, limit=len(store.hashes()), kinds=kinds)
    else:
        candidates = [(c, 0.0) for c in store.chunks(kinds)]
    return scoring.rank(
        query,
        candidates,
        k=k,
        min_score=min_score,
        keyword_weight=keyword_weight,
        semantic=semantic,
    )


# ── rationale (optional, may call a cloud model) ─────────────────────────────

PiiScan = Callable[[str], list[str]]
_CITATION = re.compile(r"\[(\d+)\]")


def cloud_safe_hits(hits: Sequence[Hit]) -> list[Hit]:
    """Hits whose text may leave the machine: courses, labs and projects, never private prose."""
    return [h for h in hits if not h.chunk.local_only]


def build_prompt(skill: str, hits: Sequence[Hit]) -> str:
    evidence = "\n".join(
        f"[{i}] ({h.chunk.kind}{', ' + h.chunk.status if h.chunk.status else ''}) "
        f"{h.chunk.title} — {h.chunk.text}"
        for i, h in enumerate(hits, start=1)
    )
    return (
        "You are checking whether a candidate's record supports a job requirement.\n"
        f"Requirement: {skill}\n\n"
        f"Evidence (the only facts you may use):\n{evidence}\n\n"
        "In at most two sentences, say how the evidence relates to the requirement and cite "
        "the evidence by number, like [1]. Do not add facts, tools, dates or years that are "
        "not in the evidence. Describe a course or lab as coursework or a hands-on lab, never "
        "as work experience or production use, and say if a course is still in progress. If the "
        "evidence only partly covers the requirement, say what is missing. If none of it "
        "applies, reply exactly: No direct evidence."
    )


def explain(
    skill: str, hits: Sequence[Hit], chat: ChatFn, pii_scan: PiiScan
) -> tuple[str | None, str | None]:
    """``(rationale, note)``: one grounded sentence or two, or ``(None, why not)``.

    Only cloud-safe hits are sent. The prompt is scanned for personal data before the call
    (``pii_scan`` returns the names of the patterns that matched), and a reply is kept only if
    every citation points at evidence that was sent.
    """
    safe = cloud_safe_hits(hits)
    if not safe:
        return None, "no cloud-safe evidence to explain"
    prompt = build_prompt(skill, safe)
    findings = pii_scan(prompt)
    if findings:
        return None, f"not sent: prompt matched personal-data pattern(s) {findings}"
    try:
        reply = chat(prompt)
    except RetrievalError as exc:
        return None, f"rationale unavailable: {exc}"
    cited = {int(n) for n in _CITATION.findall(reply)}
    if reply.strip().rstrip(".").lower() == "no direct evidence":
        return "No direct evidence.", None
    if not cited:
        return None, "rationale discarded: it cited no evidence"
    if not cited <= set(range(1, len(safe) + 1)):
        return None, "rationale discarded: it cited evidence that was not provided"
    return reply, None


# ── driver and rendering ─────────────────────────────────────────────────────


def gather(
    skills: Sequence[tuple[str, str]],
    store: IndexStore,
    embedder: Embedder,
    *,
    k: int = 3,
    min_score: float = scoring.DEFAULT_MIN_SCORE,
    chat: ChatFn | None = None,
    pii_scan: PiiScan | None = None,
) -> list[SkillEvidence]:
    """Evidence for each ``(skill, engine_status)``; a rationale only when ``chat`` is given."""
    results: list[SkillEvidence] = []
    for skill, status in skills:
        item = SkillEvidence(skill=skill, engine_status=status)
        item.hits = search(store, skill, embedder, k=k, min_score=min_score)
        if chat is not None and item.hits:
            item.rationale, item.rationale_note = explain(
                skill, item.hits, chat, pii_scan or (lambda _text: [])
            )
        results.append(item)
    return results


_LABELS = {
    "course": "course",
    "lab": "lab",
    "module": "Microsoft Learn module",
    "learning_path": "Microsoft Learn path",
    "project": "project",
    "experience": "resume",
    "story": "interview story",
}


def _hit_line(hit: Hit) -> str:
    label = _LABELS.get(hit.chunk.kind, hit.chunk.kind)
    status = f", {hit.chunk.status}" if hit.chunk.status else ""
    return f"{hit.chunk.title} ({label}{status}; score {hit.score:.2f})"


def render_markdown(results: Sequence[SkillEvidence]) -> str:
    lines = [
        "# Evidence retrieval (advisory)",
        "",
        "Closest evidence in your own record for each requirement. The fit rating is "
        "computed separately and is not changed by this list. Check each match before "
        "you claim it: similarity is not proof of experience.",
        "",
    ]
    for item in results:
        header = f"## {item.skill}"
        if item.engine_status:
            header += f" — fit engine: {item.engine_status}"
        lines += [header, ""]
        if not item.hits:
            lines += ["No evidence found above the score cutoff.", ""]
            continue
        lines += [f"{i}. {_hit_line(h)}" for i, h in enumerate(item.hits, start=1)]
        if item.rationale:
            lines += ["", f"Rationale (model-written, from the cited items only): {item.rationale}"]
        elif item.rationale_note:
            lines += ["", f"Rationale: {item.rationale_note}."]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
