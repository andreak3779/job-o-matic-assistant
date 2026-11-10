"""Public view of a profile: what may appear on LinkedIn, GitHub and other public surfaces.

The rules, in one place (the markers live in ``model.py``):

1. A record is shown only if its effective visibility is public.
2. A field of a record or container is shown only if it is marked public. An unmarked
   field is private, so a field added later cannot leak by being forgotten.
3. A ``Part`` (a nested value such as a domain-coverage row) is shown with its parent field.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Any

from pydantic import BaseModel

from jobomatic.profile.model import Part, Record, Visibility

_DROP = object()


def public_view(model: BaseModel) -> dict[str, Any]:
    """Return the public fields of ``model`` as plain data (dates as ISO strings)."""
    result = _dump(model)
    return {} if result is _DROP else result


def _dump(model: BaseModel) -> Any:
    if isinstance(model, Record) and model.effective_visibility() is not Visibility.PUBLIC:
        return _DROP
    shown: dict[str, Any] = {}
    for name, field in type(model).model_fields.items():
        if name == "visibility":
            continue
        marker = (field.json_schema_extra or {}).get("visibility")  # type: ignore[union-attr]
        if marker != Visibility.PUBLIC.value and not isinstance(model, Part):
            continue
        value = _value(getattr(model, name))
        if value is not _DROP:
            shown[name] = value
    return shown


def _value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _dump(value)
    if isinstance(value, list):
        items = [_value(item) for item in value]
        return [item for item in items if item is not _DROP]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dt.date):
        return value.isoformat()
    return value
