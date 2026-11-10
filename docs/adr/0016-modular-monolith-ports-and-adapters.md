# 0016 — Modular monolith built as ports and adapters

**Status:** Accepted

## Context

The code is one Python application of roughly 7,000 lines with one user on
one machine. Business rules (fit rating, location and salary rules) are
already pure and deterministic, but file access, SQLite, Ollama, DOCX
rendering and the MCP/CLI entry points are mixed in with them in places.
The rearchitecture needs several swaps to be routine: real vault versus
demo vault, Ollama versus no embedder, live pages versus saved ones.

Considered and rejected:

- **Microservices / a message bus.** One user, one machine; they would add
  network failure modes and nothing else.
- **Plain layered architecture.** Close, but the business layer tends to
  end up depending on file and database details.
- **Full Clean Architecture by the book.** The same idea with more layers
  than about 7,000 lines justify.

## Decision

A **modular monolith**: one deployable app, split into modules by
capability (`profile`, `learning`, `fit`, `retrieval`, `documents`,
`presence`, `applications`, and the `interfaces` for CLI and MCP).
Each module follows **ports and adapters**:

- `model.py`: domain types and pure rules, with no input/output.
- `ports.py`: small interfaces (Python `Protocol`s).
- `service.py`: the use cases, depending only on ports.
- `adapters/`: concrete files, SQLite, Ollama, DOCX, HTTP and so on.

Rules, enforced in CI by `import-linter`:

1. Domain code imports nothing from adapters or interfaces.
2. Use cases depend on ports, never on a concrete adapter.
3. Modules call each other only through another module's `service.py`.
4. The CLI and MCP server are thin driving adapters. Policy, such as "no
   documents below a Good fit" (ADR
   [0003](0003-fit-gate-enforced-at-mcp-boundary.md)), lives in the use
   case so both interfaces get it.
5. One `bootstrap.py` wires adapters to ports.

## Consequences

- Builds on ADR [0002](0002-mcp-thin-adapter-over-cli.md) rather than
  replacing it. The fit gate moves out of the MCP layer into the document
  use cases.
- Tests use in-memory or demo-vault adapters and never need personal data.
- Some indirection that a script of this size could do without; accepted
  for the testability and the swaps above.
- Introduced module by module: `profile` first, the rest when the package
  is reorganised.
