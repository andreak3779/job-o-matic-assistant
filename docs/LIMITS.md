# Claims and limits

Precise statements about what this project does, and where it stops.

## Model use

- **The core commands make no language-model calls.** Parsing a posting, rating the fit, the gate,
  the applications log and building DOCX and PDF files are plain Python. The same inputs give the
  same outputs.
- **Optional: local embeddings.** `jobo index build` and `jobo evidence` / `jobo search` use a local
  Ollama server (default `http://localhost:11434`, model `nomic-embed-text`) to turn evidence text
  into vectors. Nothing leaves the machine. `jobo search --keyword-only` needs no server.
- **Optional: `jobo evidence --explain`.** This sends a short prompt to a chat model through
  Ollama and keeps the one or two sentence answer as a rationale. The default model
  (`gemma4:cloud`) is an Ollama cloud-hosted model, so with that default the prompt does leave the
  machine; pass `--chat-model` to use a local model instead. Only evidence marked cloud-safe (course,
  lab and project text) is sent; résumé bullets and interview stories are marked local-only and are
  never sent. The prompt is scanned for personal data first and is not sent if it matches. A reply is
  discarded unless it cites evidence that was actually provided. The rationale is advisory and never
  changes a rating.
- **Claude Code and Claude Desktop are the user's own clients.** The skills and MCP tools are how
  those clients call this code. The code does not call a model on their behalf.

## Retrieval evaluation

Evidence retrieval was checked against a small set of 24 queries labelled by the author (a JD-style
phrasing and the course titles that would count as correct). That is too few and too
self-labelled to support more than an indication that retrieval works. The test suite enforces a
recall floor on the fictional demo data with recorded vectors; the figure for the real learning
history is measured by hand with `scripts/eval_retrieval.py`. Retrieval is advisory.

## The fit rating

- The cut-offs for Strong, Good, Worth a try, Stretch and Pass are starting values, chosen by the
  author, not fitted to outcomes. They are meant to be recalibrated once enough application
  outcomes are recorded ([ADR 0021](adr/0021-fit-rating-weights-core-requirements.md),
  [Fit-Calibration-Plan.md](Fit-Calibration-Plan.md)).
- The skill vocabulary, aliases and location rules are JSON files tuned to this author's search.
  Another person would change them.
- The parser has known gaps: it can split one short line into two skills, keep only half of a
  compound phrase, or treat a word in a list as a skill when it is not one. Lines it cannot score
  are listed, not hidden.

## Page counts

The deterministic `generate-resume` trims to two pages by an estimate of the layout's height,
calibrated against LibreOffice and kept a little conservative
([ADR 0024](adr/0024-resume-page-budget.md)). It is not a measurement. Only `--check-pages` counts
the real pages, and it needs LibreOffice (`soffice` or the Flatpak, chosen with
`JOBOMATIC_LIBREOFFICE`) and `pdfinfo`. Trimming works by
position, not by rereading the posting, so it is a first draft and not the tailored document.

## Duplicate detection

Duplicates are found by comparing company and role title in the applications log within a 60-day
window. That is a heuristic. A repost under a different title, or the same role at an agency, can
slip through, and two different roles with similar titles can be flagged. The override exists for
that reason.

## Scope

- One user. There are no accounts, no sharing and no concurrent editing.
- It does not submit applications, read job boards or send email.
- The MCP server speaks stdio only and is not meant to be exposed on a network.
- It is built for one person's search in one country, so location rules, currency and wording
  reflect that.
