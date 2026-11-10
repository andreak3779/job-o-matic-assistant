---
name: azure_focused_net_developer
description: >
  Specialized job search and career skill for an Azure-focused .NET developer
  actively seeking work. Use whenever the user is applying for, researching, or
  preparing for roles involving ASP.NET Core, C#, Azure, or cloud-native .NET
  development. Trigger for job postings mentioning .NET, C#, ASP.NET Core, Azure
  Functions, EF Core, REST APIs, microservices, or Azure cloud services. Also
  trigger when the user asks about AI-200 certification prep, .NET interview
  questions, Azure architecture interviews, or wants to position their skills for
  cloud developer roles. Always prefer this skill over the generic job-search
  skill when the role is .NET or Azure-specific.
---

# Azure-Focused .NET Developer — Job Search Skill

> **Profile facts**: this skill only does positioning/fit analysis and hands off actual
> document generation to other skills (see Workflows 2–3), so it never needs the
> ~11.5K-token full `profile show` — just the facts portion (ATS keywords, cert
> status, differentiators, portfolio projects, AI-200 domain coverage, Copy Fragments).
> Run `python -m jobomatic profile show facts`
> before any positioning, gap, or AI-200 work. Do NOT load the learning data wholesale —
> course-level detail is not needed here.
> **Interview prep**: `interview-prep.md` — load when preparing for a specific interview stage.
> Any `{fragment_name}` placeholder below must be filled from the facts output above's
> **Copy Fragments** section before presenting output — never leave a literal
> `{fragment_name}` in delivered text.

## Core Stack (quick reference)

| Layer | Technologies |
|-------|-------------|
| Cloud | Azure (see the facts output above for cert status) · Functions · Serverless · Security |
| Backend | ASP.NET Core · C# · .NET 10 · EF Core · REST APIs · Microservices · DDD |
| Frontend | Angular · React · Bootstrap 5 |
| DevOps | Docker · Kubernetes · GitHub Actions · CI/CD |
| AI | GitHub Copilot ({github_copilot_course_count} courses) · Prompt Engineering · AI Agents |
| Scripting | Python 3 · Linux / Unix / Bash · Shell scripting · PowerShell · AWK |
| Portfolio | ai-job-search-workflow (Python + AI automation) · Resume_Site (GitHub Actions end-to-end) |

---

## Workflow 1 — Job Posting Analysis
Parse exact versions/services → match against stack above → flag gaps and check portfolio evidence from the facts output → identify differentiators → rate fit: **Strong / Good / Stretch / Pass** + one-line rationale.

**Fit gate:** Strong/Good → proceed to cover letter/resume or learning plan. Worth a try/Stretch/Pass → recommend learning plan or better-matched roles (do NOT generate application documents). A **location Pass** (Quebec, hybrid/on-site outside the home city, Atlantic-only remote, or French required — see `job-description-fit` for the full rules) is never a learning-plan case: skills aren't the blocker, so recommend only better-located roles.

For full structured output → use the **gap-analysis-job-description** skill.

## Workflow 2 — Resume Tailoring
Extract ATS keywords → map to experience + Pluralsight credentials + portfolio projects → edits by section:
- **Summary**: lead with Azure + .NET; include cert status from the facts output.
- **Skills**: list Azure services explicitly, not just "cloud."
- **Experience**: measurable impact; inject missing keywords naturally.
- **Certs**: Pluralsight path completions as evidence.
- **Portfolio**: where relevant, reference GitHub projects as applied evidence (e.g. Resume_Site for CI/CD end-to-end, ai-job-search-workflow for Python/AI tooling).

For DOCX output → use the **create-a-cover-letter-and-tailored-resume-for-job-description** skill.

## Workflow 3 — Cover Letter
→ Use the **create-a-cover-letter-and-tailored-resume-for-job-description** skill.

## Workflow 4 — Interview Preparation
Load `interview-prep.md` → tailor to specific role and stage.

## Workflow 5 — AI-200 Cert Prep
Map domain coverage (from the facts output's AI-200 Domain Coverage table) → identify gaps → suggest courses or MS Learn modules → generate practice scenario questions for weak areas.

**Domains**: Azure AI Services (OpenAI, Computer Vision, Document Intelligence) · Vector databases and RAG · Azure AI Search · Prompt engineering and agentic patterns · Responsible AI.

See the facts output for exam deadlines.

## Workflow 6 — Home-City / Remote Positioning
On-site/hybrid in the home city, or remote open to home-province residents. Only the time zones the location preferences allow are workable — Quebec, Atlantic-only remote, and hybrid/on-site outside the home city are a Pass (enforced by `fit-check`). For "Canada-wide" remote postings that also list Quebec/Atlantic provinces, confirm the home province eligibility and hours with the recruiter. Flag US-only postings (visa required). No timezone friction for Central-time roles. Job boards: LinkedIn · Indeed Canada · Workopolis · Government of Canada Job Bank.
