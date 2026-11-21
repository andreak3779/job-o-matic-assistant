# 0035 — Claude Desktop writes tailored documents through render tools, not the rule-based generators

**Status:** Accepted. Built in the same change.

## Context

A tailored resume and cover letter reach a person in two ways:

- **The rule-based generators** (`generate-resume`, `generate-cover-letter`, and the MCP tools
  `generate_resume`, `generate_cover_letter`, `generate_application_documents`). Code picks the
  tagline, hook, bring-items and bullets by simple rules. The skill calls them "not full parity"
  with its own judgment and uses them only as an optional audit (Step 5.5).
- **The skill's own path** (Step 5). The model reads the posting, writes the content as JSON and
  `jobomatic render` lays it out. This is what Claude Code does.

Claude Desktop only had the first. The skill prompt told it that `render` has no tool, so a
person using the Desktop prompt got the rule-based output: a tagline that pasted raw posting
fragments ("professional C# · NET development experience"), a hook that claimed a core gap
("asks for professional C#, which is a big part of what I do"), and bring-items that repeated one
project. The model, seeing a weaker document than it could write, rebuilt the files itself. A
comparison on 2026-11-20 showed the MCP and command-line generators were byte-identical, and the
Desktop-side file was a different, model-written document with no gate, no sidecar and no entry
in the application folder.

The MCP and command line did not differ. Desktop lacked the second path.

A second problem sat under the first. Writing tailored content needs the candidate's real
employers, dates, bullets and contact details. In Claude Desktop `profile show full` maps to
`profile_summary`, which returns the public facts only, and the resume bullets are `local_only`
(ADRs 0019, 0020). The model had no grounded source except the attached file of an earlier
`generate_*` call.

## Decision

1. **A `render` command in `src/jobomatic/commands/render.py`** returns structured results
   (ADR 0028) and is the one implementation behind the command line and the MCP server. It has
   `schema`, `draft` and `run`, for the two kinds that belong to a posting: `resume` and
   `cover-letter`. The part-time kinds stay command-line only.
2. **Four MCP tools:** `render_schema(kind)`, `render_draft(kind, jd, ...)`,
   `render_resume(content, jd, ...)` and `render_cover_letter(content, jd, ...)`. `content` is an
   object or JSON text.
3. **`render` is gated like the generators** (fit, duplicate application, pay; ADR 0003), inside
   the command, before anything is written, with the same three confirmations. This also closes a
   gap: the command line's `render resume --jd` did not gate before. It does now. A run with
   `--out` and no posting is not gated and logs nothing, as before.
4. **`render_draft` is the grounded starting point.** It returns the content the rule-based
   generator would render, as JSON that follows the schema, and writes and logs nothing. The tool
   description and the prompt preamble tell the model every claim must trace to that draft. It is
   gated too, because it hands out the career material for that posting.
5. **Filing, sidecar and log are as for the generators.** With a posting the document goes into
   that posting's application folder, a draft is logged (never "applied"), and a
   `.meta.json` sidecar (script `render.py`) records the profile hash and fit rating. The MCP
   result carries the file and the "give it to the user" note, as the generators' do.
6. **The Desktop prompt says so.** `skill_prompts.py` maps `render schema|draft|resume|cover-letter`
   to the tools, and its preamble tells the model to write the content, render it, and not call a
   `generate_*` tool for the same posting afterwards, because those write the same file names and
   would replace the rendered documents.
7. **The generators stay.** They remain the quick rule-based version, and `render draft` starts
   from them, so the two paths share one set of facts. A test renders the draft unchanged and
   checks the text equals `generate-resume`'s.

## Consequences

- Desktop and Claude Code follow the same skill steps. What differs is only where the facts come
  from: `render draft` in Desktop, `profile show full` in Claude Code.
- **No new exposure to the Desktop model.** `generate_resume` already returns the whole resume as
  an attachment, so the model already saw those bullets. `render_draft` gives them as text,
  behind the same gate. Nothing marked private or `local_only` is added.
- The model writes the words, so the grounding rule is prompt-level, as it is in Claude Code. The
  code checks only the shape (the schema), the limits (a summary of at most 2 lines, 1 to 5
  bring-items) and the gate. It does not check that a claim is true. `--check-pages` still
  measures the real page count on the command line; the MCP tools do not run LibreOffice.
- `render resume --jd` and `render cover-letter --jd` can now refuse (exit 2). The skill says to
  pass `--confirm-gaps` only after the user says yes to a Stretch or Worth a try rating.
- `render` errors now go to stderr with an `ERROR:` prefix for the tailored kinds (they were
  stdout lines starting `[ERROR]`). The part-time kinds are unchanged.

## Addendum: every resume and cover letter can be skimmed in 15 seconds

Decided 2026-11-20, the day the two paths' output was compared side by side. Hiring research puts
a recruiter's first scan of a resume at about 6 to 15 seconds (TheLadders eye-tracking, 2012 and
2018; InterviewPal, 2025) and most readers' time on a cover letter at under a minute (Resume
Genius, Jobera). The sources are career-service companies and self-reported, so the figure is a
guide, not a measurement. The rule is that a reader who sees only the headline, summary, skill
labels, role lines and the letter's hook, bold labels and ask knows whether the candidate fits.

- **The limits are code** (`documents/budget.py`, checked by `documents/skim.py`): a 14-word
  one-line headline, a 60-word summary, 7 skill lines of 28 words, 4 bullets of 35 words per role,
  a letter hook of 2 sentences and 40 words, 4 bring-items (label under 40 characters, body under
  20 words), highlights of 30 words, a closing of 2 sentences and 35 words, and 200 words for the
  letter. The schema quotes the same numbers, so a model reads them in the field descriptions.
- **`render` refuses content over the limits**, naming every field, before anything is written. The
  tailored kinds only; the part-time documents have no budget.
- **The generators meet it by cutting at a sentence or clause, never mid-thought** (`skim.shorten`),
  and never by rewriting a fact. The summary keeps the sentences that speak to the posting. The
  headline is the profile's own role and up to three posting skills the profile backs, so it no
  longer carries the posting's phrases or a title that overstates the role. The letter hook names a
  skill with production evidence, and bring-items that rest on the same project become one line.
- **Not changed:** the limit on *how many* roles a resume shows stays with the page-fit trim. A
  profile bullet whose first clause is not a complete thought can still read abruptly after a cut.

The branch-per-ADR habit would make this its own ADR. It is an addendum because it changes the
checks the render path makes, which this ADR introduced, and the two ship together.
