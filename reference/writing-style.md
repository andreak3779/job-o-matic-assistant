# Writing Style for Recruiter-Facing Documents

Loaded by every skill that produces text a hiring manager or recruiter will read: cover letters, resumes, cold outreach, thank-you letters, job-board letters. Goal: sounds like the candidate wrote it. Professional, relaxed, plain.

## Rules

- Write in first person, short sentences, contractions are fine ("I'm", "I'd").
- Lead with something specific (a skill, project, or employer), never with enthusiasm.
- One concrete fact beats an adjective. Say what was built, with what, and the result.
- Vary sentence length. Don't open every paragraph or bullet the same way.
- Max one em dash per paragraph; prefer a period or comma.
- No markdown (`**`) in DOCX output.
- Ask for the call plainly ("Do you have 15 minutes this week?").
- Only claim what the profile supports; keep the course/portfolio/production distinction.

## Avoid

excited to / thrilled / eager to / passionate about · I am writing to · I would welcome the opportunity · don't hesitate to · proven track record · results-driven · detail-oriented · team player · dynamic · leverage · spearhead · utilize · seamless · robust · cutting-edge · holistic · synergy · "scale that impact" · "exactly where my background fits"

`src/jobomatic/documents/humanize.py` (`find_ai_tells`) lints for these; `add_paragraph` prints a stderr warning when a paragraph contains one. Fix the copy, don't ignore the warning.
