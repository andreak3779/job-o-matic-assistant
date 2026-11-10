# 0019 — Retrieval is its own module, with a SQLite index and a pure scoring function

**Status:** Accepted

## Context

ADR [0012](0012-evidence-retrieval-advisory.md) made evidence retrieval advisory and gave
it a working implementation in one file, `shared/evidence.py`. That file mixed five concerns:
turning the profile into documents, calling Ollama, caching vectors in a JSON file, scoring, and
rendering. The cache was a JSON blob that was loaded whole and searched by a Python loop. The
rearchitecture (ADR [0014](0014-typed-profile-store-and-rag-index-replace-bundles.md),
[0016](0016-modular-monolith-ports-and-adapters.md)) needs retrieval to be a module with
a clear core, and the plan names SQLite FTS5 and `sqlite-vec` for the index.

## Decision

`jobomatic.retrieval` is a module in the same shape as the others (ADR 0016):

- **Core** (`model`, `ports`, `scoring`, `service`) knows nothing about SQLite, HTTP or file
  formats. `import-linter` enforces that it does not import `sqlite3`, `sqlite_vec` or `urllib`.
- **Adapters** are `adapters/sqlite_index.py` (an `IndexStore`) and `adapters/ollama.py`
  (an `Embedder` and a chat function).
- **The module does not import the profile or learning modules, and they do not import it.** What
  goes into the index is decided in one place, `jobomatic/corpus.py`, which turns the profile and
  the learning items into `Chunk` objects. A new source of evidence is a new function there.
- **Scoring is a pure function** (`scoring.rank`). The store supplies vector neighbours with their
  cosine similarity; `rank` adds a keyword score, applies the cutoff and orders the result. It has
  no I/O, so it can be tested with plain values and written and reviewed on its own.

The index is one SQLite file in the vault's `index/` folder (gitignored there). It holds the
chunks, an FTS5 table over the same text and a `sqlite-vec` `vec0` table with cosine distance.

- **Incremental by hash.** A chunk's vector is kept while the hash of its text is unchanged;
  only new or changed text is embedded, removed chunks are dropped, and titles, statuses and links
  are always refreshed. A different embedding model or vector size discards the index and starts
  again, because mixed vectors would be wrong.
- **Exhaustive nearest-neighbour search.** `service.search` asks for every chunk in order of
  closeness. At a few hundred chunks that is exact and fast, so the ranking does not depend on an
  approximate index. If the corpus ever grows by orders of magnitude, the limit is the one place
  to change.
- **The index is derived.** The typed profile is the source of truth; deleting the index loses
  nothing and `index build` recreates it.

What goes in: completed Pluralsight and Microsoft Learn items (title and summary), projects,
resume bullets and interview stories. Resume bullets and stories are `local_only`: they can be
searched and shown on this machine but are never put in a prompt sent to a cloud model, exactly as
before (ADR 0012).

If the embedding service is not running, `index build`, `search` and `evidence` say so and stop
with a non-zero exit. Nothing else depends on it: the fit rating, the gap analysis and the
document generators never call retrieval.

## Evidence

The same hybrid method, `cosine + 0.15 × keyword overlap` with a 0.60 cutoff, is kept so the
numbers are comparable with ADR 0012. The recall floor (hybrid recall@3 of 21/24 on the labelled
real-history queries) is checked by `scripts/eval_retrieval.py`; the same evaluation runs on the
fictional demo vault in CI (`tests/test_retrieval_eval.py`) using recorded embeddings, so it needs
no embedding service and anyone can reproduce it.

## Experiment: BM25 instead of keyword overlap (2026-11-02)

`scripts/eval_bm25.py` re-ranks the same candidates (learning items only, k=3) with SQLite FTS5
BM25 in place of the share-of-query-words term. Production scoring is unchanged.

| Method | Real vault R@1 | Real vault R@3 | Demo R@1 | Demo R@3 |
| --- | --- | --- | --- | --- |
| semantic only | 15/24 | 22/24 | 17/20 | 18/20 |
| overlap hybrid (current) | 18/24 | 21/24 | 17/20 | 18/20 |
| bm25 only | 16/24 | 22/24 | 16/20 | 18/20 |
| similarity + 0.10 x BM25 | 19/24 | 22/24 | 17/20 | 18/20 |
| reciprocal rank fusion | 19/24 | 22/24 | 17/20 | 18/20 |

Weights 0.05 to 0.50 all reach 22/24 at k=3, so the gain does not depend on a tuned weight.

Re-run on 2026-11-08 (real vault, 399 learning chunks, the same 24 queries; demo 27 chunks, 20
queries): every figure in the table is unchanged. Looking at the weights one by one shows what the
sentence above does not: only recall@3 is flat. Recall@1 is 18, 19, 18, 17, 18 for weights 0.05, 0.10,
0.15, 0.25, 0.50, so 19/24 at 0.10 is the best of five rather than a plateau. At 0.50 the blend
misses "tuning slow relational database queries", the query BM25 alone also misses, so the weight
cannot simply be raised. The conclusion is unchanged: promising, not proven, and the margin is one
query.

Reading it honestly:

- The margin is one query in 24 (provisioning infrastructure declaratively), and the demo vault
  (27 learning chunks) cannot tell any method apart. Treat BM25 as promising, not proven.
- The overlap term buys recall@1 (15 to 18) but costs one recall@3 query compared with semantic
  alone. BM25 keeps the recall@1 gain without that loss.
- Reciprocal rank fusion ties the blend, but its scores are not on the cosine scale, so the
  `min_score` "no evidence found" cutoff would stop working. A blend (similarity plus a weighted
  BM25) keeps that cutoff and is the variant worth adopting if any is.
- Adopting it is an architecture change, not a swap inside `rank()`: BM25 needs corpus statistics
  (document frequencies), which `rank()` does not receive. The index already holds them in the
  FTS5 table, so the store port would supply keyword scores alongside similarities. The cutoff
  sweep must be redone for the blend before it replaces the current rule.

## Consequences

- The real-vault floor needs Ollama and the private learning history, so it is run by hand, not
  in CI. The demo-vault floor is the one CI enforces, and it is only as meaningful as the 20
  queries behind it.
- Recorded embeddings must be re-recorded when the demo vault, its queries or the embedding
  model change (`scripts/eval_retrieval.py --demo --record`).
- Microsoft Learn modules are now in the corpus. Most have a title and no summary, so they match
  on the title only until the summaries are filled in.
- `sqlite-vec` is a new core dependency, and it needs a Python whose `sqlite3` can load
  extensions. The index reports that clearly if it cannot.
