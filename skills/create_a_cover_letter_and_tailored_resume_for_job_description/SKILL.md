---
name: create-a-cover-letter-and-tailored-resume-for-job-description
description: "Generates a tailored cover letter and resume for a specific job posting. Use whenever the user provides a job description, job posting, or job listing and wants application documents created. Also triggers when the user says 'apply for this job', 'help me apply', 'write a cover letter for', 'tailor my resume for', or uploads a job posting. **ALWAYS checks for a prior application to this exact posting first, then runs fit assessment; only generates documents if fit is Strong or better.** Resume is loaded automatically from the profile. Job description may be provided as a .md file, pasted text, or URL. Output as DOCX files only, plus a private salary-expectations .md for the posting. Asks per posting whether to also write a separate LinkedIn Top Choice paragraph .md"
---

# Cover Letter & Tailored Resume Generator

Creates tailored cover letter + ATS-optimized resume as DOCX files, plus a private
salary-expectations markdown doc for the posting (never attached to the application). On request, also a
separate LinkedIn Top Choice paragraph markdown doc (never merged into the cover letter).
Claude writes the tailored content as JSON; `python -m jobomatic render` lays it out.

> **Content format:** `python -m jobomatic render schema resume` and `render schema cover-letter` print the JSON each document takes.
> **Profile** (run before fit assessment): `python -m jobomatic
> profile show full` —
> cert status, differentiators, portfolio projects (for cover letter highlights
> and resume bullets), and ATS keyword reference. Do NOT load
> the course lists separately; course detail comes from `learning lookup` if needed.
>
> **Grounding rule:** every claim in the resume and cover letter — employers, titles,
> dates, projects, skills, cert status — must trace to the profile output above. Never
> invent, infer, or embellish a claim that isn't there; if a strong-sounding detail
> would help but isn't in the profile, leave it out rather than making it up.

---

## 🚨 MANDATORY Step 0 — Fit Assessment Gate

**Run this step FIRST, before any other inputs. Do NOT skip. Do NOT generate documents unless fit is Strong.**

### 0a — Check for a prior application

Run the lookup first — it reads the applications log, so it does not depend on anyone's memory:

```bash
python -m jobomatic applications check <jd_path>
```

(MCP: `applications_check`.) Companies re-post the same req, and a cold re-application days or weeks later reads as a duplicate, not renewed interest. The result is one of:

- **NEW** — proceed normally.
- **RELATED** — other roles at this company, none for this one. A repeat employer with a genuinely new posting isn't a duplicate; proceed, mentioning the earlier applications.
- **DRAFTED** — documents were generated before but nothing was submitted. Proceed.
- **REPEAT** — the same posting was applied to more than ~60 days ago. Confirm it is genuinely a new posting before continuing.
- **DUPLICATE** — the same posting was applied to within 60 days. **Stop** and ask: has it had any response (screen, interview, silence)? Is there a referral or a named recruiter contact this time? Default to **not** resubmitting cold — offer a warmer route in (referral, direct recruiter outreach) or skipping it. Only if the candidate explicitly says to proceed anyway, pass `confirm_reapply=true`.
- A **no-response pattern** note (2+ earlier applications to the company, none answered) is a reason to prefer a referral or recruiter contact over another cold application.

If the log is empty or missing the posting but the candidate says they have applied elsewhere (another machine, a spreadsheet), ask once and record it: `python -m jobomatic applications applied --jd <jd_path> --date YYYY-MM-DD`. To bring an old spreadsheet tracker in, export it as CSV and run `python -m jobomatic applications import-csv <file> --dry-run` first.

**Generating documents never marks a posting as applied** — it only logs a `drafted` entry. Record "applied" only when the candidate explicitly tells you the candidate submitted it (`applications applied`, or the `applications_mark_applied` tool). Never infer it.

### 0b — Load inputs for assessment
- **Job description**: pasted text, `.md` file, or URL (`web_fetch` if URL). Ask if missing.
- **Resume + profile facts + portfolio projects**: from the profile output loaded
  above — use the Resolved Framing Gaps and Known Genuine Gaps lists, and the
  Quick Reference table to identify portfolio-level evidence for skills that
  appear in the JD.

