"""Write a profile-update draft and its provenance sidecar, for any presence generator (ADR 0028).

The five generators (LinkedIn, GitHub, Jobgether, Indeed and ZipRecruiter, Pluralsight) read the
public view of the profile and the skill's own ``SKILL.md``, build a draft, and write it to the
vault's ``outputs/profiles/<platform>/``. They differ only in the builder, the names, and what
evidence they cite, so the flow lives here once and each generator passes its parts.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from jobomatic import bootstrap, paths
from jobomatic.profile.model import PresenceView
from jobomatic.provenance import write_sidecar
from jobomatic.results import CommandResult, Message, failure, guarded, ok


@dataclass(frozen=True)
class DraftData:
    """The draft that was written, and the warnings it carries (they are also in its sidecar)."""

    platform: str
    draft: Path
    warnings: tuple[str, ...]


def write_draft(
    *,
    platform: str,
    script: str,
    skill_path: Path,
    build: Callable[[PresenceView, str], tuple[str, list[str]]],
    out: Path | None = None,
    evidence_sources: Callable[[PresenceView], list[str]] | None = None,
    raw_inputs: Callable[[PresenceView], dict[str, Any]] | None = None,
) -> CommandResult[DraftData]:
    """Build the draft for ``platform`` and write it, with its sidecar.

    ``out`` defaults to the vault's ``outputs/profiles/<platform>/<today>.md``. ``raw_inputs``,
    when given, is written next to the draft as ``<name>.raw-inputs.json`` first; failing to write
    it is a warning, not a failure.
    """
    return guarded(
        lambda: _write_draft(platform, script, skill_path, build, out, evidence_sources, raw_inputs)
    )


def _write_draft(
    platform: str,
    script: str,
    skill_path: Path,
    build: Callable[[PresenceView, str], tuple[str, list[str]]],
    out: Path | None,
    evidence_sources: Callable[[PresenceView], list[str]] | None,
    raw_inputs: Callable[[PresenceView], dict[str, Any]] | None,
) -> CommandResult[DraftData]:
    if not skill_path.is_file():
        return failure(f"SKILL.md not found: {skill_path}")
    view = bootstrap.load_presence_view()
    content, warnings = build(view, skill_path.read_text(encoding="utf-8"))

    out_file = (
        out or paths.output_dir("profiles", platform=platform) / f"{date.today().isoformat()}.md"
    )
    try:
        out_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return failure(f"cannot create output directory {out_file.parent}: {exc}")
    try:
        out_file.write_text(content, encoding="utf-8")
    except OSError as exc:
        return failure(f"cannot write output file {out_file}: {exc}")

    written: list[Path] = []
    messages: list[Message] = []
    if raw_inputs is not None:
        raw_file = out_file.with_name(out_file.stem + ".raw-inputs.json")
        try:
            raw_file.write_text(json.dumps(raw_inputs(view), indent=2) + "\n", encoding="utf-8")
            written.append(raw_file)
        except OSError as exc:
            messages.append(
                Message("warning", f"could not write raw inputs file {raw_file}: {exc}")
            )

    sidecar = write_sidecar(
        out_file,
        script=script,
        profile=view,
        inputs=[],
        evidence_sources=evidence_sources(view) if evidence_sources else [],
        warnings=warnings,
    )
    written += [out_file, sidecar]
    return ok(
        DraftData(platform, out_file, tuple(warnings)),
        messages=tuple(messages),
        written=tuple(written),
    )
