# How this was built

> **Note (November 2026):** I first planned to share this repository as a portfolio piece. I have
> decided to keep it private, because I would rather my other repositories be the public ones. The
> passages below that mention going public or sharing the code describe that earlier plan and are
> left as written.

## The short version

This project grew from resume-editing prompts into an application over about seven months, using
Claude throughout. I wrote none of the code. Claude wrote all of it, first in the web chat and then
as an AI coding agent (Claude Code) in this repository. What I did write is the requirements, the
design decisions, the standing instructions in `CLAUDE.md`, and the skill files. I asked Claude
to add tests for the tool's functionality so the results stay consistent, asked it to revise the
code repeatedly until it followed coding standards, and decided whether each change merged.

In the first versions there was no code to review: the tool was a set of skill files inside Claude,
and I judged it only by reading the documents it produced. That is how wrong claims got through,
and it is the main reason I moved to code that can be tested.

## How it got here

This repository is the fourth version. Each earlier version is still in my GitHub account.

| When | What I built | Who wrote it |
| --- | --- | --- |
| Before April 2026 | Prompts in the Claude web chat to fix grammar and spelling in my resume and cover letters. | Me, with Claude. |
| April 2026 | Reusable Claude skills (written instructions) with my career history stored beside them, which tailored my master resume and cover letter to a job posting (`ai-job-search-workflow`). To make the documents more consistent, I then asked Claude to generate the DOCX and PDF files with Node.js (`docx`) and Python scripts instead of leaving it to the skills. | I wrote the requirements and the skill files. I developed the Node.js and Python templates with Claude through prompt engineering, and Claude wrote the code. I checked the results by reading the documents, not code. |
| June 2026 | A Claude Project under source control, with Pluralsight course import (`job-search-workflow`). | Same as above. |
| July–October 2026 | Python code in a repository: three Claude projects (job applications, profile and learning, online presence), with generated bundles that passed data between them (`claude-projects`). A CLI and an MCP server appeared in August. The first commit made with Claude Code is dated 14 August. | Claude wrote all the code. I asked it to add tests for the tool's functionality to keep results consistent, had it revise the code to follow coding standards, and wrote `CLAUDE.md` and the skill files. |
| September 2026 | A public snapshot of that design with a made-up persona instead of my data (`career-fit-assistant`). | Exported from the private repo. |
| October 2026 onward | This repository: an application with a typed profile and a private vault, using the model as little as possible. | Claude Code under a written plan, as described below. |

### Why I moved from prompts to code

Three problems pushed me.

- **Accuracy.** The tailored resumes and cover letters sometimes described experience and skills I
  do not have. I noticed this in interviews, where I was asked about things the document claimed.
  I wanted every claim in a document to trace back to my real career history, so the facts now
  come from a typed profile and the fit rating is computed in code, not judged by the model.
- **Formatting.** I kept having to correct the layout of resumes and cover letters. Section
  headers were missing, page formatting was wrong, a job entry would split across a page break, and
  the resume ran past two pages. I wanted the same layout every time, so I asked for a template
  system in Python (first Node.js, later `python-docx`) with fixed page limits: a resume of at most
  two pages and a cover letter of exactly one, checked by converting the file to PDF and counting
  pages.
- **Usage limits.** I kept hitting session, daily and weekly limits, which stopped me applying for
  jobs with the tools. Moving the repeatable work into deterministic code means it runs without the
  model.

### Learning alongside the build

For the whole time I was building this, I was also taking Pluralsight and Microsoft Learn courses
on AI-assisted development, prompt engineering, GitHub Copilot and Claude. I applied what I learned
to the tool to make it more accurate, more useful and better at judging fit. The course record is
imported into the project itself (`jobo learning stats` gives the current totals), so these are
dated completions, not recollection. Examples from that record:

- **Prompt engineering:** *Getting Started on Prompt Engineering with Generative AI* (February 2026),
  *Prompt Engineering Best Practices* (April 2026) and *Advanced Prompt Engineering for Claude*
  (August 2026).
- **AI-assisted coding and Copilot:** *Introduction to AI-assisted Coding* and *Advanced AI-assisted
  Development* (March 2026), and *Production-ready AI-assisted Development and Workflows*
  (July 2026).
- **Claude:** *Introduction to Claude Code* and *Claude Code in Practice* (June 2026), *Advanced
  Claude Code* (July 2026), *Building Custom Claude Skills* and *Building with Claude Agent SDK*
  (August 2026), and *Building Applications with Claude* (September 2026).

What I took from them:

- **Prompt engineering** taught me to write clearer prompts, so the model understood what I wanted
  and used fewer tokens. That mattered because I kept hitting usage limits.
