"""Provenance sidecar helpers for generated artifacts."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import BaseModel


@dataclass
class Provenance:
    """Traceability metadata written alongside generated artifacts."""

    generated_at: str
    script: str
    profile_hash: str
    inputs: list[str]
    fit_rating: str | None = None
    command: str | None = None
    evidence_sources: list[str] | None = None
    warnings: list[str] | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "generated_at": self.generated_at,
            "script": self.script,
            "profile_hash": self.profile_hash,
            "inputs": self.inputs,
            "fit_rating": self.fit_rating,
            "command": self.command,
        }
        if self.evidence_sources is not None:
            result["evidence_sources"] = self.evidence_sources
        if self.warnings is not None:
            result["warnings"] = self.warnings
        return result


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def profile_hash(profile: BaseModel) -> str:
    """A short fingerprint of the profile data a document was made from.

    Two documents with the same hash came from identical data; a different hash means the profile
    changed in between.
    """
    return hashlib.sha256(profile.model_dump_json().encode("utf-8")).hexdigest()[:12]


def write_sidecar(
    artifact_path: Path,
    *,
    script: str,
    profile: BaseModel,
    inputs: list[str],
    fit_rating: str | None = None,
    command: str | None = None,
    evidence_sources: list[str] | None = None,
    warnings: list[str] | None = None,
) -> Path:
    """Write ``<artifact>.meta.json`` next to the artifact it describes.

    The ``command`` argument defaults to ``sys.argv`` so callers don't have to
    plumb it manually; pass an explicit value to override.
    """
    if command is None:
        command = " ".join(sys.argv)
    sidecar = artifact_path.parent / (artifact_path.name + ".meta.json")
    prov = Provenance(
        generated_at=now_iso(),
        script=script,
        profile_hash=profile_hash(profile),
        inputs=list(inputs),
        fit_rating=fit_rating,
        command=command,
        evidence_sources=evidence_sources,
        warnings=warnings,
    )
    sidecar.write_text(json.dumps(prov.to_dict(), indent=2) + "\n", encoding="utf-8")
    return sidecar
