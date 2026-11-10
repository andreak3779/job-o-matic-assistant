# 0021 — The fit rating weights core requirements over tail ones, adds a "Worth a try" tier, and lets the user confirm past the gate

**Status:** Proposed (thresholds are starting values until outcomes are recorded; see the
[calibration plan](../Fit-Calibration-Plan.md))

## Context

The fit engine ([0001](0001-deterministic-fit-engine.md)) rolls a posting up to Strong, Good,
Stretch or Pass by counting ✅/🟡/🔴 over the required skills. Every required skill counts the
same, and a Stretch or Pass stops the workflow: the document tools are refused at the MCP
boundary ([0003](0003-fit-gate-enforced-at-mcp-boundary.md)) and the skill tells Claude not to
offer documents or ask whether the user wants to continue.

Using it on real postings showed three problems:

1. **Equal weights.** A skill in the job title counts the same as the ninth tool in a list. One
   missing tail skill makes a posting Stretch, and three course-level skills with no gaps at all
   also make it Stretch, even when about four fifths of the posting is covered.
2. **No way past the gate.** The user is the one who knows whether a gap is a deal-breaker, and the
   rule leaves no room for that. Location ([0008](0008-location-eligibility-in-fit-rating.md)) is a
   different case: a role in the wrong place cannot be taken however it is worded. Pay
   ([0011](0011-salary-screen-flag-not-pass.md)) already has the right pattern: a flag the user
   confirms past.
3. **Parser noise reaches the rating.** In several recent postings the automated rating was wrong
   and had to be redone by hand. "Preferred" experience lines were counted again as required
   skills, either/or lists ("Azure or Google Cloud") became two requirements, and a prose posting
   produced no skills at all. Count thresholds turn that noise into a false Pass.

Outside evidence points the same way. A 2018 analysis of more than 6,000 applications found
interview odds about the same at a 50% skill match as at 90% or more. A 2024 survey of 505 Canadian
hiring managers found 86% had waived some requirement, most often years of experience (52%) and
degrees (31%). Both are single-source and have limits (job-seeker data, one staffing firm's
survey), so they inform the starting thresholds and do not fix them. Sources are listed in the plan.
The same outside material says the strictness is right in one place: headline skills and hard
eligibility rules. That is why the design is about weighting, not lowering every bar.

## Decision

The engine stays deterministic and Python-only. Four changes, in order of dependency.

**1. Classify each required line.**

- A line under a "preferred", "nice to have", "asset" or "bonus" wording is a nice-to-have, even
  when it sits under a required heading. This removes the double counting.
- Either/or lists count once, satisfied by the best-evidenced alternative.
- Education and years-of-experience lines are **soft requirements**: listed under their own heading
  with a note, never counted as 🔴. "Or related field" and "or equivalent" wording marks them met.
- A required skill is **core** if it is named in the posting title, sits in the first five required
  bullets, appears in two or more places in the posting, or carries a years figure. The rest are
  **tail**.

**2. Rate on core gaps and coverage.** Coverage is (✅ + ½ × (🟡 + 🕰️)) ÷ required skills. Rules run
top to bottom and the first match wins:

| Rating | When |
|---|---|
| Pass | a location rule is broken ([0008](0008-location-eligibility-in-fit-rating.md)); or 2+ core 🔴; or coverage under 40% |
| Stretch | 1 core 🔴; or coverage 40–59% |
| Worth a try | 0 core 🔴, and either a tail 🔴 or 3+ 🟡/🕰️ (so coverage is 60% or more) |
| Good | no 🔴, and short of Strong's bar (the 🕰️ cap from the current rules stays) |
| Strong | unchanged: no 🔴, 0–2 🟡, no 🕰️, at least two nice-to-haves present |

The rationale string states the coverage and names each core gap, so a rating can be explained
from its output alone.

**3. Confirm past the gate instead of stopping.** For Worth a try and Stretch the document tools
refuse unless `confirm_gaps=true` is passed, after the user has seen the gap list and said to go
ahead. This is the same prompt-level safeguard as `confirm_below_minimum`
([0011](0011-salary-screen-flag-not-pass.md)): the model could pass the flag itself, so the
parameter name and the error text say "only after the user says so". Two things stay hard stops: a
location Pass, and a skills Pass (2+ core gaps). The skill text changes to match: for Worth a try
and Stretch it lists the gaps and asks, and the "do not ask whether to proceed" instruction applies
only to the two hard stops.

**4. Flag a doubtful parse and record outcomes.**

- If more than half of the required skills are 🔴 (the owner's rule; no minimum count, because real
  postings can name as few as three skills), the output carries a **low-confidence result** notice
  and says to read the posting by hand. It does not change the rating.
- The applications log ([0010](0010-applications-log-event-sourced-explicit-applied.md)) gains
  events for a response, an interview and a rejection (with an optional reason tag).
  A `calibrate` report shows response rate by rating tier. Thresholds are revisited once about
  thirty outcomes exist.

## Consequences

- More postings clear the bar, so more applications are possible and more time can go into weaker
  matches. The coverage figure and the core-gap list are there so the user chooses with the facts.
- The thresholds (40%, 60%, five bullets, the 50% low-confidence line) are judgment calls. They are written in
  one place, covered by tests that pin each boundary, and stay "Proposed" until outcome data can
  confirm or move them. Until then they are not evidence.
- The rating is still reproducible (0001's guarantee holds). It is harder to describe in one
  sentence than a plain count, which is why the rationale string carries so much.
- Core detection is a heuristic. A posting that buries its headline skill in a late bullet will
  have it treated as tail; the low-confidence flag and the hand-check step remain the backstop.
- A confirmed override is only as honest as the person (or model) confirming. This is accepted,
  as it is for the salary flag.
- The rating vocabulary grows from four to five terms, so every place that lists ratings (skills,
  MCP tool descriptions, golden files, README) is updated in the same change.
- Not decided here: whether a skills Pass should ever be overridable. It is kept hard for now.

## Alternatives considered

- **Ask an LLM to judge fit.** Rejected for the reasons in [0001](0001-deterministic-fit-engine.md);
  the same input must give the same gate decision.
- **Only lower the thresholds.** Rejected: with equal weights, a lower bar lets in missing headline
  skills as readily as missing tail ones.
- **Remove the gate and show the table.** Rejected: the gate catches the hard cases (location, two
  or more missing headline skills) that waste a day of work, and the fix for the rest is an
  override, not the absence of a check.
