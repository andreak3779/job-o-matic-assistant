---
name: learning-plan-gap-analysis
description: >
  Generates a prioritised learning plan PDF from a completed gap analysis.
  Use whenever the user asks for a learning plan, study plan, or course list
  after a gap analysis has been produced — or asks "what should I study for
  this role", "what courses do I need", "create a learning plan", or "how do
  I close these gaps." Always use after a gap analysis — do not generate ad hoc.
  Output is a PDF with clickable links. If no genuine gaps exist, produce an
  interview readiness plan instead.
---

# Learning Plan — Gap Analysis Skill

Converts a gap analysis into a phased PDF learning plan with verified clickable
links. Sources: Pluralsight · Microsoft Applied Skills (free) · Microsoft Learn.

> **Upstream input:** This skill consumes gap analyses from `gap-analysis-job-description`. Fit ratings (Strong/Good/Stretch/Pass) from the gap analysis determine which plan type is generated and how priorities are assigned.
> **Before selecting courses:** Load `course-urls.md` (the vault's `profile/` folder) — verified
> slugs by gap type. Do not guess slugs; search if a course isn't listed.
> **Before generating PDF:** Write a role config `profile/roles/[role-slug].json`
> (copy `templates/roles/_example.json` as a starting point) and run
> `python -m jobomatic generate-learning-plan <vault>/profile/roles/[role-slug].json`. The old copy-and-fill
> Python workflow has been retired.

---

## Inputs

1. **Gap analysis** — markdown from `gap-analysis-job-description` skill, or
   pasted gaps. If missing: "I need the gap analysis first."
2. **Job context** — role title + company (from gap analysis header).
3. **Active application?** — yes = Priority 1 urgency increases.

---

## Step 1 — Classify Plan Type

Consult the fit rating from the gap analysis output:

- **Fit rating is Strong or Good** (all required skills ✅ or 🟡; ≤ 1–2 gaps in nice-to-haves) → Standard phased plan (Priority 1 / 2 / 3)
  - Strong fit: focus on nice-to-have depth (Priority 2–3)
  - Good fit: close 1–2 gaps before phone screen (Priority 1–2)
- **Fit rating is Worth a try, Stretch or Pass** (a core requirement is 🔴, or coverage is low) → Accelerated Priority 1 plan; close critical gaps before applying
- **No genuine gaps** (Strong fit, framing gaps only) → Interview Readiness plan

---

## Step 2 — Assign Priorities

| Priority | What | Complete by |
|---|---|---|
| 1 | 🔴 Genuine gaps; critical must-haves with zero coverage | Before applying |
| 2 | 🟡 Framing gaps; course-level skills; important nice-to-haves | Before tech screen |
| 3 | Differentiators; interview depth; elevates good to exceptional | Before final round |

Rules: active application → P1 within 1–2 weeks · AI-200 domain gaps → P2/P3 (exam live but no imminent deadline) · resolved resume gaps → P2/P3 (vocabulary only, not P1).

**Mapping from gap analysis fit rating:**
- Gap analysis "**Pass**" → All Priority 1 (strongly recommend rethinking the application or committing to major reskilling)
- Gap analysis "**Stretch**" → Priority 1 for must-haves; Priority 2 for nice-to-haves
- Gap analysis "**Good**" → Priority 1 for must-haves with gaps; Priority 2–3 for nice-to-haves
- Gap analysis "**Strong**" → Priority 2 for framing gaps; Priority 3 for differentiators

---

## Step 3 — Select Courses

Load `course-urls.md` (the vault's `profile/` folder). Match each gap to the best source:

| Gap type | Source |
|---|---|
| Genuine gap (new topic) | Pluralsight Getting Started/Fundamentals |
| Framing gap (depth) | Pluralsight Deep Dive/Best Practices/Advanced |
| Azure hands-on gap | Pluralsight course + Applied Skills lab |
| AI-200 domain | Pluralsight + Applied Skills + Microsoft Learn |

If a course isn't in `course-urls.md`, use `web_search` to verify the slug
before including it. Never guess a Pluralsight slug.

---

### Duration lookup — `hrs` field in course cards and Summary table

Use this lookup order before writing any `hrs` value. Never leave `hrs` blank or write "FILL hrs".

1. **Run `python -m jobomatic learning lookup "[course title]"`** — it gives the duration of any completed course; never load `items.yaml` whole
2. **Check `course-urls.md`** — if the course row has a Duration value (not `—`), use it directly
3. (A course that is not in the learning data has not been completed; look it up by the steps below.)
4. **`web_search site:pluralsight.com "[course title]"`** — required for any course where Duration is `—` (Short Course or Lab entries) or NOT FOUND anywhere above; read the course page for the actual duration
5. Use `~X hrs` estimate **only** if none of the above resolve after a search attempt

**`timing_profile` guide:**
- `Full Course` · `Full Lab` → Duration is reliable; use directly (no web search needed)
- `Short Course` · `Lab` → Duration is `—`; must web_search for the actual value before writing `hrs`

---

## Step 4 — Generate the PDF

```bash
pip install reportlab --break-system-packages -q
```

1. Create (or update) `profile/roles/[role-slug].json` from `templates/roles/_example.json`
2. Fill the JSON fields (banner, legend, plan, key_links, footer) per the
   schema documented in `project-2/CLAUDE.md`
3. Run: `python -m jobomatic generate-learning-plan <vault>/profile/roles/[role-slug].json`
4. Tell the user the PDF's path under `outputs/` (the value comes from the
   JSON's `output` key)

File naming: `[Company]_[RoleShortTitle]_LearningPlan.pdf` (this is the
value of `output` inside the JSON, not derived from the filename).

### Certification urgency

Read current status from `profile-facts.md` (or
`python -m jobomatic profile show section "Cert Registry"`
— don't load the full ~11.5K-token `profile show` just for this)
at generation time rather than assuming the row below is still accurate — a cert shown
here as "in progress" may since have been passed, and the row must change accordingly:

| Cert | Deadline | Action |
|---|---|---|
| AZ-900 | Passed April 18, 2026 | Note in plan header as complete |
| AI-200 | Live July 2026 | Phase 2/3 for Azure roles; no imminent deadline — **if the profile shows this cert as passed, replace this row with "Note in plan header as complete" instead** |

---

## Step 5 — Present and Summarise

After stating the output path, give a 4–5 sentence inline summary:
item count · total hours · Priority 1 ask · any time-sensitive deadline ·
what to do first.

---

## Plan Formats

### Standard Plan sections (in order)
Banner → legend → About This Plan → course cards by phase → Quick Reference Table → Key Links → footer

### Interview Readiness Plan sections
Banner → legend → About This Plan → Before Phone Screen → Before Tech Screen →
Before Final Round → STAR Story Prep → Quick Reference Table
