---
name: interview-practice-job-description
description: >
  Job-specific mock-interview practice. Takes a job description, works out what
  that employer will probably ask, and runs a live Q&A: one question at a time,
  scored against a rubric, with feedback and model answers grounded in the candidate's
  real experience. The question set is built from the posting's required skills
  and responsibilities (pulled from the researched .NET question bank plus
  scenario questions written for the role), "gap-pressure" questions on skills
  where their evidence is course-level or missing, behavioural (STAR) questions
  matched to the company's tone, and optional company-specific questions from
  web research. Use whenever the user pastes or uploads a job description and
  says "practice interview for this job", "mock interview for this role", "quiz
  me on this posting", "practice for my interview at [company]", "what will they
  ask me", or "drill me for this job". Generic practice with no posting →
  interview-practice. Written prep guide (DOCX) → interview-prep. Quick fit
  rating → job-description-fit. Output: live Q&A, a JD-readiness scorecard and
  an optional progress log.
---

# Interview Practice — For a Specific Job Description

Same mock-interview loop and scoring as `interview-practice`, but the questions
are chosen for **this posting**. It also tells the candidate how ready they are for each
thing the employer asked for.

> **Shared files — load as indicated** (`reference/` is the repo-root `reference/` folder; `profile/` is the vault's profile folder):
> - `reference/interview-practice-rubric.md` — the practice loop, scoring rubric, feedback format, honesty rules and wrap-up. Read in full before the first question. **This skill does not redefine them.**
> - `reference/interview-question-bank.md` — the question pool. Never show "Look for" notes before the user answers.
> - `python -m jobomatic profile show facts` — evidence tiers, differentiators, known gaps (honesty check + grounding).
> - the vault's `profile/gap-coaching.md` — for every required skill rated 🟡/🔴/🕰️.
> - the vault's `profile/star-bank.md` — for behavioural model answers. Read-only here.
> - `reference/recruiter-briefing-template.md` — only if the user wants a template to send the recruiter (Step 1).
> - `outputs/interview-practice/sessions.md` — optional prior progress.
>
> **If a required file is missing:** stop and tell the user which one.
>
> **Grounding rule:** every employer, project, course, number or outcome in a model answer traces to the profile output or `star-bank.md`; otherwise label the answer as generic. Never invent experience.

---

## Step 1 — Collect Inputs

| Input | Required | How to get it |
|---|---|---|
| Job description | ✅ | Pasted text, `.md` file, or URL (`WebFetch`). The fit-check script takes a file path, so if the JD is pasted or fetched, write it to a scratch `.md` file first. |
| Interview stage | Optional | Phone Screen / Technical Screen / Final Round. Default: Technical Screen. Ask only if not stated. |
| Recruiter briefing | Optional | Ask once: "Any notes from the recruiter about format or focus areas?" If they have notes, use them in Step 2. If not, offer the recruiter-briefing template — don't block on it. |
| Length | Optional | Quick (6) · Standard (10–12) · Long (15). Default by stage: phone 6–8, technical 10–12, final 10–12. |
| Mode | Optional | Interview mode (default) or Coach mode — see the rubric. |

## Step 2 — Read the Posting

Extract from the JD: job title, company, must-have vs nice-to-have skills,
day-to-day responsibilities, tone (enterprise/formal vs startup/casual), seniority
signals, and red flags. From the recruiter briefing (if any): format, panel,
coding test, focus areas, instructions.

## Step 3 — Get the Fit Picture (deterministic — don't re-derive)

From the repo root, run:

```bash
python -m jobomatic fit-check <jd_path>
```

Use its ✅/🟡/🕰️/🔴 statuses for each required skill exactly as printed; don't
re-judge them. Apply the sanity check from `job-description-fit` Step 2: if the
required-skills table looks implausibly short, or lists **Required lines not
scored**, read those lines yourself and say that the parse was incomplete.

Two things from the output matter here:
- **The statuses** drive which questions are "gap-pressure" questions (Step 4).
- **The rating and Location section are informational only.** Practice is useful whatever the rating — they may already have the interview — so this skill never gates on Strong/Good/Stretch/Pass. If the Location section shows a 🚫 or ⚠️, mention it in one line and carry on; don't re-run the application decision.

Then run `profile show facts` and read the matching `gap-coaching.md`
entry for every required skill that is 🟡, 🔴 or 🕰️.

## Step 4 — Build the Question Plan

Build the set from five sources. Label each question's source internally; never
repeat an ID.

| Source | What | How to choose |
|---|---|---|
| **A. Bank — required skills** | Questions from `interview-question-bank.md` whose section **Tags** match the JD's skill terms | Rank by how central the skill is in the JD (title, first bullets, repeated mentions). Required skills before nice-to-haves. Level `[M]`/`[S]` from the JD's seniority. |
| **B. Role scenarios** | 2–4 scenario questions you write from the JD's *responsibilities* ("You'd own the API behind our checkout; the p95 doubled after release — walk me through it.") | Anchor on real responsibilities and the domain; give them IDs `JD-01`, `JD-02`… |
| **C. Gap-pressure** | The question an interviewer asks when the resume doesn't show a required skill ("Our platform runs on Kubernetes — what's your experience?") | One per required skill rated 🟡/🔴 (cap 3). The *correct* answer is the **honest floor + bridge + willingness** from `gap-coaching.md`, not bluffing. IDs `GP-01`… |
| **D. Behavioural** | `BE-` questions matched to the posting's tone and responsibilities — use the "Picking `BE-` questions by role type" table in bank §13 (e.g. concurrent projects → `BE-09`, new-to-team → `BE-10`, fast learning → `BE-07`/`BE-22`, ambiguity → `BE-11`, stakeholder-facing → `BE-08`, "hit the ground running" → `BE-31`/`BE-32`) | 2–3 for a technical stage, 3–4 for phone screen and final. |
| **E. Company** | `BE-02` "Why this company/role?" plus 0–2 company-specific questions, and `BE-17` as the closer | Needs real research — see below. For `BE-17`, score the questions the user would ask against **this** posting (rubric §3): they should reference the role's actual problems, not generic §17 text. Offer to sharpen them and a `QA-12` close tailored to the JD. |

**🕰️ skills** (real but legacy, kept off the resume): don't build a question
that forces the user to surface it. Mention once, before starting, that the JD
asks for it and that the experience exists only legacy; ask whether they want
to raise it in this interview. Only then include a question.

**Company research (Source E).** If the user wants company questions or `BE-02`
coaching, run `WebSearch` for "[Company] about mission values", "[Company]
recent news" and "[Company] clients industries" (use the current year). Use only
what you actually find; if nothing useful comes back, drop the company-specific
questions and say so.

**Stage mix** (Standard length; scale proportionally):

| Stage | A (bank) | B (scenario) | C (gap) | D (behavioural) | E (company) |
|---|---|---|---|---|---|
| Phone Screen | 2 (`[J]`/`[M]`) | 0–1 | 1 | 2–3 | `BE-01` + `BE-02` |
| Technical Screen | 5–6 | 2 | 2 | 2 | 0–1 |
| Final Round | 3 (incl. an `SD-` design) | 2 | 1–2 | 3 | 1 |

If the recruiter briefing names a format (e.g. "coding exercise", "panel", "system
design"), shift the mix to match and say so.

**Do not print the question list.** Show the user a short plan — the stage,
number of questions, and the *skills being covered* (e.g. "ASP.NET Core, EF
Core, Azure Service Bus, one Kubernetes gap question, 3 behavioural") — and
begin. Revealing the actual questions would defeat the practice.

## Step 5 — Brief the User (30 seconds)

Before Q1, give a 4–6 line brief: the role in one sentence, the 3 strongest
things they can lead with (✅ skills), and the 1–3 areas the interviewer is most
likely to push on (🟡/🔴 required skills). Then start.

## Step 6 — Run the Practice Loop

Follow `reference/interview-practice-rubric.md` exactly: ground rules (§1),
technical rubric (§2) or STAR rubric (§3), bands (§4), honesty and grounding
(§5), feedback format (§6). Additions specific to a posting:

- **Gap-pressure answers** are scored on **Calibration** first. A confident, honest answer that states the real evidence level, names the nearest real experience as a bridge, and shows a concrete learning plan can score 4+. A bluff scores 1 on Calibration however polished it sounds — say why.
- **Model answers** use the JD's own vocabulary (mirror its terms) but never change the facts.
- **Role scenarios (`JD-`)**: assess for structure — clarify, hypothesise, act, verify — as well as correctness; domain knowledge from the profile's Employer & Industry Context may be used only where it's recorded there.
- **No asking about or recording protected-characteristic information.** If the JD invites self-identification, that is not part of interview practice; leave it out.

## Step 7 — Wrap Up with a Readiness Report

Deliver the rubric §7 wrap-up, then add a **JD readiness table** — one row per
required skill and the main responsibilities:

| JD requirement | Fit status | Practice score | Readiness |
|---|---|---|---|
| ASP.NET Core Web API | ✅ | 4.3 | 🟢 Ready |
| Kubernetes | 🔴 | 3.8 (honest-floor answer) | 🟡 Ready to handle the question |
| … | | | |

Readiness: 🟢 ≥ 4.5 · 🟡 3.5–4.4 · 🟠 2.5–3.4 · 🔴 < 2.5 or not covered ("not practised"). A skill that was not asked about is shown as *not practised*, not guessed.

Close with the top 3 things to fix before the interview and the study list.

Offer, in one line:
- Append this session to `outputs/interview-practice/sessions.md` (label `{Company} — {Role}`; scores and IDs only).
- A **retry round** on the weakest IDs.
- `interview-prep` for the full DOCX guide (STAR stories, company research, questions to ask) for this posting.
- `learning-plan-gap-analysis` if a real gap kept scoring low and there's time before the interview.
- `post-interview-thank-you-letter` after the real interview.

---

## What This Skill Does NOT Do

- Does not decide whether to apply and does not gate on the fit rating — use `job-description-fit` or `gap-analysis-job-description` for that.
- Does not generate the interview prep DOCX — use `interview-prep`.
- Does not write to the vault's `profile/star-bank.md`, to application tracking, or to any file other than the optional session log (and the scratch JD file).
- Does not reveal the question list, "Look for" notes or model answers before the user has answered.
- Does not invent experience, state cert status or course counts from memory, or coach the user to bluff about a gap.
- Does not ask about or record protected-characteristic information.
