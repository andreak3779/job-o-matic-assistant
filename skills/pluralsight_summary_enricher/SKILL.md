---
name: pluralsight-summary-enricher
description: >
  Adds a short, paraphrased "summary" to learning items that have none, so each Pluralsight
  course or lab has a description of what it covers. Runs automatically as the final step of the
  pluralsight-updater skill for the items it just added. Can also be triggered manually with
  phrases like "add summaries to my Pluralsight history", "backfill course summaries", or
  "generate descriptions for my Pluralsight courses/labs". Writes only through
  `learning summarize`; never edits items.yaml by hand.
---

# Pluralsight Summary Enricher

Each learning item can carry a `summary`. Microsoft Learn items arrive with the provider's own
text (`summary_source: provider`). Pluralsight exports have none, so this skill writes a short
paraphrase for them and the CLI stores it marked `generated`. The summaries are for the
candidate's own reference and for evidence retrieval; they are never pasted verbatim into
resume or profile text.

## Workflow

1. **Work list.** `python -m jobomatic learning summarize --missing` prints
   `id<TAB>title` for every item without a summary. For an automatic run, work only on the ids
   the updater handed over; for a backfill, work in batches of about 20.
2. **Look each one up.** Search scoped to the source site, for example
   `site:pluralsight.com "<title>"` (labs live on `app.pluralsight.com`). Read the top result to
   see what the course actually covers.
3. **Write one paraphrase per item, 15 to 35 words,** in your own words: what skill, tool or
   concept it teaches and at what level. If search finds nothing usable, infer from the title,
   the type (course or lab) and neighbouring items on the same topic, and tell the user which
   ones were inferred so they can confirm. Never invent API names, versions or features the
   source does not support; stay generic when unsure.
4. **Show the user the batch** (id, title, summary), then on a yes write a JSON file `{id: summary}`
   in the scratchpad and run
   `python -m jobomatic learning summarize --missing --from-json <file>`.
   It refuses unknown ids and **never overwrites** an existing summary (provider, manual or an
   earlier generated one). To replace one, the user edits that item deliberately.
5. **Advisory topic check.** If a summary shows an item sits under the wrong topic, say so. Topic
   rules live in `topics.yaml`; do not move items yourself.

## Copyright guardrails (non-negotiable)

- Paraphrases only: never copy sentences or distinctive phrasing from the course page or search
  snippet.
- No quotation marks reproducing source text.
- Keep each summary short (roughly 15 to 35 words), too short to substitute for the course
  description.
- One summary per item, written fresh; do not template several summaries off one search result.

## Companion skills

- `pluralsight-updater`: upstream; hands over the ids of new items after each import.
