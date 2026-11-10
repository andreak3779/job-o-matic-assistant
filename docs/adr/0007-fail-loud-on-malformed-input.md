# 0007 — Fail loud on malformed input; never silent fallback

**Status:** Accepted

## Context

During one work session, six independent modules were discovered to each
silently mishandle malformed or ambiguous input instead of raising or
warning:

- `src/jobomatic/fit/parser.py` silently dropped bullet lines that didn't start
  with a literal `-`/`•` marker under a recognized heading, producing an
  empty required-skills list and a false "Pass" rating instead of failing
  to parse.
- `src/jobomatic/fit/engine.py::_load_aliases` silently iterated a malformed alias
  entry (a string where a list was expected) character-by-character,
  producing garbage single-letter aliases instead of raising.
- `project-2-profile-learning-hub/skills/profile_hub_bundle_generator/scripts/build_bundles.py::_build_genuine_gaps`
  silently fell back to using only the first word of a "Known Genuine Gap"
  bullet with no em-dash separator, with no warning.
- `src/jobomatic/privacy/guard.py` contained key names in its sensitive-key list that
  didn't match any field in the current data model, giving false confidence
  that certain data was being screened when it never was.
- `project-2-profile-learning-hub/scripts/query_learning_history.py::cmd_lookup`
  silently collapsed two course entries with an exact normalized name,
  keeping whichever the dict comprehension happened to retain last.
- `project-2-profile-learning-hub/scripts/merge_pluralsight_course.py::_bump_summary_table`
  silently incremented a TOTAL count when inserting a course into a
  section with no matching Summary-table row, printing no warning.

Each was discovered only by manual reproduction, not by tests, because
nothing in the codebase's conventions said this class of bug was disallowed.

## Decision

A fallback path that would discard, guess at, or silently degrade
information must either raise an exception (when the caller cannot proceed
correctly without that information) or emit a visible warning the caller
will actually see (when execution can reasonably continue in a degraded but
honest state). It must never do so quietly. This applies to any code that
parses hand-maintained reference files, accepts user-supplied job
descriptions, or mutates shared markdown/JSON data in place.

## Consequences

- This is a code-review checklist item, not an automated lint rule —
  "does this input look malformed" is not mechanically detectable in
  general, so a reviewer must ask "what happens on the fallback path?"
  for every conditional handling unexpected shape.
- Adopting this ADR does not retroactively guarantee every fallback
  remaining in the codebase follows it — only the six instances above have
  been fixed so far. Future audits may find and fix more.
- This makes some code paths slightly more verbose (an extra
  `warnings.append()` or `raise`), an accepted cost for correctness and
  honest error reporting.
