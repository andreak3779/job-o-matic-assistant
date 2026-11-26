# 0038 — A "some of" list is one requirement, and what a posting especially wants is required

**Status:** Accepted. Built.

## Context

A posting listed fourteen tools after "experience with some of what we work with day-to-day". The
parser made a required row of each tool it knew and silently dropped the six it did not, so two
missing tools made the posting a Pass. Wording the same list as "any of" merged it into one row
that a single tool satisfied, which rated far too high.

The same posting called .NET and C# "a strong asset" below, while its duties said there was a
growing amount of .NET work and that people with .NET experience were especially wanted.

## Decision

1. A list introduced by "some of", "some or all of", "a few of", "several of" or "the skill set
   (or skills) may include", then a colon, dash or bracket, with at least three short names of
   which two are known skills, is **one requirement**. After a colon the names may also stand on the bullets or indented lines
   underneath; a sentence there gives the skills it names, and one naming none stays a line of its
   own. One lead-in line ("Expertise in the following tools:") may sit between them. The owner's
   scoring:
   - ✅ two or more of the names have production evidence;
   - 🟡 any other current evidence (including exactly one name in production);
   - 🕰️ legacy evidence only;
   - 🔴 none.
2. Every listed name is shown with its own status, known to the vocabulary or not. A name without
   evidence is never a gap of its own.
3. The row's skill names only the listed names that share the evidence shown, so a document claims
   nothing the evidence does not cover. A row can therefore be `match` for documents and 🟡 for
   the rating (`SkillMatch.rated_as`).
4. A name in the list is not counted again as a nice-to-have, and the list counts as the number
   of names it holds when deciding whether a posting was read thinly
   ([0037](0037-a-thin-read-needs-the-users-yes.md)).
5. An optional line becomes **required** when it names a skill from a sentence saying the posting
   especially (or particularly) wants to hear from people who have it. "A strong asset" on its own
   stays optional.
6. "Any of" lists are unchanged: one name satisfies them
   ([0021](0021-fit-rating-weights-core-requirements.md)). "One or more of", "at least one of" and
   "one of the following" now count the same way.

## Consequences

- A broad stack list no longer sinks a posting, and cannot carry it on one tool either. It weighs
  as one requirement however long it is, so a posting that is mostly one such list rates on few
  rows.
- Under a heading-style introduction every following bullet belongs to the list until the next
  line that is neither a bullet nor indented, so a separate requirement written straight after it
  is absorbed.
- A "one of" introduction with its names on the lines underneath is not covered, nor is "some of"
  without a colon, dash or bracket.
- Rule 5 matches one narrow way of stressing a skill. Other kinds of emphasis are left to the
  reader.

## Addendum: a stack to know part of, and copies that lost their layout (2026-11-24)

- A paragraph that says what the stack spans and then that not all of it is needed (or to be deep
  in several of these) is a "some of" list. Names written as a pair ("TypeScript/Node.js") count
  as two.
- In a copy with no bullets or indents anywhere, a line of four words or more that names a skill
  is a list item. A line stating that a skill is an asset is an item, never a heading.
- A list that wraps after a comma, or names written one per line under the introduction at its own
  indent, stay one list.
- "●", "○" and similar marks are bullets.

## Addendum: "some combination of" (2026-11-26)

- "Some combination of", "some mix of" and "some subset of" introduce a list too, with or without
  a colon.
- A line under the introduction that calls a skill an asset stays optional, and a remark about
  what is not required ("knowing every one isn't required") is read on its own line.
  Neither joins the list.
- A sentence under the introduction gives the skills it names in brackets as well.
