"""Hybrid scoring: turn candidate chunks into a ranked, cut-off list of hits.

THIS MODULE IS WRITTEN BY THE AUTHOR, not generated. Claude Code reviews it.
The old implementation is ``shared/evidence.py`` (``_tokens``, ``keyword_score``, ``search``), now
only in git history: ``git show main:shared/evidence.py``;
ADR 0012 explains why it looks the way it does. Do not copy it line by line. Write it from the
spec below, then compare.

Pure function of its inputs: no I/O, no models (ADR 0016, 0019). The store has already done
the vector search, so each candidate arrives with its cosine similarity (0..1, higher is closer).

Spec
----
``tokens(text)``
    The set of searchable words in ``text``: lower-cased, split on anything that is not a letter,
    digit, ``#``, ``+`` or ``.`` (so "C#", "C++" and "ASP.NET" survive), with stop words dropped
    and plurals folded so "queries" and "query" match. Stop words are filler such as "the", "and",
    "experience", "strong", "skills".

``keyword_score(query_tokens, doc_tokens)``
    The share of the query's tokens found in the document, 0..1. An empty query scores 0.

``rank(query, candidates, *, k, min_score, keyword_weight, semantic)``
    For each ``(chunk, similarity)`` candidate compute the keyword score of ``query`` against
    ``chunk.text``, then the combined score:

    * ``semantic=True``  : ``similarity + keyword_weight * keyword``
    * ``semantic=False`` : ``keyword`` alone (the baseline the evaluation compares against;
      similarity is ignored, so callers may pass 0.0)

    Drop anything scoring below ``min_score`` (an empty result must mean "no evidence found",
    not "least bad match"), sort best first (ties must not depend on input order), return at most
    ``k`` ``Hit`` objects with ``score``, ``semantic`` (the similarity) and ``keyword`` filled in.

Floor
-----
With the defaults below, the hybrid recall@3 on the labelled query set must stay at or above
21/24 (``scripts/eval_retrieval.py``; the same check runs in CI on the demo vault).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from jobomatic.retrieval.model import Chunk, Hit

# Tuned against tests/fixtures/evidence_eval_queries.json (ADR 0012).
DEFAULT_KEYWORD_WEIGHT = 0.15
DEFAULT_MIN_SCORE = 0.60

_STOPWORDS = {
    # articles, prepositions, conjunctions, pronouns
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "me",
    "my",
    "no",
    "not",
    "of",
    "on",
    "or",
    "our",
    "out",
    "over",
    "own",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "too",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
    # filler from job ads
    "experience",
    "experienced",
    "skill",
    "skills",
    "strong",
}


def _stem(word: str) -> str:
    """Fold a plural into its singular form (ADR 0012).

    ``"queries"`` becomes ``"query"`` and ``"indexes"`` becomes ``"index"``.
    Words ending in ``"ss"``, ``"us"`` or ``"is"`` are left alone, so
    ``"class"``, ``"status"`` and ``"analysis"`` survive unchanged.
    """
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("sses", "xes", "ches", "shes")):
        return word[:-2]
    if len(word) > 5 and word.endswith(".js"):
        return word
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokens(text: str) -> set[str]:
    """Return the searchable words of ``text``.

    The text is lower-cased and split on anything that is not a letter,
    digit, ``"#"``, ``"+"`` or ``"."``, so ``"C#"``, ``"C++"`` and
    ``"ASP.NET"`` survive as single words. Dots are stripped from both ends of a word
    (so a full stop closing a sentence is not part of the word), except that ``".NET"`` is
    kept whole. Stop words are dropped and plurals are folded, so ``"queries"`` and
    ``"query"`` match.
    """
    result: set[str] = set()
    for word in re.findall(r"[a-z0-9#+.]+", text.lower()):
        if len(word) == 4 and word == ".net":
            result.add(word)
            continue
        word = word.strip(".")
        if not word or word in _STOPWORDS:
            continue
        stem = _stem(word)
        if stem in _STOPWORDS:
            continue
        result.add(stem)
    return result


def keyword_score(query_tokens: set[str], doc_tokens: set[str]) -> float:
    """Return the share of ``query_tokens`` that also appear in ``doc_tokens`` (0..1).

    An empty query has nothing to look for and scores ``0.0``.
    """
    if not query_tokens:
        return 0.0
    return len(query_tokens & doc_tokens) / len(query_tokens)


def rank(
    query: str,
    candidates: Sequence[tuple[Chunk, float]],
    *,
    k: int = 3,
    min_score: float = DEFAULT_MIN_SCORE,
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
    semantic: bool = True,
) -> list[Hit]:
    """Rank candidates by a hybrid score and return at most ``k`` hits.

    For each ``(chunk, similarity)`` candidate the keyword score of the query
    against ``chunk.text`` is combined with the similarity:

    * ``semantic=True``  : ``similarity + keyword_weight * keyword``
    * ``semantic=False`` : ``keyword`` alone (similarity is ignored)

    Candidates scoring below ``min_score`` are dropped, so an empty result
    means "no evidence found" and not "least bad match". The remaining hits
    are sorted best first; ties are broken by chunk id, so the order does not
    depend on the order of the input.
    """
    # Tokenize the query once, outside the loop.
    query_tokens = tokens(query)

    hits: list[Hit] = []
    for chunk, similarity in candidates:
        keyword = keyword_score(query_tokens, tokens(chunk.text))
        score = similarity + keyword_weight * keyword if semantic else keyword
        if score < min_score:
            continue
        hits.append(Hit(chunk=chunk, score=score, semantic=similarity, keyword=keyword))

    # Best first; chunk.id makes ties independent of the input order.
    hits.sort(key=lambda h: (-h.score, h.chunk.id))
    return hits[:k]
