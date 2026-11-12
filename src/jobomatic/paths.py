"""The one place that knows where personal data lives (ADR 0013).

Everything outside this module asks it for a path instead of building one from
``__file__``. The data lives in a *vault*: a separate directory marked with
``.jobomatic.toml``. The vault is found, in order, from

1. ``$JOBOMATIC_VAULT``,
2. ``vault = "..."`` in ``~/.config/job-o-matic/config.toml`` (override the file with
   ``$JOBOMATIC_CONFIG``),
3. a sibling directory called ``job-o-matic-vault`` next to this checkout.

If none of them yields a directory holding the marker, every path lookup raises
``VaultError`` (ADR 0007): there is no silent fallback to files inside this repo.

The per-file overrides (``JOBOMATIC_PRIVATE_DIR``, ``JOBOMATIC_APPLICATIONS_LOG``) move one
folder or file and still win, because the test fixture and ``scripts/golden_outputs.py`` rely on
them. They are not a second layout. There is no other way to locate data (ADR 0029): tests select a throwaway
vault with ``JOBOMATIC_VAULT``.
"""

from __future__ import annotations

import os
import re
import tomllib
from datetime import date
from pathlib import Path

VAULT_ENV = "JOBOMATIC_VAULT"
PRIVATE_DIR_ENV = "JOBOMATIC_PRIVATE_DIR"
APPLICATIONS_LOG_ENV = "JOBOMATIC_APPLICATIONS_LOG"
ALLOWED_DIRS_ENV = "JOBOMATIC_ALLOWED_DIRS"
VAULT_MARKER = ".jobomatic.toml"
SIBLING_VAULT_NAME = "job-o-matic-vault"


class VaultError(RuntimeError):
    """No usable vault: none configured, none found next to the checkout, or one is invalid."""


# The variables' earlier names (ADR 0030). They are not read. Setting one is an error, because
# ignoring it would quietly send data somewhere the user did not point it. Delete this map and
# ``reject_retired_variables`` before 1.0.
RETIRED_VARIABLES = {
    "CLAUDE_JOBS_PRIVATE_DIR": PRIVATE_DIR_ENV,
    "CLAUDE_JOBS_APPLICATIONS_LOG": APPLICATIONS_LOG_ENV,
    "CLAUDE_JOBS_ALLOWED_DIRS": ALLOWED_DIRS_ENV,
}


def reject_retired_variables() -> None:
    """Raise ``VaultError`` if a variable that was renamed is still set to something (ADR 0030)."""
    for old, new in RETIRED_VARIABLES.items():
        if os.environ.get(old):
            raise VaultError(f"{old} is no longer read; it is now called {new}. Rename it.")


