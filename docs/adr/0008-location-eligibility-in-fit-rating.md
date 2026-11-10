# 0008 — Location and work-arrangement rules are part of the fit rating

**Status:** Accepted

## Context

The candidate's home city comes from the vault's location preferences and can't take some postings however well the skills
match: Quebec-based roles (French-language work is out of scope), hybrid or on-site roles
outside the home city, and remote roles limited to Atlantic Canada, which falls
outside the time zones the candidate's preferences allow. The fit
engine (ADR [0001](0001-deterministic-fit-engine.md)) only looked at skills, so
a Strong-skills posting in Montreal was rated Strong, passed the MCP fit gate
(ADR [0003](0003-fit-gate-enforced-at-mcp-boundary.md)), and would have had a
resume and cover letter generated for a job that can't be taken.

## Decision

`src/jobomatic/fit/location.py` produces a `LocationAssessment`
(`disqualifiers`, `flags`) from the JD text, driven by
`src/jobomatic/fit/location_rules.json`. `parse_jd` attaches it as
`ParsedJD.location_check`; every `rate_fit` caller passes it as
`location=parsed.location_check`. Any disqualifier forces the rating to
**Pass** — in `rate_fit` itself, so the CLI, gap analysis and the MCP gate all
agree with no separate gate to keep in sync. The per-skill matches are still
returned, and `FitResult.skill_rating` keeps what skills alone would have
earned so reports can say "Pass because of location — skills would be Strong".

Disqualifiers: Quebec is the only place named; Atlantic Canada is the only
place named on a remote/hybrid/on-site role; hybrid or on-site with a
non-the home city place and no remote option; French listed as a requirement.
Everything ambiguous is a **flag** (⚠️), never a Pass: a Canada-wide remote
posting that also lists Quebec or Atlantic provinces, hybrid with no stated
city, "the home province" without the home city, a non-the home city city with no stated
arrangement, French as an asset or merely mentioned.

## Consequences

- A false Pass blocks a real application, so disqualifiers only come from
  **explicit location lines** (a `Location:`-style label, the title, or a short
  line that opens with remote/hybrid/on-site). A company blurb saying "our
  office in Montreal" cannot disqualify a remote role. French is the one rule
  scanned across the whole posting, because it is stated in requirement prose.
- The rules are data, not code: changing home city, adding an excluded region
  or softening a rule is an edit to `location_rules.json`. A malformed entry
  fails loudly at import (ADR [0007](0007-fail-loud-on-malformed-input.md)).
- Text heuristics will miss postings that bury location in prose, and can't
  resolve whether a "Canada-wide" role really accepts the home province residents (or
  whether Quebec's French-language rules apply to a remote employee outside
  Quebec). Those cases surface as flags for a human to confirm with the
  recruiter; the engine never guesses.
- `rate_parsed_jd(parsed, profile)` is the entry point for every JD-driven
  caller: it forwards `parsed.location_check` (and `parsed.unscored_required`,
  ADR [0009](0009-skill-terms-from-sentence-bullets.md)) so neither can be
  forgotten at a call site. Hand-built `rate_fit(...)` calls (tests, a future
  skills-only question) still get the old skills-only rating, since `location`
  stays optional there.
- Cover-letter and resume generation, and `generate_application_documents`,
  refuse a location Pass through the existing `_require_good_fit` gate with a
  message that says skills are not the blocker.
- The two other posting-specific tools ADR 0003 leaves skill-ungated — the
  job-site letter and JD-driven cold outreach — now refuse on a *location* Pass
  only (`_require_workable_location`); their skill fit is still deliberately
  ungated. Thank-you letters and interview prep are **not** gated at all: they
  only happen once an interview is underway, and a text heuristic must never
  block them. Interview prep judges "low confidence" on `skills_only_rating` so
  a location Pass can't mislabel it.
