# Interview Practice — Practice Loop and Scoring Rubric

Loaded by `interview_practice` (Steps 3–5) and `interview_practice_job_description` (Step 6). Both skills run the **same loop and the same rubric** so scores are comparable between a generic session and a job-specific one.

---

## 1. Ground rules for the interviewer role

- **One question at a time.** Ask, then stop and wait. Never list upcoming questions or reveal "Look for" notes before the user answers.
- **Act like a real interviewer, not a tutor, until the answer is in.** No hints unless asked. Accept: `hint`, `skip`, `repeat`, `retry`, `stop`, `pause`.
  - `hint` → one nudge (a keyword or the angle, not the answer). The question is then scored with a "hinted" tag and capped at 4.0.
  - `skip` → score 0, tag `skipped`, and give the key points so the gap is still closed.
- **At most one follow-up probe per question**, and only when the answer is shallow or ambiguous ("What would you do if two users saved at once?"). Score the answer and the follow-up together.
- **Typed answers are fine.** Assess content and structure; ignore typos. Aim technical answers at ~60–120 seconds spoken (roughly 150–300 words) and behavioural answers at 2–3 minutes (see §3); flag answers that ramble well past those lengths or that are one-liners on a non-lightning question.
- **Calibrate to the role level.** Score against what the target level (`[J]`/`[M]`/`[S]`) would be expected to say. A correct but surface-level answer is a 3 on a `[S]` question.
- **Be honest, not harsh and not generous.** `3` means "acceptable, would not lose the interview". Reserve `5` for answers you would hire on.
- **Never invent or inflate the user's experience** — in feedback, in model answers, or in "what you could say". See §5.
- **Protected characteristics.** Never raise, infer or store protected-characteristic information (identity, age, disability, family status, etc.) in questions, feedback, model answers or the session log. If the user volunteers something, don't carry it into any file.

---

## 2. Technical-question rubric (non-behavioural)

Score each dimension 1–5, then average to one decimal for the question score.

| Dimension | 1 | 3 | 5 |
|---|---|---|---|
| **Correctness** | Wrong or misleading | Mostly right, minor slips | Fully accurate, precise terminology |
| **Depth & trade-offs** | Definition only | Explains how/why | Names trade-offs, failure modes, alternatives, "it depends on X" |
| **Clarity & structure** | Disorganised | Understandable | Answer first, then reasoning; concise; checks understanding |
| **Evidence** | No example | Generic example | Specific real project/situation with outcome |
| **Calibration** | Bluffs / overclaims | Mostly honest | States what it is and isn't experience-wise; gaps handled with a bridge |

Not every dimension applies to every question. For `LR-` lightning questions, score **Correctness only** (0 / 3 / 5: wrong / partly / right and precise) and don't penalise the missing example.

## 3. Behavioural-question rubric (`BE-`)

Score each 1–5 and average.

| Dimension | What a 5 looks like |
|---|---|
| **Situation & Task** | Context in 1–2 sentences; the user's own responsibility is clear |
| **Action** | Specific steps in the first person ("I"), not "we"; shows judgement, not just activity |
| **Result** | An *outcome*, not a duty: quantified or concretely observable, ideally in the form "accomplished X, as measured by Y, by doing Z"; honest about limits |
| **Reflection** | What was learned or would be done differently |
| **Relevance & delivery** | Fits what the question asked; roughly 2–3 minutes spoken (about 250–400 words typed); ends cleanly |

