# Command snapshots

What each command prints (`cli/`) and what each MCP tool returns (`mcp/`), for the fictional demo
person, recorded by `tests/test_command_snapshots.py`. They exist so that the commands can change
how they produce their results (ADR 0028) without the output changing by accident.

Paths, today's date and the time stamps in the attached `.meta.json` files are replaced with
placeholders such as `<TMP>`, `<TODAY>` and `<NOW>`, so the files do not change from run to run.

When a change to the output is deliberate, record it and read the diff:

```
UPDATE_SNAPSHOTS=1 python -m pytest tests/test_command_snapshots.py
```

These are test fixtures, not examples of good writing. The generated documents themselves are
covered by [`tests/golden/`](../golden/README.md).
