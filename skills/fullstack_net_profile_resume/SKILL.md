---
name: fullstack-net-profile-resume
description: >
  Generates a platform-ready resume and cover letter template for the candidate's
  Full-Stack .NET Developer identity — optimized for upload to Canadian Job
  Bank, Indeed, LinkedIn, and similar job boards. No specific job description required.
  Use whenever the user says "create a profile resume", "update my job board resume",
  "upload to Indeed / LinkedIn / Job Bank", "generic resume", "baseline resume",
  "platform resume", "master resume for job boards", or "create a resume I can
  upload to job sites." Also trigger when the user asks to "refresh my resume"
  without supplying a JD, or says "I want a resume ready to post." Always use this
  skill — do NOT generate ad hoc. Output: two DOCX files (resume + cover letter
  template) ready to upload or customize per-application.
---

# Full-Stack .NET Developer — Profile Resume & Cover Letter

Generates a canonical, ATS-safe resume and a customizable cover letter template
rooted in the candidate's core identity: **C#, ASP.NET Core Web API, Entity Framework
Core, Angular (v12–21), TypeScript, MS SQL Server.**

> **Content format:** `python -m jobomatic render schema resume` and `render schema cover-letter`.
> **Profile** (run before Step 1): `python -m jobomatic
> profile show full` —
> employment history, cert status, differentiators, portfolio projects, and
> ATS keyword bank.
> **Layout** (only if debugging spacing): `docx-layout.md`
> Do NOT load the learning data wholesale — use the profile output for ATS keywords if needed.
> Any `{fragment_name}` placeholder below (e.g. `{github_copilot_course_count}`) must be
> filled from the profile's **Copy Fragments** section before writing final
> content — never leave a literal `{fragment_name}` in generated output. If that section
> is missing (older profile data, pre-fragments), compute the value directly from
> the profile's Cert Registry / Key Differentiators sections instead.

---

## Inputs

No job description required. Load automatically via `python -m jobomatic
profile show full` — source
of truth for employment history, dates, metrics, cert status, differentiators,
resolved/genuine gaps, portfolio evidence, and ATS keyword bank.

---

## Step 1 — Establish the Identity Anchor

This resume leads with the **Full-Stack .NET Developer** identity.
Every content decision (summary wording, skills ordering, bullet selection) must
reinforce this anchor.

Core stack to foreground in every section:

| Layer | Technologies |
|---|---|
| Language / Runtime | C#, .NET / .NET Core |
| API / Backend | ASP.NET Core Web API, REST, Entity Framework Core |
| Frontend | Angular (v12–21), TypeScript, RxJS |
| Data | MS SQL Server, T-SQL, SSIS |
| Cloud | Microsoft Azure ({cert_status_short}) |
| DevOps / Tooling | GitHub Copilot Enterprise, Azure DevOps, Docker, GitHub Actions |

---

## Step 2 — Build Resume Content

### 2a — Summary (2 sentences max)

Pattern: `[Years] of experience building [identity] · [top differentiator] · [cert / cloud signal]`

Draft:
> "Full-Stack .NET Developer with 10+ years delivering enterprise-grade
> applications using C#, ASP.NET Core Web API, Entity Framework Core, and Angular.
> Azure-certified (AZ-900) with a track record of legacy modernization, 7× SSIS
> performance improvement, and deep GitHub Copilot enterprise experience."

Never assume a specific cert's status. Read the profile output's Cert Registry
fresh each generation and phrase the cert line to match exactly what's certified vs.
in-progress right now — a cert that was active last time this skill ran (e.g. AZ-204)
may since have been retired or replaced (e.g. by AI-200), and a stated status that no
longer matches the profile is a bug, not a stale-but-harmless detail.

### 2b — Skills Section

**Ordering rule:** Core .NET stack first, then frontend, then data, then cloud/DevOps.
Do NOT alphabetize. Do NOT use tables in the DOCX output (ATS unsafe).

Suggested groupings (use labels exactly as written — these match ATS scanners):

```
Languages & Frameworks   C#, .NET / .NET Core, ASP.NET Core Web API, Entity Framework Core
Frontend                 Angular (v12–21), TypeScript, RxJS, HTML5, CSS3
Databases                MS SQL Server, T-SQL, SSIS, Entity Framework Core Migrations
Cloud & DevOps           Microsoft Azure (AZ-900), Azure DevOps, Docker, GitHub Actions, GitLab CI/CD
Testing                  xUnit, NUnit, Moq, integration testing
Tools & Practices        GitHub Copilot Enterprise, Visual Studio, VS Code, Git, Agile/Scrum
```

Prune any grouping with fewer than 2 entries. Do NOT add skills not present in
the profile output.

### 2c — Experience Bullets

Selection criteria for a platform resume (no JD to match):

- **Lead with impact** — metrics, scale, modernization outcomes preferred over task descriptions
- **Always include** the 7× SSIS performance story (Example Pharmacy)
- **Always include** at least one Angular modernization bullet per employer where it applies
- **Always include** at least one ASP.NET Core Web API bullet per employer where it applies
- **Cap at 4–5 bullets per role** — platform resume must stay ≤ 2 pages
- Legacy roles (including the earliest employer) are not on the resume and get no bullets — the profile's one-line `raw_sections["Additional Experience"]` summary is the only place they appear (no dates, no bullets)
- Use the differentiators list from the profile output to select bullets — resolved
  framing gaps that appear there should be surfaced as production evidence

**Bullet format:** `– [Action verb] [technology] to [outcome/scale]`
No Unicode beyond `–` prefix. No color. No bold inside bullets.

