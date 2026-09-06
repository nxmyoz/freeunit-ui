"""Guidance derived from FreeUnit's OpenAPI specification.

Everything here is **advisory**. unitd does not serve its own specification, so
the copy vendored alongside this module is pinned to one release and will drift
from whatever server the interface is pointed at. A newer server will accept
members this schema has never heard of.

So nothing in this module ever refuses a configuration. It answers two
questions and no more: what does this member mean, and what does a valid
starting point look like. unitd remains the only authority on what is valid,
and its rejection is already reported with a JSON Pointer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

_HERE = Path(__file__).parent

#: FreeUnit release the vendored specification came from.
SPEC_VERSION = (_HERE / "VERSION").read_text(encoding="utf-8").strip()

#: ``type`` values map onto per-language schemas by convention, not by anything
#: the specification states, so the mapping is written out rather than guessed.
_APPLICATION_SCHEMAS = {
    "external": "configApplicationExternal",
    "java": "configApplicationJava",
    "perl": "configApplicationPerl",
    "php": "configApplicationPHP",
    "python": "configApplicationPython",
    "ruby": "configApplicationRuby",
    "wasm": "configApplicationWasm",
    "wasm-wasi-component": "configApplicationWasi",
}


@cache
def _schemas() -> dict[str, Any]:
    """Return the vendored schema components."""
    spec = json.loads((_HERE / "unit-openapi.json").read_text(encoding="utf-8"))
    components: dict[str, Any] = spec.get("components", {}).get("schemas", {})
    return components


@dataclass(frozen=True, slots=True)
class Member:
    """One documented member of a configuration object."""

    name: str
    type_name: str
    description: str
    required: bool = False
    default: Any = None
    enum: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SchemaInfo:
    """What the specification says about one point in the configuration."""

    description: str = ""
    members: tuple[Member, ...] = ()
    unknown_members: tuple[str, ...] = field(default=())

    def member(self, name: str) -> Member | None:
        """Return one documented member by name."""
        return next((m for m in self.members if m.name == name), None)


def _resolve(node: Any, seen: tuple[str, ...] = ()) -> tuple[dict[str, Any], set[str], str]:
    """Flatten ``$ref`` and ``allOf`` into properties, required names and a description."""
    if not isinstance(node, dict):
        return {}, set(), ""

    ref = node.get("$ref")
    if isinstance(ref, str):
        name = ref.rsplit("/", 1)[-1]
        if name in seen:
            return {}, set(), ""
        return _resolve(_schemas().get(name, {}), (*seen, name))

    props: dict[str, Any] = dict(node.get("properties") or {})
    required: set[str] = set(node.get("required") or ())
    description = str(node.get("description") or "")

    for part in node.get("allOf") or ():
        sub_props, sub_required, sub_description = _resolve(part, seen)
        props.update(sub_props)
        required |= sub_required
        description = description or sub_description

    return props, required, description


def _type_name(prop: Any) -> str:
    """Render a member's type for display, tolerating unions."""
    if not isinstance(prop, dict):
        return ""
    if isinstance(prop.get("type"), str):
        return str(prop["type"])
    if "$ref" in prop:
        return "object"
    for key in ("anyOf", "oneOf"):
        options = prop.get(key)
        if isinstance(options, list):
            names = sorted({_type_name(option) for option in options if _type_name(option)})
            return " or ".join(names)
    return ""


def _descend(node: Any, segment: str) -> Any:
    """Return the schema for ``segment`` within ``node``, or ``None``."""
    resolved = node
    if isinstance(node, dict) and "$ref" in node:
        resolved = _schemas().get(str(node["$ref"]).rsplit("/", 1)[-1], {})
    if not isinstance(resolved, dict):
        return None

    props = (resolved.get("properties") or {}) if isinstance(resolved, dict) else {}
    if segment in props:
        return props[segment]

    # Listener addresses and application names are chosen by the operator, so
    # they are expressed as additionalProperties rather than named members.
    additional = resolved.get("additionalProperties")
    if isinstance(additional, dict):
        return additional
    return None


def _select_branch(node: Any, document: Any) -> Any:
    """Pick the right branch of an ``anyOf`` using the document's own ``type``."""
    if not isinstance(node, dict):
        return node
    target = node
    if "$ref" in node:
        target = _schemas().get(str(node["$ref"]).rsplit("/", 1)[-1], {})
    if not isinstance(target, dict) or "anyOf" not in target:
        return node

    kind = ""
    if isinstance(document, dict) and isinstance(document.get("type"), str):
        kind = document["type"].split()[0]
    schema_name = _APPLICATION_SCHEMAS.get(kind)
    if schema_name:
        return {"$ref": f"#/components/schemas/{schema_name}"}
    return node


def describe(segments: list[str], value: Any = None) -> SchemaInfo | None:
    """Describe the configuration object at ``segments``.

    Args:
        segments: Configuration path below ``/config``, empty for the root.
        value: The document actually stored at that path. Used only to pick the
            right branch of a union — an application's schema depends on its
            ``type`` — and to report members this copy of the specification does
            not know about.

    Returns:
        What the specification says, or ``None`` when the path is not described.
        That is not an error: the server may well know members this copy does
        not, which is why nothing here refuses anything.
    """
    node: Any = {"$ref": "#/components/schemas/config"}
    for segment in segments:
        node = _descend(node, segment)
        if node is None:
            return None

    node = _select_branch(node, value)
    props, required, description = _resolve(node)
    if not props and not description:
        return None

    members = tuple(
        Member(
            name=name,
            type_name=_type_name(prop),
            description=str(prop.get("description") or "") if isinstance(prop, dict) else "",
            required=name in required,
            default=prop.get("default") if isinstance(prop, dict) else None,
            enum=tuple(str(v) for v in prop.get("enum", ()))
            if isinstance(prop, dict) and isinstance(prop.get("enum"), list)
            else (),
        )
        for name, prop in sorted(props.items())
    )

    unknown: tuple[str, ...] = ()
    if isinstance(value, dict) and props:
        unknown = tuple(sorted(key for key in value if key not in props))

    return SchemaInfo(description=description, members=members, unknown_members=unknown)
