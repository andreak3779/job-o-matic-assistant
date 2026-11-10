# Skills

One folder per workflow, each with a `SKILL.md` that Claude follows. The skills hold the
conversation: what to ask, in what order, and which command to run. The commands hold the logic
(`python -m jobomatic ...`, or `jobo ...` when the virtualenv is on your PATH). A skill never
re-derives a career fact; it reads the profile.

```text
skills/       one folder per skill (SKILL.md, and sometimes small helper files)
reference/    material a skill step loads mid-workflow (rubrics, question bank, writing style)
templates/    layout notes and example inputs (docx layout, role-config example, import page)
.claude/skills/<name>  symlinks to skills/<name>, so Claude Code finds them
```

Personal data (the profile, the STAR story bank, gap-coaching notes, role configs, generated
documents) lives in the private vault, never here. See `docs/architecture.md`.

## The skills

### Applying to a job

| Skill | Use it to |
|---|---|
| `job_description_fit` | Quick fit rating and skills table for a posting |
| `gap_analysis_job_description` | Full gap analysis against a posting |
| `create_a_cover_letter_and_tailored_resume_for_job_description` | Tailored DOCX cover letter and resume (duplicate check, then fit gate) |
| `fullstack_net_profile_resume` | Platform resume and cover-letter template for job-board uploads |
| `profile_resume_pdf` | The same platform resume as a PDF |
| `cold_outreach_recruiter_letter` | Cold-outreach letter to a recruiter or agency, not tied to a posting |
| `azure_focused_net_developer` | Search guidance for .NET and Azure roles |
| `job_search` | Fallback for salary, tracking, company research, offers |
| `job_search_router` | Routes a request to the right command |
| `employment_research` | Screens a list of postings for Strong or Good fits |
| `job_fit_advisor` | Which job types and titles to target |
| `salary_research` | CAD salary and contract-rate research |

The generator for part-time documents (`render part-time-resume`, `render part-time-cover-letter`) is
in the code. The skill that drives it is personal, so it lives in the private vault.

### Interviews

| Skill | Use it to |
|---|---|
| `interview_prep` | Role-specific interview prep DOCX |
| `interview_practice` | Live mock interview, no posting |
| `interview_practice_job_description` | Live mock interview built from a posting |
| `post_interview_thank_you_letter` | Thank-you letter within 24 hours |

### Learning and profile data

| Skill | Use it to |
|---|---|
| `pluralsight_updater` | Import newly completed Pluralsight courses and labs |
| `pluralsight_summary_enricher` | Add short summaries to imported items (runs after the updater) |
| `ms_learn_updater` | Import Microsoft Learn completions (only when asked) |
| `learning_plan_gap_analysis` | Learning-plan PDF from a gap analysis |
| `cert_learning_plan` | Phased learning-plan PDF for a Microsoft certification |
| `primary_learning_plan_generator` | Merge several gap analyses into one master plan |

### Online presence

| Skill | Use it to |
|---|---|
| `update_linkedin_profile` | LinkedIn fields |
| `update_github_profile` | GitHub bio, status, profile README |
| `update_job_board_profiles` | Indeed and ZipRecruiter fields, plus resume-freshness check |
| `update_jobgether_profile` | Jobgether fields (written without a live account to check; read its warning first) |
| `update_pluralsight_profile` | Pluralsight bio, title, links |

The last three presence skills are not symlinked into `.claude/skills`. The old repository did not
link them either, so Claude Code does not offer them on its own; add a symlink to opt one in.

## Reference and templates

`reference/` is loaded by named steps, so each file says which skill step uses it:
`coverage-rubric.md` (learning plans), `interview-prep.md`, `interview-question-bank.md`,
`interview-practice-rubric.md`, `recruiter-briefing-template.md`, `writing-style.md`,
`JobSearch_KeywordStrategy.md`. The STAR story bank and gap-coaching notes are in the vault's
`profile/` folder, because they are personal.

`templates/` holds `docx-layout.md` (the layout reference; the renderers are in
`src/jobomatic/documents/`), `roles/_example.json` (the schema for a learning-plan role config),
`Resume_Snapshot.example.md` (a fictional resume snapshot) and `pluralsight_import_template.html`.

## Adding or changing a skill

- A new skill is a folder `skills/<name>/SKILL.md` with `name` and `description` front matter, plus
  a symlink `.claude/skills/<name>` -> `../../skills/<name>`.
- Run `python scripts/check_skill_hardcoding.py` after editing any `SKILL.md`. It flags cert
  statuses and course counts written as literal prose that no longer match the profile.
- When you add a reference file, say in it which skill and step loads it.
