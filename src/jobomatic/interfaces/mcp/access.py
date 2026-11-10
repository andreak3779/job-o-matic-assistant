"""Which files the MCP server may read and write: the privacy boundary for Claude Desktop.

THIS MODULE IS WRITTEN BY THE AUTHOR, not generated. Claude Code reviews it.
The rules it replaces are ``_read_roots``, ``_write_roots``, ``_denied_paths`` and
``_resolve_within`` in ``src/jobomatic/interfaces/mcp/server.py`` (``git show main:src/jobomatic/interfaces/mcp/server.py``). Write it
from the spec below, then compare.

Every path a client hands the server is untrusted: a prompt-injected job posting can steer a tool
call at any file the server process can reach. These two functions decide what is allowed.
They are pure: no environment, no ``jobomatic.paths``, no network. The server builds a
``Locations`` from ``jobomatic.paths`` and passes it in, so the rules can be tested on their own.

Spec
----
``resolve(value, roots, denied)``
    Return the fully resolved path if ``value`` is allowed, otherwise ``None``.

    * ``value`` may be a ``str`` or a ``Path``. Expand ``~`` and resolve the path, following
      symlinks and ``..``, *before* checking anything, so a trick path cannot slip out of a root.
      The path need not exist yet (a file about to be written).
    * ``~nosuchuser/x`` cannot be expanded (``RuntimeError``): that is ``None``, not a crash.
    * Any path with a ``.git`` component is denied, wherever it is.
    * Anything inside (or equal to) a ``denied`` path is denied, even if it is also inside a root.
    * Otherwise it is allowed only if it is inside (or equal to) one of ``roots``.
    * ``roots`` and ``denied`` are resolved before they are compared too (a root that is a symlink
      must still match), and a sibling whose name merely starts the same
      (``outputs-evil`` next to ``outputs``) is not inside ``outputs``.

``build_policy(locations)``
    Decide the three lists from where things are. Entries that are ``None`` (no vault found) are
    simply left out. In plain terms:

    * Readable: the vault (everything in it that is not denied), the temp directory and the
      extra directories. The code repository itself is NOT readable: a job description or an
      output never lives there, so there is no reason to let a client see it.
    * Writable: the vault ``outputs`` folder, the learning-plans folder, the one file
      ``stories_file`` (interview prep updates it) but NOT the rest of the profile, the temp
      directory and the extra directories.
    * Denied (read and write): the ``private`` folder (salary minimums), the applications log
      (edited only through the applications tools), ``.git`` in the vault, and ``.git`` and
      ``private`` in the code repository.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Locations:
    """Where things are, as the server found them. Anything missing is ``None``."""

    code_root: Path
    temp: Path
    extra: tuple[Path, ...] = ()
    vault: Path | None = None
    outputs: Path | None = None
    learning_plans: Path | None = None
    stories_file: Path | None = None
    private: Path | None = None
    applications_log: Path | None = None


@dataclass(frozen=True)
class Policy:
    """What a client may read, what it may write, and what it may never touch.

    ``read_roots`` and ``write_roots`` are the directories (and the one file) that are
    reachable for the matching kind of access; ``denied`` holds paths that are off
    limits even when they sit inside one of those roots.
    """

    read_roots: tuple[Path, ...]
    write_roots: tuple[Path, ...]
    denied: tuple[Path, ...]

    def roots(self, *, write: bool) -> tuple[Path, ...]:
        """The roots that apply to the requested kind of access."""
        return self.write_roots if write else self.read_roots


def _resolve(path: str | Path) -> Path | None:
    """``path`` with symlinks and ``..`` followed, or ``None`` if it cannot be resolved."""
    try:
        return Path(path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def _present(*candidates: Path | None) -> tuple[Path, ...]:
    """Drop the candidates that are missing and keep the rest as a tuple."""
    return tuple(path for path in candidates if path is not None)


def resolve(value: str | Path, roots: Sequence[Path], denied: Sequence[Path]) -> Path | None:
    """Return the fully resolved path if ``value`` is allowed, otherwise ``None``.

    ``value`` is untrusted, so it is resolved before anything is compared: neither a
    ``..`` nor a symlink can lead out of a root. The path need not exist yet (a file
    about to be written).
    """
    try:
        candidate = Path(value).expanduser()
    except RuntimeError:  # "~unknownuser/x" has no home directory to expand to
        return None

    if ".git" in candidate.parts:
        return None

    resolved = _resolve(candidate)
    if resolved is None or ".git" in resolved.parts:
        return None

    # Denied wins over a root that contains it, so it is checked first.
    for denied_path in denied:
        target = _resolve(denied_path)
        if target is not None and resolved.is_relative_to(target):
            return None

    for root in roots:
        allowed = _resolve(root)
        if allowed is not None and resolved.is_relative_to(allowed):
            return resolved

    return None


def build_policy(locations: Locations) -> Policy:
    """What a client may read, what it may write, and what it may never touch."""
    vault = locations.vault

    read_roots = _present(locations.vault, locations.temp, *locations.extra)
    write_roots = _present(
        locations.outputs,
        locations.learning_plans,
        locations.stories_file,
        locations.temp,
        *locations.extra,
    )
    denied = _present(
        locations.private,
        locations.applications_log,
        vault / ".git" if vault is not None else None,
        locations.code_root / ".git",
        locations.code_root / "private",
    )
    return Policy(read_roots, write_roots, denied)
