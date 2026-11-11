# 0028 — Commands return structured results that the CLI and the MCP server render

**Status:** Proposed. A problem statement only; no decision yet, details to be added.

## Context

[ADR 0002](0002-mcp-thin-adapter-over-cli.md) made the MCP server a thin adapter over the command
line, and [ADR 0016](0016-modular-monolith-ports-and-adapters.md) describes the code as ports and
adapters. In practice the adapter is coupled to the CLI's printed text:

- `interfaces/mcp/server.py` runs the CLI in-process under a global lock with `redirect_stdout`,
  then finds the files a command wrote with a regular expression over `Wrote <path>` lines
  (`_WROTE_RE`).
- `interfaces/cli/main.py` rebuilds an argv list and calls each command's own `main(argv)`, so every
  command parses arguments twice.
- Success and failure reach the MCP side as an exit code plus captured text.

A change to a printed message can break an MCP tool without a type error or a failing import
contract.

## Options to weigh

- Commands return a small result object (status, text, written files); the CLI prints it and the
  MCP server reads it, with no output capture.
- Keep the adapter but give `Wrote` lines a documented, tested format.
- Leave it, and record the coupling as accepted.

## To decide

Which commands change first, and whether the lock and `redirect_stdout` can then go.
