---
name: cert-learning-plan
description: >
  Generates a phased PDF learning plan for a Microsoft certification exam using
  Pluralsight courses, Microsoft Learn paths, and hands-on labs. Use whenever
  the user asks for a learning plan for a Microsoft certification, says "I want
  to prepare for [cert]", "create a study plan for [exam]", "what do I need to
  study for [exam name]", "make a learning plan for AI-200 / AZ-204 / AZ-104 /
  DP-420" or similar. Also trigger when the user pastes an exam domain breakdown
  or a Microsoft Learn study guide URL. Always use this skill — do not generate
  certification learning plans ad hoc. Reads live project files at runtime so
  course coverage reflects the current state of completions.
---

# Microsoft Certification Learning Plan Skill

Produces a phased PDF learning plan scoped to a specific Microsoft exam, mapped
against existing Pluralsight, MS Learn, and lab coverage already on file.

> **PDF template:** `python -m jobomatic generate-learning-plan <role-config.json>` — a data-driven engine that renders a role config. See `templates/roles/_example.json` for the schema. Copy it, fill it, then run `python -m jobomatic generate-learning-plan <vault>/profile/roles/[role-slug].json`. The previous copy-and-fill Python workflow has been retired.
> **Verified course URLs:** the vault's `profile/course-urls.md` — check before web-searching any Pluralsight slug.
> **Coverage rubric:** `reference/coverage-rubric.md` — load to classify each domain as ✅/🟡/🔴 and assign phases.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Exam name / code | ✅ | User message (e.g. "AI-200", "AZ-104") |
| Exam study guide URL | Optional | User-pasted or `https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/[exam-code]` |
| Domain breakdown | Optional | User-pasted text OR fetched via `web_fetch` from the study guide URL |
| Target exam date | Optional | Used to set urgency banner and phase deadlines |

If the user provides only an exam name, construct and fetch the standard MS Learn study guide URL to extract domains. If the page is gated, ask the user to paste the skill-measured section.

---

## Step 1 — Load Project Files

Read all of these before proceeding — never rely on cached values:

1. `profile-facts.md` — cert status, completed domains, known gaps
2. The learning data, read with `python -m jobomatic learning list`/`lookup`/`stats` — completed Pluralsight courses and labs and completed Microsoft Learn paths and modules. Anything not in it counts as not started.
3. (Microsoft Learn completions are in the same learning data: `learning list --provider mslearn`.)
4. `course-urls.md` — verified Pluralsight slugs and MS Learn paths by gap type

Also read `reference/coverage-rubric.md` to apply the correct classification logic.

---

## Step 2 — Extract Exam Domains

From the study guide (fetched or user-pasted), extract:

- Domain name and weight percentage
- Bullet-level skills measured (these drive the line-item coverage check)

Group bullets by domain. Each domain becomes its own coverage block in Step 3.

