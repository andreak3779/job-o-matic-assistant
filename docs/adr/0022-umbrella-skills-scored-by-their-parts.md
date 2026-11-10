# 0022 — Umbrella skills such as AI are scored by evidence in their parts

**Status:** Accepted. Built for AI. The AI category is a first version and will be revised.

## Context

Some skill words are umbrellas over many specific skills: "AI" covers LLMs, agentic frameworks,
retrieval-augmented generation, vector databases, MCP servers, prompt engineering and the AI
coding assistants. The fit engine finds a skill by matching the word in the profile. For an
umbrella, that is a poor test in both directions:

- Any project that mentions "AI" meets a requirement for "experience with AI", whatever it did.
- A profile with deep LLM, RAG and MCP work but little use of the word "AI" can read as thin.

[0009](0009-skill-terms-from-sentence-bullets.md) already keeps umbrellas from inflating a line
that lists examples ("AI-assisted tools such as Copilot, Claude Code, or Cursor" drops the word
"AI" and scores the examples). It does not change how a requirement that is *only* the umbrella
("Experience with AI") is scored; that still depends on the word.

## Decision

Add a parent-to-parts list next to the alternatives groups in `src/jobomatic/fit/skill_vocabulary.json`:

```json
"umbrellas": { "ai": ["llms", "agentic", "rag", "vector databases", "mcp", "prompt engineering",
                      "github copilot", "claude code", "..."] }
```

A requirement that is an umbrella is scored by the best evidence among its parts, using the
profile's own evidence tiers (paid role, personal project, course). Open questions below set how
the word itself counts.

The parts of each umbrella are the owner's to define, not generated: they decide what "experience
with AI" means for the candidate. The list is validated when the module loads (every part is a
known term, a term has one umbrella, umbrellas may not nest) and fails loudly, as the groups do.

## Resolutions (confirmed by the owner)

- **Does the bare word count?** No. A requirement that is only the umbrella ("Experience with
  AI") is scored by the best evidence among its parts. The fit table names the part that earned
  the status, for example `[via claude code]`. A requirement that names AI and other skills
  ("AI-assisted Azure DevOps") is still scored by the other skills.
- **Cap a part's evidence one tier below?** No. The profile's own tiers (paid role, portfolio,
  course) already say how strong the evidence is.
- **Which umbrellas?** `ai` and `generative ai`, which share one list. Machine learning and deep
  learning are parts of that list. Cloud, testing and security are not umbrellas.
- **The AI parts (the owner's list):** agentic development (`agentic`, `ai agents`,
  `ai coding agents`), RAG and embeddings, the AI harness (`github copilot`, `copilot`,
  `claude code`, `ollama`), LLMs, vector databases (`vector database(s)`, `vector search`,
  `pgvector`), and, added at the owner's request, `mcp`, `prompt engineering`, `langchain`,
  `machine learning` and `deep learning`.
- **Coverage:** unchanged. An umbrella requirement is one row with the best part's status.
- **"Modern AI-assisted automation techniques":** research found three readings (agents that
  decide and run workflows, business process automation with AI, AI-assisted building of flows),
  and the owner confirmed it can mean any of them. It is scored as two requirements: `AI` (by its
  parts) and `workflow automation`. A phrase list in `skill_vocabulary.json` (`phrase_expansions`)
  holds this and its variants ("AI-powered", "AI-driven", "AI-enabled" automation).
- `copilot studio` and `ai builder` are terms and AI parts.
- **Known limit:** a requirement for machine learning itself is still scored by its own word, since
  no parts were listed for it. The AI category will be revised further.

## Consequences

- A standalone "Experience with AI" would be rated from real work, and the answer could be
  explained from the output by naming the part that earned it.
- A new list for the owner to keep, the same accepted burden as `aliases.json` and the groups.
- Some postings' ratings would move. Golden files for both vaults are reviewed in the same change.
