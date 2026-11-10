# 0011 — Salary screen is a flag the user must confirm, not a Pass

**Status:** Accepted

## Context

The cover-letter skill said to compare a posting's pay with the candidate's minimums
"and ask whether to continue". Nothing enforced it, the numbers were typed
into five places across two SKILL.md files, and nothing could parse pay out of
a posting. Location (ADR [0008](0008-location-eligibility-in-fit-rating.md))
is a hard Pass because a role in Quebec cannot be taken however it is worded.
Pay is different: a role under the minimum might still be worth a conversation,
and the user — not the code — decides.

## Decision

`src/jobomatic/fit/salary.py` finds the pay a posting states (ranges, `k`
notation, hourly versus annual, CAD versus USD) and compares it with the
minimums in `private/search-constraints.json` (`src/jobomatic/fit/constraints.py`). The
result is a `SalaryAssessment` (`posted`, `below_minimum`, `flags`) that
**never changes the fit rating**.

- `fit-check` prints a **Salary screen** block when pay is posted.
- The MCP gate on `generate_resume`, `generate_cover_letter` and
  `generate_application_documents` refuses when the posted pay is below the
  minimum, with a message telling Claude to ask the user, unless
  `confirm_below_minimum=true` is passed. This is a prompt-level safeguard —
  the model could pass the flag itself — so the parameter name and the error
  text say "only after the user says so". The job-site letter and cold
  outreach are not salary-gated.
- The minimums are **private and untracked**: `private/*` is gitignored, with
  `*.example.*` templates tracked. The numbers are a negotiating position and
  the repo is cloned to several machines. `scripts/check_private_values.py`
  (run by the pre-commit hook) fails if a configured minimum is retyped into
  any tracked file; the skills now say "read it with `constraints show`".

## Consequences

- Conservative by design, because a false "below minimum" blocks real work:
  an amount needs a `$` and a clear pay context (bonus, budget, funding and
  "$10M" are skipped); a posting is "below" only if **every** comparable
  figure is; USD, an hourly figure on a role not described as a contract, and
  unparseable pay become advisory ⚠️ notes, never a verdict.
- A missing constraints file is normal (CI, a fresh clone, a second laptop
  before the file is copied) and means no screen; a malformed one fails loudly
  (ADR [0007](0007-fail-loud-on-malformed-input.md)) so a typo cannot quietly
  disable it. Copy the file between machines by hand.
- Part-time postings are out of scope: the minimums are developer minimums.
- Pay buried in prose ("competitive, around ninety thousand") is not
  detected; neither is a posting that states no pay. Both read as "no screen".
