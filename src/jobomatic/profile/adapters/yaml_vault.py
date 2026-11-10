"""Profile stored as YAML files in the vault's ``profile/`` folder (ADR 0014).

One file per concern, so diffs stay readable. Every file must exist: a missing file is an
error, never an empty section (ADR 0007).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import BaseModel, TypeAdapter, ValidationError

from jobomatic import yamlio
from jobomatic.profile.model import (
    Certification,
    Education,
    Identity,
    Profile,
    Project,
    Role,
    Rules,
    Skills,
    Story,
)
from jobomatic.profile.service import ProfileError

# file name -> (top-level key holding a list, or None when the file is one object)
_FILES: dict[str, str | None] = {
    "identity.yaml": None,
    "roles.yaml": "roles",
    "education.yaml": "education",
    "certifications.yaml": "certifications",
    "skills.yaml": None,
    "projects.yaml": "projects",
    "stories.yaml": "stories",
    "rules.yaml": None,
}


class YamlVaultProfile:
    """``ProfileRepository`` backed by ``<vault>/profile/*.yaml``."""

    def __init__(self, profile_dir: Path) -> None:
        self._dir = profile_dir

    def load(self) -> Profile:
        raw = {name: self._read(name) for name in _FILES}
        return self._build(raw)

    def save(self, profile: Profile) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

        def dump(model: BaseModel) -> dict[str, Any]:
            return cast(dict[str, Any], yamlio.plain(model.model_dump(exclude_defaults=True)))

        certifications: dict[str, Any] = {}
        if profile.coursework_summary is not None:
            certifications["coursework_summary"] = profile.coursework_summary
        certifications["certifications"] = [dump(c) for c in profile.certifications]
        files = {
            "identity.yaml": dump(profile.identity),
            "roles.yaml": {"roles": [dump(r) for r in profile.roles]},
            "education.yaml": {"education": [dump(e) for e in profile.education]},
            "certifications.yaml": certifications,
            "skills.yaml": dump(profile.skills),
            "projects.yaml": {"projects": [dump(p) for p in profile.projects]},
            "stories.yaml": {"stories": [dump(s) for s in profile.stories]},
            "rules.yaml": dump(profile.rules),
        }
        for name, content in files.items():
            (self._dir / name).write_text(yamlio.dump(content), encoding="utf-8")

    def save_stories(self, stories: list[Story]) -> None:
        """Rewrite stories.yaml alone, leaving every other hand-edited file untouched."""
        self._dir.mkdir(parents=True, exist_ok=True)
        rows = [yamlio.plain(s.model_dump(exclude_defaults=True)) for s in stories]
        (self._dir / "stories.yaml").write_text(yamlio.dump({"stories": rows}), encoding="utf-8")

    # -- reading ---------------------------------------------------------------------------

    def _read(self, name: str) -> Any:
        path = self._dir / name
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ProfileError(f"{path}: missing profile file") from None
        try:
            return yamlio.load(text) or {}
        except yaml.YAMLError as exc:
            raise ProfileError(f"{path}: not valid YAML: {exc}") from exc

    def _build(self, raw: dict[str, Any]) -> Profile:
        coursework = raw["certifications.yaml"]
        parts: dict[str, Any] = {
            "identity": _validate(Identity, raw["identity.yaml"], "identity.yaml"),
            "roles": _validate_list(Role, raw["roles.yaml"], "roles", "roles.yaml"),
            "education": _validate_list(
                Education, raw["education.yaml"], "education", "education.yaml"
            ),
            "certifications": _validate_list(
                Certification,
                coursework,
                "certifications",
                "certifications.yaml",
                extra_keys=("coursework_summary",),
            ),
            "coursework_summary": coursework.get("coursework_summary"),
            "skills": _validate(Skills, raw["skills.yaml"], "skills.yaml"),
            "projects": _validate_list(Project, raw["projects.yaml"], "projects", "projects.yaml"),
            "stories": _validate_list(Story, raw["stories.yaml"], "stories", "stories.yaml"),
            "rules": _validate(Rules, raw["rules.yaml"], "rules.yaml"),
        }
        return Profile(**parts)


def _validate(model: type[BaseModel], data: Any, file: str) -> Any:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ProfileError(_describe(file, exc)) from exc


def _validate_list(
    model: type[BaseModel], data: Any, key: str, file: str, extra_keys: tuple[str, ...] = ()
) -> list[Any]:
    if not isinstance(data, dict) or set(data) - {key, *extra_keys}:
        raise ProfileError(f"{file}: expected a mapping with only the keys {[key, *extra_keys]}")
    try:
        return TypeAdapter(list[model]).validate_python(data.get(key, []))  # type: ignore[valid-type]
    except ValidationError as exc:
        raise ProfileError(_describe(file, exc, key)) from exc


def _describe(file: str, exc: ValidationError, key: str = "") -> str:
    """One line per problem, with a path like ``roles[2].bullets[0]``."""
    lines = [f"{file}: invalid"]
    for err in exc.errors():
        where = key
        for part in err["loc"]:
            where += f"[{part}]" if isinstance(part, int) else f"{'.' if where else ''}{part}"
        lines.append(f"  {where or '<root>'}: {err['msg']}")
    return "\n".join(lines)
