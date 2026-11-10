---
name: primary-learning-plan-generator
description: >
  Merges multiple job-specific gap analyses (from Acme Payroll, Example Finance, Example Consulting,
  or any other role) into ONE cross-referenced master learning plan, and
  refreshes an existing master plan against live Pluralsight/MS Learn
  completion data. Use whenever the user says "merge these gap analyses into
  one plan", "update the master learning plan", "refresh my learning plan
  with latest course history", "combine these learning plans", pastes/uploads
  more than one gap analysis at once, or uploads a previous Master Learning
  Plan PDF and asks it to be brought current. Do NOT use this for a single
  role/single gap analysis — use learning-plan-gap-analysis for that instead.
  Do NOT use this to prepare for a certification exam — use cert-learning-plan
  for that instead. This skill never runs gap analysis itself; it only
  consumes gap analyses already produced (in Project 1) and merges/refreshes
  them here, since this project owns the canonical completion data.
---

# Primary Learning Plan Generator

Combines N job-specific gap analyses into a single deduplicated, prioritised
PDF, and re-validates every item in an existing merged plan against live
completion data on every regeneration. This is the skill behind the candidate's
recurring "Master Learning Plan" document.

> **Boundary:** Gap analysis against a specific JD happens in Project 1
> (`gap-analysis-job-description`). This skill only merges analyses that
> already exist — pasted text, uploaded `.md` files, or an uploaded prior
> Master Learning Plan PDF. Never fabricate a gap analysis to feed this skill.
> **PDF template:** `python -m jobomatic generate-learning-plan <role-config.json>` — a data-driven engine that renders a role config. See `templates/roles/_example.json` for the schema; copy it, fill it, then run `python pdf-template.py profile/roles/<your-role-slug>.json`.
> **Verified course URLs:** the vault's `profile/course-urls.md`
> **Priority rules:** reuse Step 2 of `learning-plan-gap-analysis` (P1/P2/P3
> definitions) — do not redefine them here.

---

## Inputs

| Input | Required | Notes |
|---|---|---|
| Two or more gap analyses | ✅ | Pasted markdown, uploaded `.md`, or extracted from an uploaded prior Master Learning Plan PDF |
| Prior Master Learning Plan (PDF or its known baseline date) | Optional but preferred | Enables the "Recently Completed since [baseline]" refresh section |
| Baseline date | Optional | Defaults to the prior plan's "Updated" date, or the earliest gap analysis date if no prior plan exists |

If only one gap analysis is provided, stop and suggest `learning-plan-gap-analysis` instead — this skill's value is the merge/dedupe step.

---

## Step 1 — Load Live Canonical Data

Always read fresh, never trust the numbers in an uploaded prior plan:

1. The learning data (`python -m jobomatic learning list`, `stats`, `lookup`) — completed Pluralsight courses/labs and Microsoft Learn completions. Anything not in it counts as not started; progress percentages are no longer recorded.
3. `profile-facts.md` — resolved gaps, known genuine gaps, cert status
4. `skills-summary.md` — course counts (sanity-check totals in the plan header against this)

If the file's "Last updated" date is later than the uploaded plan's date, the plan is stale by definition — flag this in the "About This Plan" text (as in prior versions, e.g. "since the June 4 baseline, N items completed").

---

## Step 2 — Ingest Each Gap Analysis

For each gap analysis, extract:
- Source label (company/role name — used in "Closes: ... gap (CompanyName)" tags)
- Fit rating (Strong/Good/Worth a try/Stretch/Pass)
- Each gap: skill name, required/nice-to-have, current coverage note

Tag every gap with its source label before merging — this tag must survive into the final course card (`Closes: X — [gap type], [CompanyName]`), exactly as the uploaded example plan does (e.g. "Acme Payroll Genuine Gap, Gating Item").

---

## Step 3 — Deduplicate Across Sources

This is the core value of this skill over running plans separately. For each candidate course:

1. **Check `profile-facts.md` resolved gaps / `skills-summary.md`** — if a skill is already resolved (e.g. DDD, 2 courses complete Apr 2026), it is a **resume-surfacing issue, not a learning gap**. Exclude it from the plan and note the correction in "About This Plan" (mirror the DDD precedent from the June 26 plan).
2. **Check the learning data** (`learning lookup`) — if the exact course is already completed, move it to Recently Completed (Step 5), not the active plan.
3. **Merge same-topic gaps from different sources onto one course card.** If Acme Payroll and Example Finance both need Kubernetes depth via different named items, pick the single best course/lab and list both sources in the "Closes" line, exactly as the existing plan does for the K8s volumes/orchestration lab overlap.
4. **Never duplicate a course across two phases.** Once assigned, remove it from consideration for any other gap.

Produce an inline (not in the PDF) **Dedup Log** before building the plan:
```
| Course | Sources merged | Reason |
|---|---|---|
| Kubernetes: Volumes & Multi-Container Pods | Acme Payroll, base plan | Same depth gap, 2 sources |
| (excluded) DDD course | Acme Payroll flagged as gap | Already resolved — resume-surfacing issue only |
```

---

## Step 4 — Assign Phases and Priorities

