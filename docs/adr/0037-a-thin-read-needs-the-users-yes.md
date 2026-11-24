# 0037 — A Strong or Good rating that rests on a thin read needs the user's yes

**Status:** Accepted. Built.

## Context

The fit rating is computed from the skills the parser could read. Real postings are often written
in prose, or as one generic list, and the parser then reads very few skills from many lines. The
low-confidence notice ([0021](0021-fit-rating-weights-core-requirements.md)) says so, but it did
not change anything: a posting read as a single satisfied skill could rate Good or Strong, and the
documents were then generated on the strength of it. Several real postings did exactly that (a
role that needed mobile development read Good because only "full-stack" was recognised).

The owner's rule: a rating that rests on very little must have their explicit yes first.

## Decision

1. In the fit gate (`jobomatic.gate.check_fit`), a **Strong or Good** rating whose result carries a
   low-confidence notice is **refused** until the user confirms. It is the same confirmation as for
   Worth a try and Stretch (`confirm_gaps`, `--confirm-gaps`), because the user's decision is the
   same: go ahead although the rating is not to be taken at face value. The refusal says why and
   tells the caller to ask the user to read the posting first.
2. When confirmed, the result carries a note saying the documents were generated on a thin read,
   at the user's request.
3. A location disqualifier is unchanged and cannot be confirmed past. A skills Pass is unchanged.
4. The rating itself is not changed; only whether documents may be written.

## Consequences

- Fewer documents are written for postings the tool half-read. The cost is one extra question for
  a thin posting that is in fact a good match.
- No new flag or MCP parameter: the existing confirmation covers it, so the CLI, the MCP tools and
  the web page all enforce it without further plumbing. The web page's sentence beside the box now
  names both cases.
- The notice's thresholds remain judgment calls, pinned by tests.