def config_path() -> Path:
    """Location of the optional user config file (override: JOBOMATIC_CONFIG)."""
    override = os.environ.get("JOBOMATIC_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "job-o-matic" / "config.toml"


def not_found_message(path: Path, label: str = "File") -> str:
    """The error for a file that is not there, in words that let a new user fix it.

    A relative path starts from the current folder (ADR 0027), which is the usual reason a file
    that exists is "not found", so the message names the full path it looked for and that folder.
    """
    short = f"{label} not found: {path}"
    if path.is_absolute():
        return f"{short}. Check the spelling of the path."
    try:
        here = Path.cwd()
    except OSError:  # the current folder was deleted; there is nothing more to say about it
        return short
    return (
        f"{short}\n"
        f"  Looked for: {os.path.normpath(here / path)}\n"
        f"  Current folder: {here}\n"
        "  A relative path starts from the current folder: run the command from the folder "
        "that holds the file, or give the full path."
    )


def code_root() -> Path:
    """Root of this checkout. For code and bundled assets, never for personal data."""
    return Path(__file__).resolve().parents[2]


def _configured_vault() -> tuple[Path, str] | None:
    env = os.environ.get(VAULT_ENV)
    if env:
        return Path(env).expanduser(), f"${VAULT_ENV}"
    cfg = config_path()
    if cfg.is_file():
        try:
            data = tomllib.loads(cfg.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise VaultError(f"{cfg} is not valid TOML: {exc}") from exc
        vault = data.get("vault")
        if vault:
            return Path(str(vault)).expanduser(), str(cfg)
    sibling = code_root().parent / SIBLING_VAULT_NAME
    if (sibling / VAULT_MARKER).is_file():
        return sibling, "the sibling directory"
    return None


def vault_root() -> Path:
    """The vault directory. Raises ``VaultError`` if there isn't a valid one."""
    found = _configured_vault()
    if found is None:
        raise VaultError(
            f'No vault found. Set ${VAULT_ENV}, add `vault = "/path"` to {config_path()}, '
            f"or keep a directory named {SIBLING_VAULT_NAME} (containing {VAULT_MARKER}) "
            f"next to {code_root()}."
        )
    path, source = found
    if not (path / VAULT_MARKER).is_file():
        raise VaultError(
            f"{source} points at {path}, which has no {VAULT_MARKER}; "
            "refusing to treat it as a vault."
        )
    return path.resolve()


def private_dir() -> Path:
    """Personal constraint files such as salary minimums."""
    reject_retired_variables()
    override = os.environ.get(PRIVATE_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return vault_root() / "private"


def applications_log() -> Path:
    """The append-only applications log (ADR 0010)."""
    reject_retired_variables()
    override = os.environ.get(APPLICATIONS_LOG_ENV)
    if override:
        return Path(override).expanduser()
    return vault_root() / "applications" / "applications.jsonl"


def outputs_dir() -> Path:
    """Generated files, one hierarchy (see ``output_dir``)."""
    return vault_root() / "outputs"


def imports_dir() -> Path:
    """Raw provider exports, kept so an import can be replayed: ``imports/<provider>/<date>.<ext>``."""
    return vault_root() / "imports"


def evidence_index_path() -> Path:
    """The evidence-retrieval index (SQLite). Rebuildable, never the source of truth."""
    return vault_root() / "index" / "evidence.sqlite"


def profile_dir() -> Path:
    """Directory holding the profile sources (the typed YAML profile, learning data...)."""
    return vault_root() / "profile"


def gap_coaching_path() -> Path:
    """Per-skill gap coaching notes used by interview prep."""
    return vault_root() / "profile" / "gap-coaching.md"


def learning_plans_dir() -> Path:
    """Generated learning-plan PDFs."""
    return output_dir("learning-plans")


def part_time_data_dir() -> Path:
    """Baseline resume and transferable-skills notes for the part-time workflow."""
    return vault_root() / "profile" / "part-time"


# -- generated files: one hierarchy (ADR 0015) --------------------------------------------------
#
#   outputs/applications/<date>_<company>_<role>/   one folder per application
#   outputs/part-time/<date>_<employer>/            same pattern, non-developer jobs
#   outputs/outreach/<date>_<recruiter>/            cold letters, no posting involved
#   outputs/profiles/<platform>/<date>.md           LinkedIn, GitHub, ...
#   outputs/learning-plans/  outputs/research/  outputs/templates/
#
# This is the only place that builds one of those paths. A generator never makes its own.

OUTPUT_KINDS = (
    "application",
    "part-time",
    "outreach",
    "profiles",
    "learning-plans",
    "research",
    "templates",
)
_FOLDER_KINDS = {"application": "applications", "part-time": "part-time", "outreach": "outreach"}
_FIXED_KINDS = {
    "learning-plans": "learning-plans",
    "research": "research",
    "templates": "templates",
}
_MAX_SLUG = 40
_SLUG_RUNS = re.compile(r"[^a-z0-9]+")
_DATED_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}_")


def slug(text: str) -> str:
    """Lowercase words joined by hyphens, at most 40 characters; ``unknown`` if nothing is left."""
    cleaned = _SLUG_RUNS.sub("-", text.lower()).strip("-")[:_MAX_SLUG].strip("-")
    return cleaned or "unknown"


def folder_name(day: date | str, *parts: str | None) -> str:
    """``2026-10-31_acme-health_net-developer``: the date, then a slug per non-empty part."""
    stamp = day if isinstance(day, str) else day.isoformat()
    return "_".join([stamp, *(slug(p) for p in parts if p and p.strip())])


def is_dated_name(name: str) -> bool:
    """True for a name built by ``folder_name`` (as opposed to a legacy random id)."""
    return bool(_DATED_NAME.match(name))


def output_dir(
    kind: str,
    *,
    day: date | str | None = None,
    company: str | None = None,
    role: str | None = None,
    platform: str | None = None,
    name: str | None = None,
) -> Path:
    """Where generated files of ``kind`` go. Builds the path only; the caller creates it.

    ``application``, ``part-time`` and ``outreach`` give one folder per job or person, named
    from ``day`` and ``company`` (plus ``role`` for an application). Pass ``name`` instead to
    reuse an existing folder name, such as an application's id. ``profiles`` needs
    ``platform``. The others are fixed folders.
    """
    if kind not in OUTPUT_KINDS:
        raise ValueError(f"unknown output kind {kind!r}; expected one of {list(OUTPUT_KINDS)}")
    base = outputs_dir()
    if kind in _FIXED_KINDS:
        return base / _FIXED_KINDS[kind]
    if kind == "profiles":
        if not platform:
            raise ValueError("output kind 'profiles' needs a platform")
        return base / "profiles" / slug(platform)
    if name is None:
        if day is None or not company:
            raise ValueError(f"output kind {kind!r} needs a day and a company (or a name)")
        name = folder_name(day, company, role if kind == "application" else None)
    return base / _FOLDER_KINDS[kind] / name