**If the exam is AI-200:** Note that AZ-900 (per `profile-facts.md` Cert Status — confirm current certification date, don't assume April 18, 2026 is still accurate) satisfies the Azure fundamentals prerequisite. Count Azure Functions courses in `pluralsight-courses.md` (search titles containing "Azure Functions") at generation time and cite the actual current count when noting that the Azure Functions objective is covered — don't state a fixed number here, it drifts as new courses complete.

---

## Step 3 — Domain Coverage Analysis

For each domain, score every skill-measured bullet against existing coursework:

| Rating | Criteria |
|---|---|
| ✅ Strong | Completed full course(s) covering this exact service/topic; or prior production experience confirmed in `profile-facts.md` |
| 🟡 Partial | In-progress course (>10%), short course, a lab but no lecture depth, or course-level-only coverage |
| 🔴 Gap | No course, no lab, no MS Learn module on this specific service or skill |

**Coverage scoring rules:**
- Check the learning data by course title and topic keywords (`learning lookup`, `learning list --topic`), Pluralsight and Microsoft Learn alike
- Only completed work is recorded, so a course either counts (✅ or 🟡 by how fully it covers the domain) or does not (🔴); there is no in-progress credit
- Azure fundamentals (AZ-900 path, broad architecture) ≠ service-specific implementation coverage; do not use it to satisfy specific service bullets

Produce a **Domain Coverage Summary table** (inline in chat, not in the PDF) before building the plan:

```
| Domain | Weight | Coverage | Key gaps |
|--------|--------|----------|----------|
| Domain 1 — Containers | 20-25% | 🟡 Partial | Container Apps, KEDA, ACR Tasks |
| Domain 2 — Data Services | 25-30% | 🔴 Gap | PostgreSQL + pgvector, Redis vector |
| Domain 3 — Messaging | 20-25% | 🟡 Partial | Event Grid, Service Bus DLQ |
| Domain 4 — Secure/Monitor | 20-25% | 🔴 Gap | KQL, OpenTelemetry, App Config |
```

---

## Step 4 — Phase Assignment

Load `reference/coverage-rubric.md` for the detailed phase decision table. Summary:

| Phase | Colour | What goes here | Complete by |
|---|---|---|---|
| 1 | 🔴 RED | 🔴 Gap domains with zero coverage; highest-weight domains first | Immediately — before exam |
| 2 | 🟡 AMBER | 🟡 Partial — in-progress courses to finish; key service gaps with some overlap | Before exam date |
| 3 | 🟢 GREEN | Exam-aligned official review content; nice-to-have differentiators; practice assessment | Final week before exam |

**Ordering rules within a phase:**
- Sort Phase 1 by domain weight (heaviest gap first)
- Sort Phase 2 by: in-progress completions first (quick wins), then new-start gaps
- Phase 3 always includes the official Microsoft Learn course (AI-200T00-A or equivalent) if one exists

**Always exclude from the plan:**
- Courses with ✅ Strong coverage in the learning data (already done)
- Certs already passed (note in "About This Plan" text instead)
- Any course where `timing_profile` is `Full Course` and progress = 100%

---

## Step 5 — Select Courses and Look Up Durations

For each gap identified in Step 3:

1. **Check `course-urls.md`** — use the verified slug if the gap type is listed there
2. **Check the learning data** (`learning lookup`) — if the course is already completed, it does not belong in the plan
3. **`web_search`** for any course NOT in `course-urls.md` — search `site:pluralsight.com "[topic] azure"` and verify the slug is a real course page before including it
4. **MS Learn paths** — prefer free MS Learn learning paths for service-specific domains where Microsoft provides official exam-aligned content (e.g., PostgreSQL, KQL, the cert's own T00-A course)

**Duration lookup order (never leave `hrs` blank):**

1. `python -m jobomatic learning lookup "<title>"` → duration (use directly)
2. `course-urls.md` → Duration column
3. `web_search site:pluralsight.com "[course title]"` — read page for actual duration
4. Use `~X hrs` estimate only if all above fail after a search attempt

**For in-progress courses:** hrs = `(1 - progress%) × total_duration`. State as "~X hrs remaining".

**Pluralsight slug rule:** Never guess a slug. If web_search does not return a confirmed Pluralsight course page for the topic, use the MS Learn equivalent instead, or omit and note it.

---

## Step 6 — Generate the PDF

Create `profile/roles/[ExamCode].json` in the vault — copy `templates/roles/_example.json`
as a starting point and fill the JSON. The fields map 1:1 onto the previous
Python variables:

| JSON key | Content |
|---|---|
| `output` | `outputs/[ExamCode]_CertificationLearningPlan.pdf` |
| `banner.title` | Exam name + full title (e.g., `AI-200: Azure AI Cloud Developer Associate`) |
| `banner.subtitle` | `Certification Learning Plan — Pluralsight + Microsoft Learn` |
| `banner.meta` | `the candidate · [Month Year]  \|  [Any prereq certs passed]  \|  Exam live [month/year]` |
| `urgency_text` | Set if exam date is within 8 weeks; otherwise set to `null` (or omit) |
| `about_text` | 3–4 sentences: what the plan covers, item count, total hours, what's already done and excluded |
| `legend` | Three entries — RED Phase 1, AMBER Phase 2, GREEN Phase 3 |
| `plan` | Course cards built from Step 5 output, interspersed with `{type:"head",color,heading}` dividers per phase |
| `key_links` | Exam page, study guide, official T00-A course, key MS Learn paths, Pluralsight profile, any prereq cert credential link |
| `footer` | `Generated [Month Year] · the candidate · All links are direct URLs · Click to open in browser` |

```bash
python -m jobomatic generate-learning-plan <vault>/profile/roles/[ExamCode].json
```

Confirm `PDF written: [path]` and tell the user the path.

**Card source field values:** `"Pluralsight"`, `"Pluralsight Lab"`, `"MS Learn"`, `"Applied Skills"`

Run the script, confirm `PDF written: [path]` in stdout, then tell the user that path.

**ReportLab constraint:** Never use `ROWPADDING` in any `TableStyle` you add above the `DO NOT EDIT` line. Use `TOPPADDING` / `BOTTOMPADDING` per row instead.

---

## Step 7 — Present and Summarise

After stating the output path, write a 4–5 sentence inline summary covering:
- Total item count and estimated hours
- Which domain has the highest-priority Phase 1 gap and why
- What's already done and excluded (strongest existing coverage)
- Any exam deadline / urgency context
- The single most important first action (what to start today)

---

## Naming and File Conventions

| File | Location |
|---|---|
| Generated PDF | `outputs/[ExamCode]_CertificationLearningPlan.pdf` |
| Role config (JSON) | `profile/roles/[ExamCode].json` |

Exam code in filenames: uppercase, no hyphens (e.g., `AI200`, `AZ104`, `DP420`).

---

## Edge Cases

**Exam not yet generally available (beta):**
Note in the About text and urgency banner. Practice Assessment may not be available; recommend checking the exam page periodically.

**Exam retires soon (like AZ-204):**
Set `URGENCY_TEXT` with the retirement date and a warning not to start AZ-204 prep; redirect to the replacement.

**All domains already ✅ Strong:**
Skip the learning plan and produce an interview readiness guide instead (use the Phase 3 + MS Learn official course only).

**No Pluralsight course exists for a topic:**
Use MS Learn as the primary source and note it. Applied Skills labs are a strong supplement for hands-on gaps.

**More than 15 items in the plan:**
Split into two PDFs: Phase 1–2 (immediate) and Phase 3 (exam readiness). Fewer items per document improves usability.
