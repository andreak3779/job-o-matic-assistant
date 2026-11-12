"""Render a role-specific learning plan PDF from a role config (ADR 0028).

The config is authored by the learning-plan skills (see ``templates/roles/_example.json``); this
only renders it. The PDF goes wherever the config's own ``output`` key says.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jobomatic.results import CommandResult, guarded, ok


@dataclass(frozen=True)
class LearningPlanData:
    pdf: Path


def run(config: Path) -> CommandResult[LearningPlanData]:
    """Render the plan described by the role JSON at ``config``."""
    return guarded(lambda: _run(config))


def _run(config: Path) -> CommandResult[LearningPlanData]:
    # Imported here because reportlab belongs to the optional ``pdf`` extra.
    from jobomatic.documents.adapters import pdf_template

    pdf = pdf_template.render_config_file(config)
    return ok(LearningPlanData(pdf), written=(pdf,))
