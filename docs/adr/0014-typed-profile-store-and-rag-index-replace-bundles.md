# 0014 — A typed profile store plus a retrieval index replace bundles

**Status:** Accepted (supersedes the bundle parts of
[0006](0006-separate-project-domains.md))

## Context

Career facts live in hand-edited markdown files. A build step parses them
(`markdown_sources.py`, about 700 lines) into two JSON bundles: one with
personal details, one safe for public profiles. Every consumer reads a
bundle. The build is a step that has to be remembered, the markdown parser
is brittle, and the bundles exist mainly to separate public from private
data, which is better done on the data itself.

## Decision

- The source of truth is a set of **YAML files** in the vault, validated by
  **Pydantic** models on every load. There is no build step.
- Every field carries a `visibility` tag (`public` / `private`).
  `profile.presence_view()` returns only the public fields. The existing PII
  guard still scans everything generated for public profiles.
- A **SQLite index** (FTS5 keyword search plus `sqlite-vec` vector search,
  embeddings from a local Ollama model) is derived from the profile and can
  be rebuilt at any time. It is not the source of truth.
- Retrieval stays **advisory**
  (ADR [0012](0012-evidence-retrieval-advisory.md)): it chooses which
  evidence to show; facts, dates and fit ratings always come from the typed
  store. The recall@k evaluation becomes a regression test.

## Consequences

- The bundle loader, bundle markdown renderer, markdown parser, bundle
  builder and the bundle-generator skill are deleted.
- Safety checks previously done at bundle build time (cert sync, course
  counts and so on) run on load instead.
- A one-time converter and a field-by-field parity check protect against
  silent changes while moving the data.
- The index needs a local embedding model; if Ollama is not running,
  retrieval is skipped and everything else still works.
