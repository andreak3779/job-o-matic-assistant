"""Print a command's result the way the command line always has (ADR 0028).

``emit`` is the one place the command line turns a ``CommandResult`` into text and an exit status:

- the payload is rendered by the function the caller passes (a renderer per payload type lives
  beside it, shared with the MCP server), and goes to stdout;
- ``info`` messages go to stdout as they are, ``note`` to stdout after ``Note: ``, ``warning`` to
  stderr after ``WARNING: ``, and ``error`` to stderr after ``ERROR: `` (``REFUSED: `` for a
  refusal, followed by how to confirm past it when something can);
- each file the run wrote is listed as ``Wrote <path>``, last, in order;
- the return value is the exit status: 0, 1 or 2.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any, TextIO

from jobomatic.results import CommandResult, override_hint


def emit(
    result: CommandResult[Any],
    render: Callable[[Any], str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr

    if render is not None and result.data is not None:
        print(render(result.data), file=out)

    last_error = max((i for i, m in enumerate(result.messages) if m.level == "error"), default=None)
    for index, message in enumerate(result.messages):
        if message.level == "info":
            print(message.text, file=out)
        elif message.level == "note":
            print(f"Note: {message.text}", file=out)
        elif message.level == "warning":
            print(f"WARNING: {message.text}", file=err)
        else:
            label = "REFUSED" if result.status == "refused" else "ERROR"
            line = f"{label}: {message.text}"
            if index == last_error and result.override is not None:
                line += f"\n{override_hint(result.override)}"
            print(line, file=err)

    for path in result.written:
        print(f"Wrote {path}", file=out)
    return result.exit_code