### 2d — Certifications

Use cert status **exactly** as recorded in the profile output's Cert Registry —
never a table memorized from a prior run. For each cert entry there:

- `status: certified` → `[Full cert name] ([CODE]) — Certified [Month Year]` (date from the entry)
- `status: in_progress` → `[Full cert name] ([CODE]) — In Progress`
- `status: not_pursuing` (or any retired/inactive status) → **omit entirely** — do not display it, even if it was shown in a previous version of this resume

Do NOT display a cert not in the profile output. Do NOT display "exam prep complete"
as a certification line — certifications must have a credential ID.

---

## Step 3 — Build Cover Letter Template

This is a **customizable template** — not tailored to a specific company.
Use `[Company Name]` and `[Role Title]` as literal placeholders so the candidate
can swap them per application without regenerating.

### Content budget (enforce before writing):

| Section | Limit |
|---|---|
| Hook | 2 sentences |
| WHAT I BRING bullets | 4–5 items; each ≤ 120 chars body text |
| TWO HIGHLIGHTS | 1–2 lines each |
| Closing | 2 sentences |

### Hook

Lead with the strongest universal differentiator, NOT "I am writing to apply…"

Draft:
> "With 10+ years building full-stack enterprise applications in C#, ASP.NET Core,
> and Angular, I bring deep production experience across the entire delivery
> lifecycle — from REST API design and EF Core data modeling to Angular migrations
> and CI/CD pipelines."

### WHAT I BRING (4–5 bullets — pick from this list, ordered by impact)

1. **Full-stack .NET delivery** — C#, ASP.NET Core Web API, EF Core, Angular (v12–21), TypeScript in production
2. **Legacy modernization** — Led VB.NET → C#/.NET Core migrations at three consecutive employers
3. **Performance engineering** — Redesigned SSIS ETL pipeline, delivering 7× throughput improvement
4. **Azure cloud** — {cert_status_short}; hands-on Azure DevOps, Docker, GitHub Actions
5. **GitHub Copilot Enterprise** — {github_copilot_course_count} enterprise Copilot courses; led AI-assisted development adoption

Select 4 bullets for the template. Keep item 1 always. Rotate items 2–5 based on
role type if the user later tailors this letter.

### TWO HIGHLIGHTS (use most recent / most impactful employers)

- **Acme Software** — Delivered full-stack .NET features and led SSIS performance work
- **Globex Industrial** — Angular and ASP.NET Core modernization across enterprise product lines

Pull exact employer names and date ranges from the profile output.

### Closing (2 sentences)

> "I'm actively seeking remote .NET Developer and cloud-focused roles across
> Canada where I can contribute deep full-stack expertise from day one.
> I would welcome the opportunity to speak with [Company Name] about how my
> background aligns with [Role Title] — please feel free to reach out at your
> convenience."

---

## Step 4 — Generate DOCX

The platform resume and the reusable cover-letter template come straight from the profile; no posting is involved and nothing is logged:

```bash
python -m jobomatic generate-profile-resume
python -m jobomatic generate-profile-cover-letter
```

They write `resume.docx` and `cover-letter.docx` to the vault's `outputs/templates/`. The resume leads with the profile's headline and keeps the profile's own order of skills and bullets. The cover letter's hook is the first sentence of the summary, WHAT I BRING comes from the differentiators, the highlights are the most recent employers, and `[Company Name]` and `[Role Title]` stay as literal text for the candidate to swap per application.

To hand-write the content instead (a different hook, other bullets), write it as JSON per `render schema resume` / `render schema cover-letter` and run `python -m jobomatic render resume <file> --out <outputs/templates/resume.docx>` (likewise `cover-letter`). Keep `[Company Name]` and `[Role Title]` literal in the letter.

**ATS rules (mandatory for job board upload compatibility):**
- No tables · no columns · no text boxes · no graphics
- Standard section headings: `Summary`, `Skills`, `Experience`, `Certifications`
- Resume ≤ 2 pages · cover letter = 1 page
- Paper size: US Letter

---

## Step 5 — Validate and Present

No automated DOCX validator is available locally (the sandbox's `/mnt/skills/public/docx/scripts/office/validate.py` doesn't exist in Claude Code). Open both `outputs/{Name}_Resume_SeniorFullStackNET.docx` and `outputs/{Name}_CoverLetter_Template.docx` and visually confirm formatting before delivering them.

Fix any errors before presenting.

**Output filenames:**
- `resume.docx`
- `cover-letter.docx`

Save both in `outputs/templates/` and tell the user their paths.

**Inline summary after presenting:**
- ATS keywords foregrounded
- Cert status applied
- Differentiators surfaced
- Placeholder fields in cover letter (list them so the candidate knows what to swap)
- Page count of each document

---

## Platform Upload Notes

When uploading to job boards:

| Platform | Resume | Cover Letter |
|---|---|---|
| Canadian Job Bank | Upload DOCX directly | Paste plain text or upload separately |
| Indeed | Upload DOCX (parsed automatically) | Paste text in application form |
| LinkedIn | Upload DOCX to "Featured" or "Easy Apply" | Paste text or attach |
| Company portals | Upload DOCX (most accept it) | Attach as second DOCX |

**Tip:** If a platform asks for plain text, open the DOCX and paste — Arial
and standard headings survive copy-paste well. Avoid saving as PDF for upload
unless the platform explicitly requires PDF; DOCX parses more reliably.

## Writing style

Before drafting any prose, follow `reference/writing-style.md`: plain, professional-but-casual, no AI filler. Treat `WARNING: AI-sounding wording` output from the generator as something to fix.
