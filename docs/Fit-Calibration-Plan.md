# Fit calibration plan

Decision record: [ADR 0018 in `claude-projects`, ADR 0021 in `job-o-matic-assistant`](adr/) (the two
copies of the ADR differ only in their number). This plan is the work breakdown for it.

> This file is kept free of personal data even though the repo is private, so it could be shared
> without a clean-up: no names, employers, salary figures or private rules. Example postings are
> described by shape ("11 requirements, 7 met, 3 course-level") and never by employer.
> Implementation lands in `job-o-matic-assistant`; the prototype repo keeps a copy of this record.

## Goal

Make the fit rating a better guide to "is this posting worth an application", without giving up the
deterministic, testable engine. Specifically: stop rating a well-covered posting Stretch because of
a handful of course-level or tail gaps, keep the hard stops that earn their keep, and collect the
outcome data needed to tune the thresholds on evidence.

## Why now

| Finding | Where it shows |
|---|---|
| Equal weighting: a title skill counts like a tail skill | `_derive_rating` in `src/jobomatic/fit/engine.py` |
| 3+ course-level skills with no gaps is Stretch, whatever the coverage | same function |
| Stretch and Pass end the workflow; no way to confirm past it | `job_description_fit` skill text; MCP gate |
| The parser re-counts "preferred" lines as required, splits either/or lists, and finds nothing in prose postings | several recent postings needed hand-scoring |
| Only "applied" is recorded, so no rating can be checked against what happened | applications log |

Outside evidence (single-source, so it sets starting points only):