### 0c — Parse the JD
Extract and hold in working memory:
- **Required skills** — anything marked must / required / strong / essential / years of experience in
- **Nice-to-have skills** — anything marked nice to have / asset / preferred / bonus

### 0d — Run quick match
For each required and nice-to-have skill, assign one of:

| Status | Meaning |
|---|---|
| ✅ | Production experience in resume, OR resolved framing gap from the profile output |
| 🟡 | Portfolio-level (GitHub project), course-level only (Pluralsight / MS Learn), or framing gap needing surface |
| 🕰️ | Only evidenced by legacy employment — real, but deliberately kept off the resume; ask before surfacing |
| 🔴 | Not present in resume, portfolio, coursework, or legacy history — genuine gap |

Rules:
- Never re-flag items in the Resolved Framing Gaps list from the profile output — those are always ✅.
- Check the profile output before assigning 🔴 — portfolio projects can elevate a skill from course-only to 🟡 Portfolio-level.
- Distinguish production vs. portfolio vs. course-level honestly. Do not soften 🔴 to 🟡 to make the fit look better.
- Nice-to-haves only affect the fit rating, not the gate decision.

### 0e — Display the assessment inline

Output a compact table in this format:

```
## ✅ / 🔴 Fit Assessment — [Job Title] at [Company]

**Required Skills**
| Skill | Status | Evidence |
|---|---|---|
| [skill from JD] | ✅ / 🟡 / 🔴 | [one-phrase source — employer or course] |

**Nice-to-Haves**
| Skill | Status | Evidence |
|---|---|---|
| [skill from JD] | ✅ / 🟡 / 🔴 | [one-phrase source] |

**Fit Rating: [Strong / Good / Worth a try / Stretch / Pass]**
[One sentence rationale.]
```

Keep the Evidence column to ≤ 6 words (e.g. "Acme Software, production", "CookingTime, portfolio", or "Pluralsight, 3 courses"). Only cite a portfolio project that appears as an active entry in the profile output's Portfolio Projects table — a project commented out or omitted there isn't real evidence, even if it's mentioned elsewhere in this file as an example.

Fit rating definitions:
- **Strong** — All required skills ✅; 0–2 required skills are 🟡; no 🕰️; at least 2 nice-to-haves present
- **Good** — All required skills ✅, 🟡, or 🕰️; 1–2 genuine 🔴 gaps in nice-to-haves only (any required 🕰️ caps here)
- **Worth a try** — no core requirement is 🔴 (a core requirement is named in the posting title, sits on one of the first five required lines, is on a line with a years figure, or is mentioned on two or more lines; soft-skill lines are never core), and either a 🔴 outside the core or 3+ required skills are 🟡/🕰️; coverage is 60% or more
- **Stretch** — 1 core requirement is 🔴; or coverage is 40–59%
- **Pass** — 2+ core requirements are 🔴; or coverage is under 40%; or critical domain/tech mismatch; **or** the posting breaks a location rule (below), regardless of skills

**Location rules — a Pass regardless of skill fit.** The candidate's home city comes from the vault's location preferences, so a posting is rated **Pass** (even if every skill is ✅) when it is:
- Quebec-based (any arrangement — French-language work is out of scope);
- hybrid or on-site outside the home city;
- remote/hybrid/on-site limited to Atlantic Canada (east of Ontario is outside the working time zones); or
- listing French as a requirement (French as an *asset* is only a ⚠️ flag).

On-site/hybrid roles in the home city and remote roles in the time zones the candidate's location preferences allow are fine. Ambiguous postings never Pass on their own — e.g. "CA-Nationwide" listed beside Quebec/Nova Scotia, hybrid with no stated city, "the home province" without the home city, or a city with no stated arrangement produce a ⚠️ flag: relay it and tell the user to confirm home-province eligibility and expected hours with the recruiter before applying. This is computed in code (`src/jobomatic/fit/location.py`, rules in `src/jobomatic/fit/location_rules.json`, ADR 0008) and surfaced by `fit-check` / `gap-analysis` as a **Location & work arrangement** section — don't re-derive it by hand, and don't override it.

