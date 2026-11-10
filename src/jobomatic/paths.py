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

The older per-file overrides (``CLAUDE_JOBS_PRIVATE_DIR``, ``CLAUDE_JOBS_APPLICATIONS_LOG``)
still win, because tests and the container rely on them.

Some callers take an explicit ``root`` (tests build a temporary tree). A root that is ``None``
or this checkout means "use the vault"; any other root is used as given, in the old project-2
layout.
"""

from __future__ import annotations

import os
import re
import tomllib
from datetime import date
from pathlib import Path

VAULT_ENV = "JOBOMATIC_VAULT"
PRIVATE_DIR_ENV = "CLAUDE_JOBS_PRIVATE_DIR"
APPLICATIONS_LOG_ENV = "CLAUDE_JOBS_APPLICATIONS_LOG"
VAULT_MARKER = ".jobomatic.toml"
SIBLING_VAULT_NAME = "job-o-matic-vault"

# Directory name the old per-project layout used for the profile sources.
_LEGACY_PROFILE_DIR = "project-2-profile-learning-hub"


class VaultError(RuntimeError):
    """No usable vault: none configured, none found next to the checkout, or one is invalid."""


def config_path() -> Path:
    """Location of the optional user config file (override: JOBOMATIC_CONFIG)."""
    override = os.environ.get("JOBOMATIC_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "job-o-matic" / "config.toml"


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


def _is_default_root(root: Path | None) -> bool:
    return root is None or root.resolve() == code_root()


def private_dir() -> Path:
    """Personal constraint files such as salary minimums."""
    override = os.environ.get(PRIVATE_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return vault_root() / "private"


def applications_log() -> Path:
    """The append-only applications log (ADR 0010)."""
    override = os.environ.get(APPLICATIONS_LOG_ENV)
    if override:
        return Path(override).expanduser()
    return vault_root() / "applications" / "applications.jsonl"


def outputs_dir(root: Path | None = None) -> Path:
    """Generated files, one hierarchy (see ``output_dir``)."""
    if _is_default_root(root):
        return vault_root() / "outputs"
    assert root is not None
    return root / "outputs"


def imports_dir() -> Path:
    """Raw provider exports, kept so an import can be replayed: ``imports/<provider>/<date>.<ext>``."""
    return vault_root() / "imports"


def evidence_index_path() -> Path:
    """The evidence-retrieval index (SQLite). Rebuildable, never the source of truth."""
    return vault_root() / "index" / "evidence.sqlite"


def profile_dir(root: Path | None = None) -> Path:
    """Directory holding the profile sources (resume snapshot, profile facts, learning data...).

    It mirrors the old project-2 layout until the profile becomes YAML (Sessions 5 and 5b).
    """
    if _is_default_root(root):
        return vault_root() / "profile"
    assert root is not None
    return root / _LEGACY_PROFILE_DIR


def star_bank_path(root: Path | None = None) -> Path:
    """The STAR story bank that interview prep can write back to."""
    if _is_default_root(root):
        return vault_root() / "profile" / "star-bank.md"
    assert root is not None
    return root / "project-1-application-engine" / "reference" / "star-bank.md"


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
    root: Path | None = None,
) -> Path:
    """Where generated files of ``kind`` go. Builds the path only; the caller creates it.

    ``application``, ``part-time`` and ``outreach`` give one folder per job or person, named
    from ``day`` and ``company`` (plus ``role`` for an application). Pass ``name`` instead to
    reuse an existing folder name, such as an application's id. ``profiles`` needs
    ``platform``. The others are fixed folders.
    """
    if kind not in OUTPUT_KINDS:
        raise ValueError(f"unknown output kind {kind!r}; expected one of {list(OUTPUT_KINDS)}")
    base = outputs_dir(root)
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