- [TalentWorks, 6,000+ applications: interview odds about equal at 50% and 90%+ skill match](https://www.cnbc.com/2018/12/12/matching-half-of-a-jobs-requirements-might-still-get-you-an-interview.html) (2018, job-seeker data).
- [Express Employment Professionals, 505 Canadian hiring managers: 86% waived a requirement, 52% years of experience, 31% degrees](https://www.hrreporter.com/focus-areas/recruitment-and-staffing/canadian-employers-waiving-job-requirements-to-fill-roles-report/392621) (Nov 2024, one firm's survey).
- [Career-coach rules of thumb run from 50% to 80%, with the first few listed requirements counting most](https://skillcrush.com/?p=518607).
- [Automatic rejection mostly happens on knockout questions (eligibility, licences, location), not skill counts](https://support.kula.ai/articles/8596267232-knockout-questions). Mostly vendor material.

## Decisions (confirmed 2026-11-05, all as proposed)

The thresholds stay starting values until Step C5 (ADR 0021 remains Proposed).

| # | Question | Decision |
|---|---|---|
| F1 | Name of the new tier | "Worth a try" |
| F2 | Coverage cut-offs | Pass under 40%, Stretch 40–59%, Worth a try 60%+ |
| F3 | Core definition | Title, first five required bullets, 2+ mentions, or a years figure |
| F4 | Is a skills Pass ever overridable? | No (location Pass also stays hard) |
| F5 | Outcome events to record | response, interview, rejection (+ optional reason tag) |

## Steps

Each step ends with the tools still usable (fit check, document generation, applications log). A step
that cannot get there is reverted, not left half done.

| Step | Topic | Depends on | Model / effort |
|---|---|---|---|
| C1 | Parse hygiene and soft requirements | — | Sonnet, medium |
| C2 | Core/tail classification and the new rating | C1 | Sonnet/Opus, medium (walk through it afterwards) |
| C3 | The override at the gate (built with the document gate) | C2 | Sonnet, low |
| C4 | Outcome events and the `calibrate` report | — (can run beside C1) | Sonnet, low |
| C5 | Calibrate the thresholds and accept the ADR | C2, C3, C4, ~30 outcomes | with the owner |

### C1: Parse hygiene and soft requirements

1. Treat a line under "preferred", "nice to have", "asset" or "bonus" wording as a nice-to-have even
   under a required heading (extends [0009](adr/0009-skill-terms-from-sentence-bullets.md)).
2. Score either/or lists once, by the best-evidenced alternative.
3. Move education and years-of-experience lines to a **Soft requirements** block; "or related field"
   and "or equivalent" mark them met. Never count them as 🔴.
4. Add the low-confidence notice: more than half of the required skills 🔴, whatever their number
   (the owner's rule).
5. Add fixtures: a posting with duplicated "preferred" experience lines, one with an either/or
   cloud list, and a prose-only posting.

**Done when:** the three fixtures parse to the expected skill lists, the existing parser tests still
pass, and the soft-requirements block appears in `fit-check` and `gap-analysis` output.

### C2: Core/tail classification and the new rating

1. Add a core/tail flag to each parsed required skill, using the F3 rule.
2. Replace the count rules in `_derive_rating` with the table in the ADR. Compute coverage and put it
   and the core gaps in the rationale.
3. Add `Worth a try` to the `Rating` type and to every place that lists ratings (skills, MCP tool
   descriptions, golden files, README).
4. Tests that pin every boundary: core 🔴 count 0/1/2, coverage 39/40/59/60%, 2 versus 3 course-level
   skills, the 🕰️ cap. Keep the existing documented-rules tests passing or update them in the same
   commit.

**Done when:** a posting with 7 met, 3 course-level and no gaps rates Worth a try (it was Stretch);
a posting with one missing title skill rates Stretch whatever its coverage; golden files are
regenerated and reviewed line by line.

### C3: The override at the gate

1. Add `confirm_gaps` to the document-generating MCP tools and the matching CLI flag. Refuse Worth a
   try and Stretch without it, with error text that says "only after the user says so".
2. Keep the location Pass and the skills Pass as hard refusals.
3. Update the `job_description_fit`, `gap_analysis_job_description` and cover-letter skill text: list
   the gaps and ask for Worth a try and Stretch; the "do not ask" rule applies to the hard stops only.
4. Add a note to [0003](adr/0003-fit-gate-enforced-at-mcp-boundary.md) pointing at the new ADR.

**Done when:** tests show each rating's gate behaviour with and without the flag, and the skill
text has no remaining "do not offer documents" line for the two overridable tiers.

**Status:** done. The gate is `src/jobomatic/gate.py`; the command line and the MCP tools
both use it.

### C4: Outcome events and the `calibrate` report

1. Add `response`, `interview` and `rejection` events (optional `reason` tag) to the applications
   log, following [0010](adr/0010-applications-log-event-sourced-explicit-applied.md): append-only,
   set only on an explicit request.
2. Store the fit rating at the time of applying on the application record, so it can be compared
   later even after the rules change.
3. `applications calibrate` prints response and interview rate by rating tier and the most common
   rejection reasons, and says plainly when the sample is too small to read.

**Done when:** the events replay into the same state as before for old logs (nothing breaks), and
the report runs on an empty log and on the demo vault.

### C5: Calibrate and accept

1. After about thirty recorded outcomes, read the `calibrate` report.
2. Move the thresholds only if the data supports it; record the numbers and the sample size in the
   ADR.
3. Change the ADR status from Proposed to Accepted (or write the superseding ADR).

**Done when:** the ADR states the evidence behind each threshold, or says the thresholds are still
starting values and why.

## Risks

| Risk | Mitigation |
|---|---|
| Weaker applications waste time | Coverage and core gaps are shown; the override is a decision, not a default |
| Core detection misreads a posting | Low-confidence flag, hand-check step, tests on the odd fixtures |
| Thresholds read as facts | ADR stays Proposed; thresholds live in one place with boundary tests |
| Override flag passed by the model alone | Parameter name and error text; same accepted limit as the salary flag |
| Outcome data is thin or biased (people reply to a few) | The report states sample size; no threshold moves on a small sample |
| Rating vocabulary change breaks consumers | One change updates every list of ratings; golden files reviewed |

## Open questions

- Should a skills Pass ever be overridable, for example with a written reason recorded on the
  application?
- Should coverage count a 🟡 as ½ for every kind of evidence, or weight a built project above a
  course?
- Should nice-to-haves ever raise a Worth a try to Good, or stay a Strong-only factor?

## Later

- **Umbrella skills scored by their parts** (AI first): [ADR 0022](adr/0022-umbrella-skills-scored-by-their-parts.md),
  Accepted and built for AI. The parts are the owner's list; the AI category will be revised.
- **Soft skills as a separate unscored block:** [ADR 0023](adr/0023-soft-skills-are-a-separate-unscored-block.md),
  Accepted and built. Soft-skill lines are listed in the Soft requirements block and never scored.

