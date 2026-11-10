"""Reading and writing the vault's YAML files, shared by the module adapters.

Reading refuses a key that appears twice in one mapping. PyYAML keeps the last one silently,
which hides a copy-paste slip in a hand-edited file.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, cast

import yaml


class StrictLoader(yaml.SafeLoader):
    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark
                )
            seen.add(key)
        return cast(dict[Any, Any], super().construct_mapping(node, deep))


class _Dumper(yaml.SafeDumper):
    pass


def _str_representer(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str_representer)
_Dumper.add_representer(
    date, lambda d, v: d.represent_scalar("tag:yaml.org,2002:timestamp", v.isoformat())
)


def load(text: str) -> Any:
    """Parse YAML; raises ``yaml.YAMLError`` on bad syntax or a duplicate key."""
    return yaml.load(text, Loader=StrictLoader)


def plain(value: Any) -> Any:
    """Turn enums into their values so ``dump`` can write them; dates stay dates."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def dump(content: Any) -> str:
    return cast(
        str,
        yaml.dump(
            content,
            Dumper=_Dumper,
            sort_keys=False,
            allow_unicode=True,
            width=100,
            default_flow_style=False,
        ),
    )