Other things to credit or flag in any answer: a short pause to think is fine (don't penalise a considered start); naming the answer's structure (STAR, CAR, HERO) is fine but not required; "I don't know" on its own is a 1 on Depth, but "I haven't used that, here's how I'd find out / the closest thing I have done is…" is a good answer and scores on Calibration. Flag criticism of a past employer or teammate, blaming language, memorised-sounding delivery, and answering a different question from the one asked.

**Questions-to-ask answers (`BE-17`, `QA-`).** When the user gives the questions they would ask, score each question 1–5 on: *specific to this role/interviewer* · *shows homework (not answerable by the website)* · *about outcomes, team or growth, never logistics* · *appropriate for the stage and interviewer* (e.g. `QA-07` only after round one). Reward at least one question about what success looks like. In the 🎯 line, suggest sharper versions from the `QA-` pool and, for the closing move, a `QA-12` "consultant close" tailored to the conversation.

## 4. Score bands

| Question score | Band | Meaning |
|---|---|---|
| 4.5 – 5.0 | 🟢 Interview-ready | Say it this way in the interview |
| 3.5 – 4.4 | 🟡 Solid — tighten | Right substance; sharpen structure/evidence |
| 2.5 – 3.4 | 🟠 Needs work | Gaps in depth or correctness; re-practise |
| < 2.5 | 🔴 Re-study | Learn the concept, then retry the question |

---

## 5. Honesty and grounding (non-negotiable)

Before writing any model answer or "stronger version":

1. Load facts with `python -m jobomatic profile show facts` (small). Use `full` only if a behavioural answer needs work-history detail you can't get from `star-bank.md`.
2. Every employer, project, course, number or outcome in a model answer must trace to the profile output or the vault's `profile/star-bank.md`. If the evidence isn't there, say so and give a generic best-practice answer **labelled as such** — don't borrow a plausible-sounding project.
3. **Overclaim check.** If the user's answer claims experience, compare it with the profile. Flag any claim that is stronger than the evidence tier (production > portfolio > course/lab > none). Example: "I run Kubernetes in production" when the profile shows course-level only. Offer the honest-floor wording instead.
4. **Known gaps / learning-level skills.** If the question touches a profile "Known Genuine Gap", or a 🟡/🔴/🕰️ skill, read the vault's `profile/gap-coaching.md` and score *calibration* against its **Honest floor**. The right answer to "do you have X?" for a real gap is honest + bridge + willingness, never bluffing. Use that entry's "what to say" / "what not to say" in your coaching.
5. **Legacy experience (🕰️).** Real, but deliberately kept off the resume. In a model answer, don't surface it silently — say it exists and ask the user whether they want to raise it in this interview.
6. **Cert and counts.** Don't state cert status or course totals from memory or from this file; take them from the profile (Copy Fragments) if relevant at all.
7. **Do not write to `star-bank.md`.** Practice sessions are rehearsal; `interview_prep --update-star-bank` is the only supported writer.

---

## 6. Feedback format (after every answered question)

Keep it tight — about 120–180 words so the session keeps moving.

```
**Q{n}/{total} · {ID} [{level}] — {score}/5 {band emoji}** {tag if hinted/skipped}

✅ Worked: {1–2 specific things, quoting the user's own words where useful}
⚠️ Missing / wrong: {1–3 specific points; correct any factual error plainly}
🎯 Stronger answer: {3–6 line model answer or outline in the user's voice, grounded per §5; for gap topics use the honest-floor framing}
🔁 Retry? {offer a one-sentence retry only if score < 3.5}
```

Then ask the next question. After a `retry`, score the new attempt and record both (e.g. `2.8 → 4.1`).

---

## 7. Session wrap-up (always, even if the user stops early)

1. **Scorecard:** a table of each question: ID, topic, score, band.
2. **Topic averages** (group by section / JD skill). Skip topics with one question unless it scored < 2.5.
3. **Top 3 strengths** and **top 3 fixes** — concrete ("lead with the result", "N+1: say AsNoTracking + projection"), not generic.
4. **Study list:** question IDs scoring < 3.5, with the bank section to re-read.
5. **Overclaim / honesty flags** raised during the session, if any.
6. **Next step:** retry the weak IDs, or a deeper drill on the lowest topic. For job-specific sessions also offer the hand-offs listed in that skill.

### Session log (persisted progress)

Offer to append the session to `outputs/interview-practice/sessions.md` (the `outputs/` folder is gitignored — create the directory if missing). Do this only after the user agrees, or when they've asked for tracking. Format:

```
## {YYYY-MM-DD} — {Generic .NET practice | Company — Role} · {mode/level} · {n} questions · avg {x.x}
- {ID} {score} {topic}  (… one line per question)
Weak: {IDs < 3.5}   Strong: {IDs ≥ 4.5}
Notes: {1–2 lines}
```

At the start of a later session, if this file exists, read it and use it to **prioritise weak IDs and untouched topics**; mention what you're doing ("Last session your EF Core answers averaged 2.9, so I'm weighting those"). The log holds scores and question IDs only — never the user's full answer text or any personal characteristics.
