"""What a command returns, and the one place an expected failure becomes a result (ADR 0028).

A command returns a ``CommandResult``. The command line, the MCP server and the web UI render it;
none of them reads printed text. The result has no field for finished text: a command's product is
its typed ``data``, and a renderer turns that into text, so two interfaces cannot say different
things.

- ``ok`` is exit status 0, ``error`` is 1 and ``refused`` is 2. A refusal is a gate saying no, and
  carries ``override``, the confirmation that would let it through (``None`` when nothing can).
- ``written`` lists every file the run created or changed, so an adapter attaches exactly those and
  never matches text in the output.
- ``guarded`` is the single boundary: it runs a command and turns the failures a user can cause
  into ``error`` or ``refused`` results. Anything else is a bug and propagates.

This module sits beside ``bootstrap`` in the layers, so the commands, the presence generators, the
gate and the interfaces can all use it. It imports no command, no gate and no interface, which is
why the refusal exception is defined here and the gate's ``GateRefusal`` extends it.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, Literal, TextIO, TypeVar

from jobomatic.documents.service import DocumentError
from jobomatic.learning.service import LearningError
from jobomatic.paths import VaultError
from jobomatic.profile.service import ProfileError
from jobomatic.retrieval.model import RetrievalError

T = TypeVar("T")

Status = Literal["ok", "error", "refused"]
Level = Literal["info", "note", "warning", "error"]

EXIT_CODES: dict[Status, int] = {"ok": 0, "error": 1, "refused": 2}


@dataclass(frozen=True)
class Message:
    """One line about the run. ``info`` is plain, ``note`` is advice to show alongside the
    result, ``warning`` is something the run worked around, ``error`` is why it failed."""

    level: Level
    text: str


@dataclass(frozen=True)
class CommandResult(Generic[T]):
    status: Status
    data: T | None = None  # the command's typed payload
    messages: tuple[Message, ...] = ()
    written: tuple[Path, ...] = ()  # every file this run created or changed
    override: str | None = None  # refused only: the confirmation that clears it

    def __post_init__(self) -> None:
        if self.status != "ok" and not any(m.level == "error" for m in self.messages):
            raise ValueError(f"a {self.status} result needs an error message saying why")
        if self.override is not None and self.status != "refused":
            raise ValueError("only a refused result can name an override")

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.status]


def ok(
    data: T | None = None, *, messages: tuple[Message, ...] = (), written: tuple[Path, ...] = ()
) -> CommandResult[T]:
    return CommandResult("ok", data, messages, written)


def failure(
    text: str, *, data: T | None = None, messages: tuple[Message, ...] = ()
) -> CommandResult[T]:
    """The command could not do what was asked (a missing file, a bad profile, bad input).

    ``data`` is whatever it had produced before it failed, which a renderer still shows first.
    """
    return CommandResult("error", data, (*messages, Message("error", text)))


def refusal(reason: str, *, override: str | None = None) -> CommandResult[Any]:
    """A gate said no. ``override`` names the confirmation that would let it through."""
    return CommandResult("refused", messages=(Message("error", reason),), override=override)


def override_hint(override: str) -> str:
    """The sentence that tells a caller how to confirm past a refusal, for either interface."""
    flag = "--" + override.replace("_", "-")
    return (
        f"Only if the user says so, run again with {override} "
        f"(command line: {flag}; tool: {override}=true)."
    )


class Refusal(Exception):
    """A gate said no. ``override`` names the confirmation that would let it through, if any.

    ``str()`` is the reason plus the hint on how to confirm, which is what a caller that has no
    structured result (a plain ``except``) shows the user.
    """

    def __init__(self, reason: str, override: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.override = override

    def __str__(self) -> str:
        if self.override is None:
            return self.reason
        return f"{self.reason}\n{override_hint(self.override)}"


# The failures a user can cause: a missing or unusable profile or vault, a document that cannot be
# built, bad input, a file that cannot be read or written. The commands raise these on purpose.
# ``Refusal`` is handled first because it means something different.
_EXPECTED = (
    ProfileError,
    VaultError,
    DocumentError,
    LearningError,
    RetrievalError,
    ValueError,
    OSError,
)


def guarded(command: Callable[[], CommandResult[T]]) -> CommandResult[T]:
    """Run ``command`` and return its result, turning an expected failure into one.

    A ``Refusal`` becomes ``refused`` (with its override) and any exception in ``_EXPECTED``
    becomes ``error``. Any other exception is a bug and is not caught.
    """
    try:
        return command()
    except Refusal as exc:
        return refusal(exc.reason, override=exc.override)
    except _EXPECTED as exc:
        return failure(str(exc))


@dataclass(frozen=True)
class Console:
    """What the command line prints for a result: the text for stdout and the text for stderr."""

    stdout: str
    stderr: str


def console(result: CommandResult[Any], render: Callable[[Any], str] | None = None) -> Console:
    """The text of a result, the way the command line has always printed it.

    - the payload, rendered by ``render`` (a renderer per payload type, next to the payload), goes
      to stdout;
    - an ``info`` message goes to stdout as it is, a ``note`` after ``Note: ``, a ``warning`` to
      stderr after ``WARNING: ``, and an ``error`` to stderr after ``ERROR: `` (``REFUSED: `` for a
      refusal, followed by how to confirm past it when something can);
    - each file the run wrote is listed last as ``Wrote <path>``.

    The command line prints this, and the MCP server returns it, so the two cannot differ.
    """
    out: list[str] = []
    err: list[str] = []
    if render is not None and result.data is not None:
        out.append(render(result.data))
    last_error = max((i for i, m in enumerate(result.messages) if m.level == "error"), default=None)
    for index, message in enumerate(result.messages):
        if message.level == "info":
            out.append(message.text)
        elif message.level == "note":
            out.append(f"Note: {message.text}")
        elif message.level == "warning":
            err.append(f"WARNING: {message.text}")
        else:
            label = "REFUSED" if result.status == "refused" else "ERROR"
            line = f"{label}: {message.text}"
            if index == last_error and result.override is not None:
                line += f"\n{override_hint(result.override)}"
            err.append(line)
    out.extend(f"Wrote {path}" for path in result.written)
    return Console("".join(f"{line}\n" for line in out), "".join(f"{line}\n" for line in err))


def emit(
    result: CommandResult[Any],
    render: Callable[[Any], str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Print ``result`` (see ``console``) and return the exit status: 0, 1 or 2."""
    text = console(result, render)
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    out.write(text.stdout)
    err.write(text.stderr)
    return result.exit_code