### 0f — Apply the gate (MANDATORY)

**If fit is Strong or Good:**
→ Bold statement: **"✅ Strong fit — proceeding to generate documents."** (or **"Good fit with selective tailoring — proceeding."**)
→ Continue to Step 1 immediately. Generate documents.

**If fit is Pass because of location (🚫 in the Location & work arrangement output):**
→ Name each 🚫 reason, say skills are not the blocker, and **stop**. Do NOT generate documents, do NOT ask whether to proceed, and do NOT offer Option B (a learning plan can't fix a location mismatch). Offer only: **Option A** — help find the home city or the home province-eligible remote roles. (The MCP `generate_*` tools enforce this too — they refuse a location Pass.)

**If the fit output has a "Low-confidence result" notice:** more than half of the required skills show no evidence. Tell the user to read the posting themselves before continuing; it does not change the rating. **If it has a "Soft requirements" list:** those are education, years, title-level and soft-skill lines, never scored and never gaps; show them as written and do not decide whether they are met.

**If the fit output has a "Terms to confirm" list:** a word that is also a skill name (such as "solid" in "Solid understanding of CI/CD") was read as ordinary English and left out of the rating. Ask the user, once per posting, which meaning the line intends before continuing; never decide it yourself. If it is the skill, re-run the fit check with the word in capitals in a copy of the posting.

**If the fit output has a "Possible typos" list:** a word in a requirement is one letter from a skill name ("Typscript" for "typescript") and was not scored. Ask the user whether the posting meant that skill; if yes, re-run the fit check with the word corrected in a copy of the posting.

**If fit is Strong/Good with ⚠️ location flags:** relay the flags and ask the user to confirm eligibility/hours with the recruiter before sending the application; continue generating documents unless they say otherwise.

**If fit is Worth a try or Stretch:**
→ State the specific concerns clearly (name the 🔴 gaps, which required skills are missing, what they mean for the application).
→ Ask: **"Do you want to go ahead anyway, or would you rather:"**
   - **Option A:** Help you find better-matched positions?
   - **Option B:** Suggest a learning plan to close the primary gap?
   - **Option C:** Show you a gap analysis first?
→ Generate documents **only if the user says yes to going ahead.** The tools refuse a Worth a try or Stretch rating unless `confirm_gaps` is set (command line: `--confirm-gaps`); set it only after that yes, never by default.

**If fit is Pass (skills):**
→ State the specific concerns clearly (name the 🔴 gaps).
→ **Do NOT ask if the user wants to proceed.**
→ **Do NOT generate documents.** A Pass on skills cannot be confirmed past; the tools refuse it whatever flag is set.
→ State: **"This role is not a fit. I recommend focusing on roles that align with your core strengths. Would you like me to:"**
   - **Option A:** Help you find better-matched positions?
   - **Option B:** Suggest a learning plan to close the primary gap?

---

## Step 1 — Gather Remaining Inputs
(Runs only after the gate passes)

- **Job description**: already loaded in Step 0.
- **Resume**: already loaded in Step 0.
- **Profile facts**: already loaded in Step 0.
- **Portfolio projects**: already loaded in Step 0.
- **Salary screen:** it is computed in code, not by hand. The `fit-check` output (CLI or the `fit_check` tool) ends with a **Salary screen** block comparing the posted pay with the candidate's private minimums. If it shows 🔴 (top end below the minimum), say so now and ask whether to continue before generating anything; only if the candidate says yes, pass `confirm_below_minimum=true`. USD pay, an unclear hourly figure, or no minimums configured appear as ⚠️ notes — relay them, don't judge them. No posted pay means no block. The minimums live in `private/search-constraints.json` (gitignored); `python -m jobomatic constraints show` prints them. Never write them into a tracked file.
- **LinkedIn Top Choice check (ask every time — don't assume):** ask **"Do you want a LinkedIn Top Choice paragraph for this posting? It goes in its own markdown file, not in the cover letter."** Only offer it if the user has marked, or will mark, this job as a Top Choice on LinkedIn. It is a per-posting decision: a past yes does not carry over, and no/unclear means skip it. Record the answer (yes/no) for Step 5.7. If yes, ask for the reason this role is a top pick if it isn't obvious from the JD and the profile.

---

## Step 2 — Analyze the JD
Extract and keep in working memory: job title + company · **5–8 ATS keywords** (copy JD wording exactly) · 3–5 nice-to-haves · tone (startup vs enterprise) · key responsibilities · must-haves/disqualifiers.

---

## Step 3 — Extract Contact Info
Use values exactly as written in the profile output. Do not paraphrase, reformat, or infer:
`name · email · phone · linkedin · github · pluralsightUrl`

---

## Step 4 — Plan Content

**Resume:** Summary (2 lines, exact role + 2–3 ATS keywords) · Skills (ATS keywords first, remove irrelevant categories) · Experience bullets (reorder/reword by JD relevance) · Cert status: use values from the profile output.

**Legacy history:** the generated resume always ends Professional Experience with the profile's one-line "Additional Experience" summary (`raw_sections["Additional Experience"]` — no dates, no bullets); legacy roles never get full entries. If any required skill is 🕰️, ask before generating whether to surface it for this application (an Earlier Experience addendum or a cover-letter mention) — never add it automatically.

**Always include the "Professional Development & Portfolio Building" (May 2025–Present) entry — never omit it entirely.** It's the only entry bridging the most recent employer to today; dropping it makes every tailored resume look like an unexplained gap since 2025, regardless of the posting. Trim it to 2–3 bullets most relevant to the JD (its underlying content is broad — Azure/AI-200-heavy in places — so cut for relevance same as any other role), but the entry itself always stays, positioned first per the reverse-chronological rule in Project 2's CLAUDE.md.

**Education & Certifications — always include, verbatim from the profile.** Read it from the profile's `## Education & Certifications` section (or `resume.education` in the typed profile for the degree/diploma entries specifically) and reproduce every entry as-is — institution, credential, and dates included. Do not omit the section, do not omit dates, and do not soften or generalize a credential (e.g. don't turn a diploma into a "degree"). This was a deliberate, explicit decision by the candidate — the legacy-history / no-dates caution that applies elsewhere in this system (see Project 2's `Career_History.md` convention) does **not** apply to this section; the candidate chose to disclose full education history including graduation years. Don't re-litigate that choice per-application.

**Page 2:** Run the script first, then open the output and check page count. If it spills to page 2, uncomment `page2Header()` and position it before the job that starts on page 2.

**Cover letter — STRICT ONE PAGE MAXIMUM. No exceptions.**
Hook (strongest match to top JD requirement, NOT "I am writing…") · WHAT I BRING (4–5 items max: ATS keyword → evidence, 1 line each — never 2) · TWO HIGHLIGHTS (2 most relevant employers + concrete detail, 1–2 lines each) · Closing (company/role interest + direct CTA, 2 sentences max) · Tone: enterprise = formal, startup = direct.

**Cover letter content budget — enforce before writing any bullet:**
- Hook: 2 sentences max
- WHAT I BRING bullets: 4–5 items; each body text must fit on one line (≤ 120 chars) — cut ruthlessly if needed
- TWO HIGHLIGHTS bullets: 1–2 lines each; combine detail into a single sentence where possible
- Closing: 2 sentences max
- If content feels tight, cut a WHAT I BRING bullet entirely rather than letting any bullet run long

**Top Choice stays out of the cover letter.** It is written as its own file in Step 5.7, so the one-page budget above is unaffected.

When selecting cover letter highlights and WHAT I BRING evidence, check the profile output's Portfolio Projects table for active projects that demonstrate the JD's key requirements — use only what's listed there (e.g. Resume_Site for GitHub Actions CI/CD, ai-job-search-workflow for Python/AI tooling, CookingTime for .NET/Blazor/testing discipline), and confirm each one still appears before citing it, since projects get added or retired. Prefer production employers for highlights, but use portfolio projects as secondary evidence when they directly address a required skill. Do not invent a highlight, metric, or project detail not present in the profile output — cut a bullet rather than fabricate one.

---

## Step 5 — Generate DOCX

Write the tailored content from Step 4 as two JSON files (in the scratchpad, not the repo), then lay them out:

1. `python -m jobomatic render schema resume` and `render schema cover-letter` show the fields and their limits (a resume summary is at most 2 lines and 7 skill lines; a letter has 1–5 "What I Bring" items and at most 2 highlights).
2. Resume content: contact (from `profile show contact`), tagline, summary, skills (most JD-relevant first), experience (bullets reordered by relevance), additional experience, education, and certification lines. Cert lines come from the profile's cert table (Certified or In progress).
3. Cover-letter content: contact, role title, company, hook, bring items, highlights, closing.
4. Render both against the posting, which files them in its application folder and logs the posting as `drafted` (never applied):

```bash
python -m jobomatic render resume <resume.json> --jd <jd_path>
python -m jobomatic render cover-letter <letter.json> --jd <jd_path>
```

Bad content stops with the field that is wrong. Layout is not editable; if a page overflows, cut content. Add `--check-pages` to either `render` command to count the real pages with LibreOffice: it fails (exit 1, file kept) when a resume is over 2 pages or a letter is not exactly 1.

**ATS rules:** no tables · no columns · no text boxes · no graphics · standard section headings · no color beyond the section rules · one font throughout · resume ≤ 2 pages · cover letter = 1 page.

---

## Step 5.5 — Optional Audit Pass (script cross-check)

`generate_resume.py`/`generate_cover_letter.py` (the deterministic scripts
behind `python -m jobomatic generate-resume`/`generate-cover-letter`)
build the same kind of content from the profile, but select ATS keywords,
skills, and bullets by simpler rule-based logic — not full parity with this
skill's JD-tailored judgment (no per-bullet character-budget enforcement, no
startup-vs-enterprise tone switching, and `generate_resume.py` trims to two pages
by position, not by rereading the posting: oldest roles lose bullets first). **This step
does not replace the documents you just generated** — it's an optional,
advisory second pass to catch coverage gaps, not a content source.

If you want the extra confidence, run it against a scratch path (not the
real deliverable filenames):

```bash
python -m jobomatic generate-resume <jd_path> --out outputs/tmp/audit_resume.docx --check-pages
python -m jobomatic generate-cover-letter <jd_path> --out outputs/tmp/audit_cover_letter.docx
```

Open both and compare against the documents from Step 5 — not for wording
parity (expected to differ), but for **structural coverage**: does the
audit version reference a required or nice-to-have skill that's genuinely
missing from your version entirely? Does it include a section heading yours
lacks? If something material surfaces, fix it in the real deliverable, not
by substituting the audit copy. Delete the `outputs/tmp/audit_*` files
afterward — they're a check, not a keeper.

---

## Step 5.6 — Salary Expectations Doc (always)

Write `salary.md` in the application's folder (`python -m jobomatic application-dir <jd_path>` prints it; the resume and cover letter are already there). It is for the candidate's eyes only. It is not attached to the application, and it never goes into the resume or cover letter.

**Inputs.**
- The JD's stated pay range, bonus, and any other compensation or benefits it names. If the JD has no range, say so in the doc.
- Market anchors in CAD. First read the newest `outputs/research/SalaryResearch_*.md`. If one exists from the last ~3 months and covers a comparable role and location (remote Canada vs. hybrid the home city), reuse its figures and cite it by filename. Otherwise run the salary-research skill's required searches for this role. Never invent a figure. Label every number with its source and date, and mark thin or single-source data as low confidence.
- Experience level from the profile: 10+ years enterprise .NET and `{cert_status_short}` (fill from the profile's Copy Fragments, never leave the literal placeholder). Cert premium only counts as a factor when the JD's stack actually uses what the certs cover.

**Structure.**

```
# Salary Expectations — [Role] at [Company]
The candidate · [Month YYYY] · All figures in CAD

## Posting
[Posted range, bonus, benefits, location/remote terms. "No range posted" if none.]

## Market Anchors
| Source | Figure | Date | Confidence/notes |

## Recommendation
**Target ask:** [range]
**Negotiation floor:** [number + one-line rationale]
**Walk-away minimum:** [from `python -m jobomatic constraints show`: the permanent base and the contract hourly figure; base salary only, so bonus and RRSP match don't count toward the salary figure. If no minimums are configured, ask the candidate rather than guessing.]
**Where the posted range sits:** [below / inside lower half / inside upper half / above market, with the reason]

## Ready-to-Paste Answer
[One or two plain sentences for an application form or recruiter screen asking for salary expectations. Give a range, not a single number. The range starts at the walk-away minimum (from `constraints show`) and ends at the top of the target ask. The candidate chose this on 2026-10-07; when the posted range starts above the minimum, note in Caveats that a range starting at the minimum signals willingness to go below what the posting offers.]

## Total Compensation Notes
[Bonus, RRSP match, benefits, learning budget, vacation: what is worth weighing against base.]

## Caveats
[Anything uncertain: single-source data, an unrecorded detail, a gap that affects leverage.]
```

**Rules.**
- The walk-away minimum is a different number from the negotiation floor. The floor is where to push back before saying yes; the minimum is the lowest the candidate would accept. Show both. If a posted range tops out below the minimum, say so at the top of the doc. The minimum is the low end of the range the candidate states on forms and in screens, but the negotiation floor and target ask in the doc stay unchanged, and the candidate negotiates up from the target ask, not from the minimum.
- If the target ask falls above the posted range, say so plainly and note the risk. Don't quietly shade it down or up.
- Keep it grounded: leverage comes from the fit assessment and profile evidence, not from claims the profile doesn't support.
- No protected-characteristic or self-identification information, ever, per the repo-wide rule.

---

## Step 5.7 — LinkedIn Top Choice Doc (only if the user said yes in Step 1)

Write `top-choice.md` in the same application folder. Skip this step entirely on a no. It is a paragraph to paste into LinkedIn, so it is not a DOCX and not part of the cover letter or resume.

**Content.** A short heading line (`# LinkedIn Top Choice — [Role] at [Company]`), then one paragraph, 2–3 sentences, plain first-person wording per `reference/writing-style.md`:
- Sentence 1: why this role, using one concrete reason from the JD (product, domain or stack).
- Sentence 2: the closest matching evidence from the profile (employer, project, or skill), stated as a fact.
- Optional sentence 3: a plain call to action, such as availability for a call.

**Rules.**
- Every claim traces to the profile or the JD. Keep the production, portfolio and course-level distinction.
- No enthusiasm filler (see the Avoid list in the writing style file) and no protected-characteristic or self-identification information.
- Keep it under 600 characters unless the user says LinkedIn's field allows more. Print the character count under the paragraph.
- Run the paragraph through `src/jobomatic/documents/humanize.py` (`find_ai_tells`) and fix anything it flags.

---

## Step 6 — Validate and Present

No automated DOCX validator is available locally (the sandbox's `/mnt/skills/public/docx/scripts/office/validate.py` doesn't exist in Claude Code). Open each DOCX in the application's folder and visually confirm formatting — page count, section headings, no broken layout — before delivering it. LibreOffice is installed as a Flatpak (no `soffice` on `PATH`): convert each DOCX to PDF and read the real page count with the command in Project 1's `CLAUDE.md` under "DOCX page-count check" — use absolute paths — rather than estimating.

Fix errors before presenting. Naming: the generators write `resume.docx` and `cover-letter.docx` into `outputs/applications/<date>_<company>_<role>/` (the folder name is also the application's id in the log). Confirm the files are there and tell the user their paths: the resume DOCX, the cover letter DOCX, `salary.md`, and `top-choice.md` when requested.

Inline summary: ATS keywords incorporated · gaps excluded · assumptions made · whether a Top Choice doc was written · the salary doc's target ask and floor (one line).
## Writing style

Before drafting any prose, follow `reference/writing-style.md`: plain, professional-but-casual, no AI filler. Treat `WARNING: AI-sounding wording` output from the generator as something to fix.
