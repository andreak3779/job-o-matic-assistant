# 0023 — Soft skills are a separate block that is listed but not scored

**Status:** Accepted. Built after four real postings each showed the same problem (communication,
collaboration and problem-solving lines scoring as skills).

## Context

Postings list soft skills ("Strong written and verbal communication skills", "a self-starter who
challenges the status quo") next to the technical requirements. The fit engine matches skills by
word against the profile ([0001](0001-deterministic-fit-engine.md)), which works for technologies
and not for these:

- The parser knows a short list of section headings. "Soft Skills" is not one of them, so its
  bullets stay in whatever section came before (often Nice to Have) and are scored as skills,
  usually as a 🔴 "no evidence" row.
- A match on the word proves nothing. The profile holds evidence for these qualities in stories
  and in the way roles are written, not as skill terms.
- A 🔴 row for communication skills reads as a gap and is not one the user can fix.

## Decision

Recognise soft-skill headings (soft skills, personal qualities, attributes and similar) as their own
section. Lines under them are collected as soft requirements and shown in `fit-check` and
`gap-analysis` under **Soft skills (not scored)**, so they are listed and never dropped, as the
"Required lines not scored" list already is ([0009](0009-skill-terms-from-sentence-bullets.md)).
They never change the rating.

This can share one block with the education and years-of-experience lines that
[0021](0021-fit-rating-weights-core-requirements.md) already moves out of the rating.

## Resolutions (confirmed by the owner)

- **Does a soft-skill line ever change the rating?** No. Whether a role leads people shows in the
  title-level line instead.
- **Point at the user's stories?** Not now. A separate, small change for interview prep.
- **A soft-skill line with no heading (inside a technical list):** detected by a phrase list
  (`src/jobomatic/fit/soft_skill_phrases.json`, edited without touching code). A line that holds a phrase and
  names no known skill is listed; a line that also names a skill keeps scoring that skill. A line
  that matches nothing stays scored as before, until a phrase is added for it.
- **One block or two?** One. Soft skills share the Soft requirements block with the education,
  years and title-level lines, each with its own label.
- **Headings:** a section headed soft skills, personal qualities, personal attributes,
  interpersonal skills, competencies or attributes is listed whole. A heading that says
  "technical" is not read as soft skills.
- Soft-skill lines do not use up the "first five required lines" that make a requirement core
  (ADR 0021): they are not requirements to score.
- The phrase list is a starting set; the owner reviews it after use.

## Consequences

- No false 🔴 rows for qualities that are not skills; the lines are still in front of the reader.
- The heading list grows, so a posting that labels the section unusually still leaks into the
  technical lists until its heading is added.
- The rating vocabulary and the golden files are unchanged; only the output gains a block.
