---
name: job-description-fit
description: >
  Quick fit check against a specific job posting — produces a fit rating and
  inline skills table only; no gap analysis report is generated. Use whenever
  the user pastes or uploads a job description and wants a fast yes/no on fit
  before committing to a full gap analysis or application documents. Trigger
  phrases: "quick fit check", "am I a fit for this", "does this match my skills",
  "what's my fit rating", "rate my fit", "check this job", or any job description
  pasted without an explicit request for a full report. Also trigger when the user
  says "should I apply?" and has not yet run a gap analysis. If Strong or Good,
  prompts the user to generate a cover letter and resume. If Worth a try or Stretch,
  lists the gaps and asks whether to go ahead. If a skills Pass, states the fit
  and stops — no document generation. A role outside the candidate's
  location constraints (Quebec, hybrid/on-site outside the home city, Atlantic-only
  remote, French required) is always a Pass, whatever the skill match. Always
  use this skill for quick fit checks — do not handle ad hoc.
---

# Job Description Fit — Quick Check

Produces a compact fit rating + skills table in one step. No gap analysis
report is written. If the fit is Strong or Good, offers to generate tailored
cover letter and resume via the `create-a-cover-letter-and-tailored-resume-for-job-description` skill.

> **Fit computation is deterministic — don't re-derive it by hand.** Run
> `python -m jobomatic fit-check <jd_path>` (backed by
> `src/jobomatic/fit/engine.py`, which already implements the ✅/🟡/🔴 rules and the
> Strong/Good/Stretch/Pass thresholds below) and present its output directly.
> This reads the profile from the vault's profile itself — you
> don't need to load `profile show` for this skill at all.

---

## Step 1 — Load Inputs

- **Job description**: pasted text, `.md` file, or URL (`web_fetch` if URL).
  If missing, ask before proceeding. If the JD is pasted text or fetched from
  a URL rather than an existing file, write it to a scratch `.md` file first
  — `fit-check` takes a file path, not stdin.

---

## Step 2 — Run the Fit Check

Run `python -m jobomatic fit-check <jd_path>` from the repo root and
take its printed markdown table as the fit assessment — do not manually
re-parse the JD or re-derive the ✅/🟡/🔴 statuses.

**Sanity-check the result before presenting it.** The underlying JD parser is
heading-and-bullet-driven and can miss atypically-formatted postings (no
recognizable "Requirements" heading, prose-only requirements, etc.) — if the
required-skills table looks implausibly short or empty for how detailed the
posting actually is, fall back to reading the JD yourself, parsing required
and nice-to-have skills manually, and note to the user that the automated
parse looked off. Do not silently present a table you don't believe reflects
the actual posting.

