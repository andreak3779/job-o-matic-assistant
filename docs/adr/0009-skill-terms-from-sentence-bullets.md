# 0009 — Sentence-style JD bullets are scored by extracting skill terms

**Status:** Accepted

## Context

The fit engine (ADR [0001](0001-deterministic-fit-engine.md)) classifies each
required skill by matching it against the profile, and was built for short
bullets ("C#", "SQL Server / T-SQL query optimization"). Many real postings
write requirements as sentences under headings like "Required Qualifications".
Two failures followed:

1. The parser didn't recognise those headings, so a detailed posting parsed to
   *no* required skills (`Pass — No required skills provided`).
2. Once the headings were recognised, each whole sentence was matched as one
   phrase, never hit the profile, and read as a genuine gap — a posting that
   matched well rated `Pass` on "11 genuine gaps", which is worse than an empty
   table because it looks plausible.

## Decision

- `src/jobomatic/fit/parser.py` recognises "Required/Minimum/Basic/Key Qualifications",
  "Qualifications", "You have…", "Who you are", and hyphenated "Nice-to-Have";
  tests nice-to-have headings first so "Preferred Qualifications" isn't read as
  required; and closes a section at "Responsibilities", "Salary", "Pay range"
  and similar.
- A bullet of more than 6 words (parenthetical detail excluded — "Strong Azure
  fundamentals (App Service, Functions)" stays a short skill) is treated as a
  sentence. `src/jobomatic/fit/terms.py` extracts the technology terms in
  `src/jobomatic/fit/skill_vocabulary.json` from it, in the posting's own spelling, and
  those become the scored skills. Short bullets keep the original
  split-on-and/or/slash behaviour unchanged.
- "…, or comparable/similar/equivalent/other" collapses the preceding list
  into one `A / B / C` alternatives entry, scored by its best evidence.
- A required sentence with no recognised term is **not scored and not dropped**:
  it lands in `ParsedJD.unscored_required` → `FitResult.unscored_required`, and
  `fit-check` / `gap-analysis` list it under "Required lines not scored — read
  these yourself". It never changes the rating.

## Consequences

- The vocabulary is JD-side only and has to be maintained, the same accepted
  burden as `aliases.json`: a technology missing from it is listed as unscored
  rather than scored. That under-counts requirements, so a high rating on a
  posting with several unscored lines deserves a manual read.
- Whether the candidate *has* a skill is still decided by `fit_engine` against the
  profile bundle; the vocabulary only decides what counts as a skill in a JD.
  When a real posting surfaces a synonym the profile covers (e.g. "secure
  development" ↔ "secure coding"), the fix is an `aliases.json` entry.
- Bare "or" in a sentence is still conservative — each term is required
  separately — matching the original short-bullet behaviour. Only the explicit
  "or comparable…" phrase makes alternatives.
- Compound short bullets such as "CI/CD with GitHub Actions" still split on `/`
  (a known quirk of the short path); sentence bullets keep `CI/CD` whole.

## Update (fit calibration, ADR 0021)

Examples after "such as", "e.g.", "for example", "including" or "like" are now one alternatives
entry too, whether the list ends in "and" or "or": "AI-assisted tools such as GitHub Copilot,
Claude Code, or Cursor" is one requirement met by any one tool, not four. The list stops at a
sentence break or at an "and" that starts a new requirement ("... and experience with Docker").
A bare "or" outside an examples list is unchanged: each term is still required separately.

Two or more terms from one **alternatives group** (`alternative_groups` in
`src/jobomatic/fit/skill_vocabulary.json`: ORMs, cloud platforms, front-end frameworks, server-side
languages, relational and NoSQL databases, message brokers, test frameworks, CI/CD platforms,
infrastructure-as-code tools, monitoring tools, AI coding assistants) joined by "/" or "or" are
also one entry: "Entity Framework/ Dapper" and "AWS or Azure" are choices, not two requirements.
"And", a plain comma list, and terms from different groups ("C#/.NET") stay separate, and groups
hold only true substitutes (no "JavaScript"/"TypeScript" or "HTML"/"CSS"). A group may name only
known terms and a term may sit in one group; the file is validated at import and fails loudly.

A few vocabulary words are also ordinary English (`caps_only` in the vocabulary file; today only
"solid"). They count as a skill only in capitals: "SOLID principles" is scored, "Solid understanding
of CI/CD" is not. A rule cannot know which meaning a posting intends, so each such word found in
any other form is listed under **Terms to confirm** (`ParsedJD.terms_to_confirm` ->
`FitResult.terms_to_confirm`, shown by `fit-check` and `gap-analysis`) with its line, once per
posting. It never changes the rating, and the skills tell Claude to ask the user which meaning the
line has rather than decide.

When the examples follow a **category term** ("NoSQL databases such as MongoDB", "message queues
such as SQS, RabbitMQ, or Kafka"), the category and its examples are one entry, `NoSQL / MongoDB`, met by evidence
for the category or for any example: the category is the requirement and the examples only
illustrate it. Only terms in `category_terms` (kinds of tool such as AI, NoSQL, messaging and
testing) join; a product does not ("Python libraries such as Pandas" is not met by Python alone),
and the label must sit within four words of the marker with no comma or "and" between.

**Umbrella terms** (`umbrella_terms`: AI, generative AI, machine learning, deep learning) are too
broad to join: any project that mentions AI would meet "AI-assisted development tools such as
Cursor or Windsurf". When examples follow one, the umbrella is dropped and the examples carry the
requirement (`GitHub Copilot / Claude Code / Cursor`). A requirement that is only the umbrella is
scored as usual. Scoring an umbrella by evidence in its parts is proposed in
[0022](0022-umbrella-skills-scored-by-their-parts.md).

**Considered and not adopted:** treating any list whose last connector is "or" as alternatives
("LLMs, agentic frameworks, RAG, vector databases, or MCP servers" as one entry). Those are
separate terms of different kinds, not substitutes, so they stay separate rows; only same-kind
tools (the alternatives groups) and examples of a category collapse. A bare "or" between terms of
different kinds is still scored as separate requirements.

A word that is one letter from a long skill name and that the vocabulary does not know ("Typscript"
for "typescript") is listed under **Possible typos**, with its line, and not scored: the tool never
corrects a posting for the user. Both the word and the term must be at least eight letters, because
shorter words sit one letter from too many ordinary ones ("sprint" and "Spring", "signal" and
"SignalR"). Measured on about 127,000 words of ordinary technical writing the flag fired on none, at
the cost of missing typos in short skill names such as "Angular". Plurals, singulars and version
numbers ("containers", "Python3") are known forms and never flagged.


**A list of skills in a sentence is one row per skill (2026-11-08).** "Experience with Azure and
REST APIs" is rated as two requirements, not as one sentence scored by its best-evidenced phrase,
which let evidence for Azure cover a missing REST API. The rule (`conjoined_terms` in
`src/jobomatic/fit/terms.py`) is deliberately narrow: two or more known terms, joined only by a comma
or "and", with nothing but filler words before the first or after the last. It leaves a sentence whole
when it holds a parenthesis ("Accessibility (WCAG)" is one requirement explained), a word between
terms ("Monitoring and observability with Azure Monitor"), a choice or examples ("or", "such as"), or
a meaningful extra word ("Azure fundamentals"). "CI/CD" is one practice and is never split at its
slash. Measured on the three real-vault golden postings, this changed the rows of the cloud and
CI/CD lines only and no rating.

Interview-prep and thank-you story selection compared skill text to story text as a bare substring,
so the old split-off row "ci" matched almost any story ("specific"). Matching now treats `-`, `/` and
spaces alike and also tries the skills named inside a row (`commands/support.py::story_mentions`).
