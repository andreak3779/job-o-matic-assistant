# 0012 — Evidence retrieval is advisory and sits beside the fit engine

**Status:** Accepted. The implementation was replaced by [0019](0019-retrieval-module-and-sqlite-index.md); the advisory rule below still holds.

## Context

The fit engine (ADR [0001](0001-deterministic-fit-engine.md)) matches a job
description's skills against the profile bundle by terms and aliases. That makes
the rating reproducible, but it misses paraphrase: a requirement written as
"tuning slow relational queries" is not found in evidence that says "query
optimization in SQL Server", so a real strength can show up as a gap. DDD had
the same problem before it was fixed by hand in the resume.

## Decision

The evidence command (`jobo evidence <skill or jd.md>`; first written as `shared/evidence.py`) retrieves the
nearest evidence for a requirement from three sources — course and lab summaries
(from the learning history),
portfolio projects, and resume bullets from the profile bundle — and shows it with
a citation to its source. It ranks by cosine similarity plus a small keyword bonus,
drops anything under a score cutoff, and uses a local Ollama embedding model
(`nomic-embed-text`). Vectors are cached in `outputs/evidence-index.json`
(gitignored), keyed by a hash of each text.

- **It never changes the rating.** The rating stays computed in code. Retrieval only
  adds an advisory list, and the output says so.
- **Cloud models are optional and narrow.** `--explain` asks a chat model for a short
  rationale. Only course, lab and project text is sent; resume bullets are never put
  in a prompt, the prompt is scanned for personal data first, and a reply is kept only
  if every citation points at an item that was sent. The prompt tells the model to call
  courses coursework, not experience.
- **No new core dependency.** The client is `urllib`; similarity over a few hundred
  vectors is plain Python.
- **Self-study is not indexed as experience.** Resume entries with no employer are
  skipped: their long summaries repeat the course documents and outranked them.

## Evidence

`scripts/eval_evidence.py` scores retrieval on 24 labelled JD-style phrasings
(`tests/fixtures/evidence_eval_queries.json`) against the real learning history.

| Method | Recall@1 | Recall@3 |
| --- | --- | --- |
| Keyword only | 12/24 | 16/24 |
| Semantic only | 16/24 | 22/24 |
| Hybrid (default) | 19/24 | 21/24 |

At the default cutoff, 44 of the 72 returned items were labelled correct.

## Consequences

- The labelled set is small and was written by the author who also built the
  retriever, so the figures are indicative, not a benchmark. The 44/72 precision
  understates quality because other relevant courses were not labelled.
- The corpus is tiny (346 summaries, median 204 characters). Chunking is one chunk per
  course, so it exercises none of the harder parts of retrieval at scale.
- Similarity is not proof. A score of 0.70 for an unrelated term still returns
  something; the cutoff only removes the weakest matches. Output asks the reader to
  check each match before claiming it.
- Embeddings run locally. Ollama's cloud models are chat-only as far as we could
  verify, so they are used only for the optional rationale.