Sentence-style requirements ("Experience building Azure applications using
event-driven architectures") are reduced to the skill terms in them (ADR 0009).
If the output has a **Required lines not scored** list, those lines named no
technology the parser knows — read each one yourself and say so in your summary,
because the rating does not cover them. If the table is full of 🔴 rows that are
whole sentences, the extraction missed; treat the rating as unreliable and parse
by hand.

If the output has a **Low-confidence result** notice, more than half of the required
skills show no evidence. Say so, and tell the user to read the posting themselves
before relying on the rating. It does not change the rating.

If the output has a **Soft requirements** list, those are education,
years-of-experience, title-level and soft-skill lines (communication, teamwork and the
like). They are never scored and never gaps. Show them to the user as written; do not
decide whether they are met.

If the output has a **Terms to confirm** list, a word that is also a skill name
(for example "solid", which is an adjective in "Solid understanding of CI/CD" but
the SOLID design principles elsewhere) was read as ordinary English and left out
of the rating. Ask the user, once per posting, which meaning the line intends.
Never decide it yourself. If it is the skill, say what it would add, and re-run
with the word written in capitals in a copy of the posting; if not, drop it.

If the output has a **Possible typos** list, a word in a requirement is one letter
from a skill name ("Typscript" for "typescript"). It was not scored, because the
tool never guesses. Say so, and ask the user whether the posting meant that skill;
if yes, re-run with the word corrected in a copy of the posting.

For reference, the status meanings and rating thresholds the script applies:

| Status | Meaning |
|---|---|
| ✅ | Production experience in resume, OR resolved framing gap |
| 🟡 | Portfolio-level (GitHub project) or course-level only (Pluralsight / MS Learn) |
| 🕰️ | Only evidenced by legacy employment (`Career_History.md`) — real experience, deliberately not on the active resume |
| 🔴 | Not present in resume, portfolio, coursework, or legacy history — genuine gap |

- **Strong** — All required skills ✅; 0–2 required skills are 🟡; no 🕰️; at least 2 nice-to-haves present
- **Good** — All required skills ✅, 🟡, or 🕰️, short of Strong's bar. Any required 🕰️ caps the rating at Good.
- **Worth a try** — no core requirement is 🔴 (a core requirement is named in the posting title, sits on one of the first five required lines, is on a line with a years figure, or is mentioned on two or more lines; soft-skill lines are never core), and either a 🔴 outside the core or 3+ required skills are 🟡/🕰️; coverage is 60% or more
- **Stretch** — 1 core requirement is 🔴; or coverage is 40–59%
- **Pass** — 2+ core requirements are 🔴; or coverage is under 40%; **or** the posting breaks a location rule (below), regardless of skills

Coverage = (✅ + ½ × (🟡 + 🕰️)) ÷ required skills. The rating is computed in code from these counts (ADR 0021); read it from the output, never re-derive it.

**Location rules — a Pass regardless of skill fit.** The candidate's home city comes from the vault's location preferences, so a posting is rated **Pass** (even if every skill is ✅) when it is:
- Quebec-based (any arrangement — French-language work is out of scope);
- hybrid or on-site outside the home city;
- remote/hybrid/on-site limited to Atlantic Canada (east of Ontario is outside the working time zones); or
- listing French as a requirement (French as an *asset* is only a ⚠️ flag).

On-site/hybrid roles in the home city and remote roles in the time zones the candidate's location preferences allow are fine. Ambiguous postings never Pass on their own — e.g. "CA-Nationwide" listed beside Quebec/Nova Scotia, hybrid with no stated city, "the home province" without the home city, or a city with no stated arrangement produce a ⚠️ flag: relay it and tell the user to confirm home-province eligibility and expected hours with the recruiter before applying. This is computed in code (`src/jobomatic/fit/location.py`, rules in `src/jobomatic/fit/location_rules.json`, ADR 0008) and surfaced by `fit-check` / `gap-analysis` as a **Location & work arrangement** section — don't re-derive it by hand, and don't override it.

---

## Step 3 — Apply the Gate

### If fit is Strong or Good:

State: **"✅ [Strong / Good] fit — would you like me to generate a tailored cover letter and resume for this role?"**

**Salary screen.** After the skills table, `fit-check` prints a **Salary screen** block when the posting states pay, comparing it with the candidate's private minimums (`private/search-constraints.json`, never written into tracked files). Relay it as written: 🔴 means the top end is below the minimum — say so and ask whether to continue; ⚠️ notes (USD pay, unclear hourly figure, no minimums configured) are for the candidate to judge. It never changes the fit rating.

**Prior application.** If the rating is Strong or Good, also run `python -m jobomatic applications check <jd_path>` before offering to generate documents, and surface a DUPLICATE or no-response-pattern result.

If any required skill is 🕰️, say so first: name the skill and that its only evidence is legacy work kept off the resume by design. Ask whether to surface it for this application (a short "Earlier Experience" addendum or a cover-letter mention) before handing off. Never add it automatically.

- If the user says **yes** (or equivalent) → hand off to `create-a-cover-letter-and-tailored-resume-for-job-description`. The fit assessment above satisfies the fit-check portion of that skill's Step 0, but its Step 0a (prior-application check) still hasn't run here — ask it before proceeding, then skip straight to Step 1.
- If the user says **no** → stop. Offer no further output.

### If fit is Strong or Good but the output has ⚠️ location flags:

Present the flags before the offer to generate documents, and say the user should confirm eligibility/hours with the recruiter (e.g. whether home-province residents can take a "Canada-wide" remote role). The rating is unchanged — the flag is a to-do, not a refusal.

### If fit is Pass because of location (🚫 in the Location & work arrangement section):

Name each 🚫 reason and note that **skills are not the blocker** (the rationale states what the skills alone would have rated). Do **not** recommend a learning plan or gap closure for this role — it wouldn't change the outcome.

State: **"This role is outside your location constraints. Focus on the home city on-site/hybrid roles or remote roles open to the home province."**

**Do NOT offer to generate application documents.** **Do NOT ask if the user wants to proceed anyway.** Stop here.

### If fit is Worth a try or Stretch:

State the specific gaps clearly — name each 🔴 required skill gap, what it means for candidacy, and (for Worth a try) that nothing core is missing.

Then ask: **"Do you want to go ahead anyway? I can generate the resume and cover letter; the gaps stay yours to frame honestly."**

- If the user says **yes**, hand off to the cover-letter skill and tell it the user confirmed the gaps. The document tools only generate past a Worth a try or Stretch rating when `confirm_gaps` is set (command line: `--confirm-gaps`), and you set it **only after the user says yes**.
- If the user says no or does not answer, stop here.

### If fit is Pass (skills):

State the specific blockers clearly — name each 🔴 required skill gap and what it means for candidacy.

Then state: **"This role is not a fit right now. Focus on roles that align with your core strengths."**

**Do NOT offer to generate application documents.** A Pass on skills cannot be confirmed past; the tools refuse it whatever flag is set.
**Do NOT ask if the user wants to proceed anyway.**

Stop here.

---

## What This Skill Does NOT Do

- Does not write a gap analysis markdown file
- Does not emit a GapAnalysis_Bridge.md (no genuine-gap report is generated here — run the full `gap-analysis-job-description` skill if a Bridge file is needed for learning plan generation)
- Does not generate cover letters or resumes directly — it hands off to the cover letter skill after the user confirms
- Does not produce a resume tailoring strategy or application angle — use `gap-analysis-job-description` for that level of detail
