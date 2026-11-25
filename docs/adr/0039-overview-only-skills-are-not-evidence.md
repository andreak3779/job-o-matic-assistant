# 0039 — A skill seen only from above is not evidence

**Status:** Accepted. Built.

## Context

Any mention of a skill in the profile's keywords counted as coursework (🟡). An introductory
platform overview therefore met a posting that asked for extensive experience in that language, and
a note in the keyword saying it was not a claimable skill had no effect: the engine matches words,
it does not read them. A posting built on that stack rated Good.

## Decision

1. A gap may be recorded with `evidence: overview`:

   ```yaml
   - skill: Scala / Groovy
     severity: genuine
     evidence: overview
   ```

2. Skills named that way (split on `/`, aliases included) get **nothing from coursework**: not from
   the skill groups, not from the ATS keywords, not from the gap list. With no other evidence the
   row is 🔴, shown as "overview only, not counted".
3. Real work still counts. Production bullets, a portfolio project, a resolved framing gap and
   legacy roles are read as before.
4. A choice stays a choice: "Scala or Python" is still met by Python.
5. Only a genuine gap can carry it; `severity: resolved` with `evidence: overview` is rejected
   ([0007](0007-fail-loud-on-malformed-input.md)).
6. The owner decides which skills carry it. Nothing infers it from wording such as "introductory".

## Consequences

- The rating can only stay the same or fall, and only for postings naming a marked skill.
- Related skills are marked by naming them together; marking Scala does not mark Groovy by itself.
- A vault using the new value cannot be loaded by an earlier version of the tool.
- How long or deep a posting asks the experience to be ("extensive") is still not weighed for
  other coursework.
