---
name: gap-analysis-job-description
description: >
  Produces a structured gap analysis comparing the candidate's resume and skills
  against a specific job description. Use this skill whenever the user shares a
  job posting and asks how well they match, what gaps exist, whether to apply,
  or how to frame the application. Also trigger when the user pastes a job
  description without an explicit question — the implied ask is always "how do
  I fit this?" Trigger phrases: "gap analysis", "how do I fit", "should I apply",
  "what am I missing for this role", "analyze this job", "evaluate this posting",
  "this is another example job description", or any substantial job description
  pasted into the conversation. Always use this skill — do not handle ad hoc.
  Output: downloadable markdown file + inline summary.
---

# Gap Analysis — Job Description Skill

Compares the candidate's profile against a job posting. Output: markdown file + inline
summary covering fit rating, strengths, gaps, and application strategy.

> **The report is generated deterministically — don't build it by hand.** Run
> `python -m jobomatic gap-analysis <jd_path>`
> (backed by `src/jobomatic/fit/engine.py`, the same engine `job_description_fit`
> uses) and read the written file back before summarizing it. This reads the
> profile from the vault's profile itself — you don't need to load
> `profile show` for this skill.

---

## Inputs

1. **Job description** — pasted text, uploaded file, or URL (`web_fetch` if
   URL). If it's not already a file, write it to a scratch `.md` file first —
   `gap-analysis` takes a file path, not stdin.

If the job description is missing, ask before proceeding.

---

## Step 1 — Generate the Report

Run `python -m jobomatic gap-analysis <jd_path>` and read the file it writes
(`gap-analysis.md` in the posting's folder under `outputs/applications/`). It does not
add the posting to the applications log.

**Sanity-check the result before summarizing it.** Same caveat as
`job_description_fit`: the JD parser is heading-and-bullet-driven and can
miss atypically-formatted postings. If the Summary Table looks implausibly
short or empty for how detailed the posting actually is, fall back to
reading the JD yourself and flag to the user that the automated parse looked
off — don't silently summarize a report you don't believe reflects the
actual posting.

If the report has a **Low-confidence result** section, more than half of the required
skills show no evidence. Say so, and tell the user to read the posting themselves
before relying on the rating. It does not change the rating.

If the report has a **Soft requirements** section, those are education,
years-of-experience, title-level and soft-skill lines (communication, teamwork and the
like). They are never scored and never gaps. Show them to the user as written; do not
decide whether they are met.

If the report has a **Terms to confirm** section, a word that is also a skill name
(such as "solid" in "Solid understanding of CI/CD") was read as ordinary English and
left unscored. Ask the user, once per posting, which meaning the line intends; never
decide it yourself. If it is the skill, re-run with the word in capitals in a copy of
the posting.

If the report has a **Possible typos** section, a word in a requirement is one letter
from a skill name. It was not scored. Ask the user whether the posting meant that skill,
and re-run with the word corrected in a copy of the posting if so.

For reference, the status meanings and rating thresholds the script applies:

| Status | Meaning |
|---|---|
| ✅ Match | Production experience in resume, OR resolved framing gap |
| 🟡 Portfolio | Demonstrated in own GitHub project; no production employment use |
| 🟡 Coursework | Pluralsight only; no production or project use |
| 🕰️ Legacy | Only evidenced by legacy employment (`Career_History.md`); real experience kept off the active resume by design. Surfacing it is a per-application decision — never automatic. |
| 🔴 Gap | Not in resume, portfolio, coursework, or legacy history |

| Rating | Meaning |
|---|---|
| **Strong** | All required skills ✅; 0–2 required skills are 🟡; no 🕰️; at least 2 nice-to-haves present. → Proceed to cover letter/resume generation OR learning plan for depth. |
| **Good** | All required skills ✅, 🟡, or 🕰️, short of Strong's bar (any required 🕰️ caps here). → Proceed to cover letter/resume with selective tailoring; for 🕰️ skills, ask whether to add an Earlier Experience addendum first. |
| **Worth a try** | No core requirement is 🔴 (core = in the title, on one of the first five required lines, on a line with a years figure, or mentioned on two or more lines; soft-skill lines are never core), and either a 🔴 outside the core or 3+ required skills are 🟡/🕰️; coverage 60%+. → List the gaps and ask whether to go ahead; documents only with the user's yes (`confirm_gaps`). |
| **Stretch** | 1 core requirement is 🔴; or coverage is 40–59%. → Recommend a learning plan to close the primary gaps first; if the user still wants to apply, documents only with their yes (`confirm_gaps`). |
| **Pass** | 2+ core requirements are 🔴; or coverage is under 40% → not a fit; focus on better-matched roles or significant reskilling. **Or** the posting breaks a location rule (below) → not workable from the home city, whatever the skills. |

**Location rules — a Pass regardless of skill fit.** The candidate's home city comes from the vault's location preferences, so a posting is rated **Pass** (even if every skill is ✅) when it is:
- Quebec-based (any arrangement — French-language work is out of scope);
- hybrid or on-site outside the home city;
- remote/hybrid/on-site limited to Atlantic Canada (east of Ontario is outside the working time zones); or
- listing French as a requirement (French as an *asset* is only a ⚠️ flag).

On-site/hybrid roles in the home city and remote roles in the time zones the candidate's location preferences allow are fine. Ambiguous postings never Pass on their own — e.g. "CA-Nationwide" listed beside Quebec/Nova Scotia, hybrid with no stated city, "the home province" without the home city, or a city with no stated arrangement produce a ⚠️ flag: relay it and tell the user to confirm home-province eligibility and expected hours with the recruiter before applying. This is computed in code (`src/jobomatic/fit/location.py`, rules in `src/jobomatic/fit/location_rules.json`, ADR 0008) and surfaced by `fit-check` / `gap-analysis` as a **Location & work arrangement** section — don't re-derive it by hand, and don't override it.

**Gate behavior for this skill:**
- **Strong/Good:** Analysis informs next steps — proceed to cover letter/resume generation (via `create-a-cover-letter-and-tailored-resume-for-job-description` skill) OR learning plan if reskilling needed
- **Worth a try/Stretch:** List the gaps and recommend a learning plan to close them. Proceed to cover letter/resume generation only if the user says to go ahead anyway; the tools then need `confirm_gaps` (command line: `--confirm-gaps`), which you set only after that yes.
- **Pass (skills):** Recommend a learning plan or better-matched roles. Do NOT proceed to cover letter/resume generation: a skills Pass cannot be confirmed past.
- **Pass (location):** The report's **Location & Work Arrangement** section lists the 🚫 reasons and states what the skills alone would rate. Do NOT recommend a learning plan or gap closure for this role, and do NOT proceed to cover letter/resume generation — the gaps are reference-only.
- **⚠️ location flags (any rating):** Relay each flag in the inline summary and tell the user to confirm home-province eligibility and hours with the recruiter before applying.

State the output file's path for the user.

---

## Step 2 — Inline Summary

6–8 sentences covering: fit rating · top 2 strengths · primary gap + mitigation ·
single most important resume action · whether to apply. Draw these from the
generated report's Strong Matches / Genuine Gaps / How to Frame the
Application sections — don't re-derive them independently.