Reuse `learning-plan-gap-analysis` Step 2 priority definitions (P1 = genuine gap/before applying, P2 = framing gap/before tech screen, P3 = differentiator/before final round). Layer on:

- **Gating items** (zero coverage anywhere, named explicitly as required in a JD) always lead Phase 0/Phase 1 regardless of source, flagged in the header banner (see "URGENT — Two gating items" pattern in the existing plan).
- **AI-200 domain overlap**: if a course also closes an AI-200 exam domain, note "AI-200 Overlap" in the phase header — this doesn't change priority, just adds context.
- Phase numbering follows topic grouping (as in the existing plan — Phase 0 IaC, Phase 1 Angular, Phase 2 .NET, etc.), not source company. Sources are metadata on individual cards, not phase organizers.

---

## Step 5 — Build the "Recently Completed" Refresh Section

Compare every item that was **active/not-yet-started** in the prior plan against Step 1's live data:

- If now completed in the learning data → move to "Recently Completed since [baseline date]", with actual completion date and a one-line note of what it closed.
- If still not completed → keep in its phase at its full duration (progress is no longer recorded).
- If untouched → keep as-is.

Recompute the plan-wide totals (items remaining, hours remaining) from scratch — never carry forward the prior plan's totals.

**Never mark anything complete based on inference alone.** If a course name in the prior plan doesn't exactly match a completed-courses row (e.g. name changed, catalog restructure), flag it for the candidate to confirm rather than assuming completion — same rule as `pluralsight-updater`.

---

## Step 6 — Select Courses for Remaining Gaps

Same lookup order as `learning-plan-gap-analysis` Step 3 and duration lookup order:
1. `course-urls.md` verified slug
2. `learning lookup` for durations
3. `web_search site:pluralsight.com "[title]"` for anything unverified — never guess a slug
4. `~X hrs` estimate only as last resort, flagged with `*` and a footnote (as in the existing plan's 4.7b item)

---

## Step 7 — Generate the PDF

Create (or update) `profile/roles/master.json` in the vault — copy
`templates/roles/_example.json` if the file doesn't exist, then fill the JSON to match
your merged plan. The fields map 1:1 onto the previous Python variables:

| JSON key | Was the Python variable |
|---|---|
| `output` | `OUTPUT` |
| `banner.title`, `.subtitle`, `.meta` | `BANNER_TITLE`, `BANNER_SUBTITLE`, `BANNER_META` |
| `urgency_text` | `URGENCY_TEXT` (omit or set `null` if no deadline) |
| `about_text` | `ABOUT_TEXT` |
| `legend` | `LEGEND` (array of `{label, color}`) |
| `plan` | `PLAN` (mix of `{type:"head",color,heading}` and `{type:"course", source,color,num,title,url,gap,hrs}`) |
| `key_links` | `KEY_LINKS` (array of `{label, url}`) |
| `footer` | `FOOTER` |

```bash
.venv/bin/pip install reportlab -q
python -m jobomatic generate-learning-plan <vault>/profile/roles/master.json
```

Confirm `PDF written: [path]`, then tell the user that path.

**Filename/versioning rule:** the version number (`v5` → `v6`, etc.)
lives in `output` and `footer` — bump it on every regeneration regardless
of how small the change, and never reuse a version number. If you're
updating an existing role rather than creating a fresh one, just edit
`profile/roles/<your-role-slug>.json` and re-run.

---

## Step 8 — Present and Summarise

After stating the output path, give a 5–6 sentence summary covering:
- What was merged (source count + names) and what was refreshed
- Items moved to Recently Completed this pass, with dates
- Any gaps excluded as already-resolved, and why
- Current Phase 1/gating priority — what to do first
- Total remaining items and hours
- Whether any prior-plan item couldn't be confirmed and needs the candidate's check

This skill never edits the profile on its own. A profile change is a separate, explicitly-requested step — even if this session's dedup pass surfaces a correction that belongs in `profile-facts.md` or `skills-summary.md`, note it to the candidate and wait for the candidate to ask for the profile run.

---

## Naming and File Conventions

| File | Location |
|---|---|
| Generated PDF | `outputs/{Name}_MasterLearningPlan_[Scope]_v[N]_[MonDD]_2026.pdf` |
| Role config | `profile/roles/[role-slug].json` (committed; one per recurring role) |

Version number increments by 1 each regeneration regardless of how small the change; never reuse a version number.

---

## Edge Cases

**Only one gap analysis provided:** Stop and redirect to `learning-plan-gap-analysis` — this skill exists for the merge, not single-role plans.

**No prior plan exists (first-ever merge):** Skip Step 5 (no refresh section); baseline date = date of the earliest gap analysis being merged.

**Two sources disagree on priority for the same skill** (e.g. one calls it a nice-to-have, another calls it required): Use the higher-urgency rating. Note the conflict in the Dedup Log.

**A course in the prior plan no longer exists in the Pluralsight catalog** (renamed/retired): Web-search for the replacement, note the substitution explicitly in "About This Plan" (mirror the "Cosmos DB Deep Dive retired → replaced by DP-420 course" precedent).

**More than ~35 remaining items:** Split into "Immediate" (Phase 0–2) and "Depth" (Phase 3+) PDFs rather than one oversized document.
