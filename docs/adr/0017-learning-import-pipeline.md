# 0017 — Learning history comes from imports, not hand-kept markdown

**Status:** Accepted

## Context

Course history is kept in two hand-maintained markdown files plus a
Pluralsight JSON. Updating them takes a chain of scripts (parse, copy a
staged file, dry-run, merge, enrich), counts and totals are edited into the
markdown, and the matching rule is "is this title new?". That rule missed
courses that had been in progress and later reached 100%. Microsoft
Learn's transcript was kept by hand and drifted out of date (75 modules
recorded against 81 completed).

## Decision

One `learning` module with a `LearningItem` per completed course, lab,
module or learning path, stored as YAML in the vault.

- **One use case, many sources.** `jobo learning import` takes a
  `LearningSource` adapter: a Pluralsight HTML export, the Microsoft Learn
  transcript, or a manual entry.
- **Match by stable ID,** never by "is this title new". It prints a diff,
  and writes only with `--apply`.
- **Completed items only.** There is no readable course list; totals and
  per-topic hours are computed on demand, never stored.
- **MS Learn source:** the transcript share link's JSON, which the Learn
  profile page itself uses and which needs no sign-in. It is undocumented,
  so every response is validated against a JSON Schema, owner fields
  (name, email) are dropped, and each response is saved so imports can be
  replayed. It is fetched **only when explicitly requested**; everything
  else reads the saved copy.
- **Gaps** (learning-path links, a few modules without links) are filled
  from Microsoft's public course pages; a Claude-assisted lookup proposes
  links for the rest and a person confirms each one.

## As built

- **Ids are namespaced by provider:** `pluralsight:<link path>` and `mslearn:<catalog uid>`.
- **One exception to "never by title":** when an incoming id is not stored, a stored item of the
  same provider, kind and title whose id the import does not contain is treated as the same item
  with a new id, reported as *re-keyed*. Replaying a real export showed Pluralsight lists about a
  third of the courses under a different link than the old hand-filled JSON recorded, and the
  same course renamed by Pluralsight had been recorded twice. The one-time migration merged
  three such pairs, so the old "269 courses" was really 266.
- **Totals never count a learning path's minutes**, because a path's duration is the sum of its
  modules (the transcript's own `totalTrainingMinutes` does the same).
- **Completed only:** in-progress entries are not stored, so evidence retrieval and the
  learning-plan skills treat anything not completed as not started.
- **Topics** come from ordered keyword rules (`topics.yaml`, replaceable per vault). The defaults
  reproduce 294 of the 300 hand-made categories; the migration kept the hand-made ones.
- **Gaps:** `learning enrich` confirms a learning path's page by its `uid` before accepting it,
  caches pages in the vault, and ties modules to their path. Paths no page confirms and modules
  without a link go to the confirmed-link lookup in the updater skill.
- **Hand-written counts in the profile** are checked by `profile validate`, which warns when they
  differ from the imported data.

## Consequences

- The markdown course lists, the merge scripts and the learning-history
  query script are deleted.
- The share-link ID is treated as private: it lives in the vault only.
- If Microsoft changes or removes the endpoint, validation fails loudly and
  a transcript PDF importer (in the backlog) becomes the fallback.
- The Microsoft Learn Platform API (Entra ID/MSAL) is deferred; it would
  plug in behind the same `LearningEnricher` port.