- **AI-assisted coding and Copilot** taught me how to build with AI: writing plans and requirements
  documents that direct the model toward the result I want. That is the feature-plan loop described
  under [The process](#the-process).
- **Building Custom Claude Skills** (August 2026) reinforced how a skill should be written and
  structured: clear headings, the actions it is allowed to take, and explicit requirements. I
  applied those lessons to the skills in this repository (`skills/*/SKILL.md`).

## Tools

- **Claude Code** for the agent work, with Claude Sonnet 5, Sonnet 5.5 and Opus 5.5 (the models
  named in the commit trailers).
- **Claude Desktop** as the MCP client the server was built for.
- **Local tools** that check the agent's output: `pytest`, `ruff`, `mypy`, `import-linter`, and a
  git pre-commit hook ([how they constrain the agent](#how-the-checks-constrain-the-agent)).

## The process

1. **Feature plan.** For each feature I wrote a plan describing what I wanted to achieve, the role
   Claude should fill, and the outcome I expected. I reviewed Claude's draft, asked for revisions
   and for anything it had missed, and repeated that loop until I was satisfied the plan would give
   me the outcome I wanted. The agent was asked to ask questions, not to assume.
2. **Items, with tests between them.** I then asked Claude to implement the plan as a series of
   items and to add testing between each one. I also asked it to split the work into items that
   sub-agents could do in parallel, which was not always possible. The plan marks which sessions
   can run at the same time in separate worktrees.
3. **Decision records.** Choices that were not obvious became a short ADR before or while the code
   was written ([docs/adr/](adr/)).
4. **Small changes on a branch.** Each piece was one pull request, squash-merged to `main` only
   after the hook and CI passed.
5. **Tests first or alongside.** New behaviour came with tests; refactors were checked against
   recorded outputs (golden files) so behaviour could not change silently.
6. **Walkthroughs.** The plan gives each larger step a walkthrough: I run the real commands on real
   data and explain how the feature works. I do not claim a feature in public until its walkthrough
   has passed, and some walkthroughs are still to do.
7. **My review.** I read each finished document by hand and checked it against my own knowledge of
   my career and my master resume. I asked for changes, and decided when a step was finished. The
   tool cannot confirm that a sentence is true; that check is mine
   ([what the tool does and does not guarantee](TRUTHFULNESS.md)).

## How the checks constrain the agent

- **The gate and its tests** mean a change that weakens a refusal fails the suite.
- **Import rules** (`lint-imports`) fail a change that breaks the module layering. When new rules
  were added, they were tested by deliberately breaking them once to see them fail.
- **A private-values scan** in the commit hook blocks any tracked file that restates personal data.
- **A hardcoded-facts scan** flags numbers in skills that should be computed from the profile.
- **The agent's instructions** (`CLAUDE.md`) hold standing rules, such as never adding protected
  characteristics to a document and never committing generated files.

## Where the AI was wrong, and how it was caught

The first case was found while preparing this repository to go public. The other three happened in
the prompt-based versions and are the reason I rebuilt the tool.

| What went wrong | How it was caught | What now prevents it |
| --- | --- | --- |
| The personal-terms scanner missed a name that sat right after a written-out `\n` in a string, so a real employer name stayed in a code comment. | Caught before making the repo public. | A test for the case in `tests/test_pii_scan.py`; the name was replaced. |
| In the prompt-based versions, the model rewrote a job description to overstate my experience. I had worked on a migration project as part of a team, and the tailored resume said I led it. | Reading the generated resume against my own career history. | Documents are now built from a validated profile and tiered evidence, not free rewriting ([how](TRUTHFULNESS.md)). I still read every document before sending it. |
| The tool left real experience out of the job-fit assessment. A startup posting asked for rapid prototyping and proofs of concept, which I had done for a previous employer, but the fit result did not credit it. The prompt-based versions also dropped experience that did not match a posting's wording. | Reading the fit result against my own career history. | The fit report lists the required lines it could not score, so they can be checked by hand. "Rapid prototyping" and "proof of concept" are not yet terms in the fit vocabulary, so a posting that asks for them is still read as a soft skill and ignored. This is a known gap that I plan to close. |
| In the prompt-based versions, the documents had missing headers, wrong page formatting, job entries split across pages, and resumes longer than two pages. | Opening each file and looking at it. | Documents are generated from fixed Python templates, and the page limits are checked by converting to PDF and counting pages ([CLAUDE.md](../CLAUDE.md)). |

## How I worked with Claude

I worked with Claude the way two people pair-program. The ideas, the features, the architecture and
the standards the code had to follow came from me; Claude wrote the code and proposed options; and
we went back and forth until the result met what I had asked for. I do not claim the code as mine.
What I can explain and defend is what the tool is for and why it makes the choices below.

- **This is not an auto-apply tool.** I set criteria for how well my career history and learning
  fit a posting, so that I apply only to postings that are a Strong or Good fit and do not spend
  time on poor matches. The gate refuses to generate documents below that bar unless I confirm.
- **The criteria needed correcting.** Research on how job fit is judged showed my criteria were
  too strict: a well-covered posting could be rated Stretch because of a few coursework-level
  skills. I recalibrated them in November 2026 ([ADR 0021](adr/0021-fit-rating-weights-core-requirements.md)
  and the [calibration plan](Fit-Calibration-Plan.md)). The thresholds are starting values until I
  have recorded real outcomes, so I treat them as unproven.

- **The fit rating is computed in code, not by the model** ([ADR 0001](adr/0001-deterministic-fit-engine.md)).
  Deciding whether a posting is worth an application is the first question every document path
  asks. I wanted the same posting to get the same answer every time, and I wanted that answer to
  rest on my real profile, so the rating is counted from evidence and the model does not judge it.
- **Location rules are part of the rating** ([ADR 0008](adr/0008-location-eligibility-in-fit-rating.md)).
  The rating once looked only at skills, so a posting with a strong skills match in a place I
  cannot work still passed the gate and had documents generated for a job I could not take. Those
  postings are now a Pass whatever the skills say.
- **"Applied" is never set automatically** ([ADR 0010](adr/0010-applications-log-event-sourced-explicit-applied.md)).
  Companies re-post the same requisition, and applying again a few days later looks like a
  duplicate. The log has to be right on both of my laptops, so recording an application is always
  an explicit act of mine, and generating documents only records a posting as drafted.
- **Code and personal data live in two repositories** ([ADR 0013](adr/0013-code-and-vault-split-into-two-repos.md)).
  I wanted to share the code as a portfolio piece. Git history cannot be reliably scrubbed
  afterwards, so my career data, salary limits and generated documents stay in a separate private
  repository from the start.
