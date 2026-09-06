"""A structured editor for the members the specification describes.

The objection to generating a form from a schema is that it becomes the only
way the document can be expressed, and quietly discards anything the schema does
not cover — which for a configuration format that grows every release means
losing an operator's work.

This form therefore never replaces a document. It edits the scalar members it
understands and merges them into the document as it was, leaving objects,
arrays and anything the specification has never heard of exactly where they
were. What it does not manage, it says so and preserves.

Raw JSON editing remains, and remains the way to reach everything else.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from freeunit_ui.schema import Member, describe

#: Scalar JSON types this form can render as an input.
_EDITABLE = {"string", "integer", "number", "boolean"}

#: Rendered when a boolean is not set at all, which a checkbox cannot express.
UNSET = ""


@dataclass(frozen=True, slots=True)
class Field:
    """One editable member, with its current value."""

    name: str
    kind: str
    description: str
    required: bool
    value: str
    choices: tuple[str, ...] = ()
    default: Any = None


@dataclass(frozen=True, slots=True)
class FormModel:
    """What the structured editor can and cannot manage at one path."""

    fields: tuple[Field, ...] = ()
    preserved: tuple[str, ...] = ()
    description: str = ""

    @property
    def usable(self) -> bool:
        """Whether there is anything here worth showing a form for."""
        return bool(self.fields)


def _kind(member: Member) -> str:
    """Classify a member as an input type, or 'other' when it is not scalar."""
    if member.enum:
        return "enum"
    name = member.type_name
    if name in _EDITABLE:
        return name
    # Unions such as "array or string" are editable as text only if a string is
    # among the options; anything else is left to the JSON editor.
    options = {part.strip() for part in name.split(" or ")} if name else set()
    if "string" in options and options <= _EDITABLE | {"array", "object"}:
        return "string"
    return "other"


def _as_text(value: Any) -> str:
    """Render a stored value for an input."""
    if value is None:
        return UNSET
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build(segments: list[str], document: Any) -> FormModel:
    """Describe the structured editor for ``document`` at ``segments``."""
    info = describe(segments, document)
    if info is None:
        return FormModel()

    values = document if isinstance(document, dict) else {}
    fields: list[Field] = []
    unmanaged: list[str] = []

    for member in info.members:
        kind = _kind(member)
        if kind == "other":
            if member.name in values:
                unmanaged.append(member.name)
            continue
        fields.append(
            Field(
                name=member.name,
                kind=kind,
                description=member.description,
                required=member.required,
                value=_as_text(values.get(member.name)),
                choices=member.enum,
                default=member.default,
            )
        )

    # Anything the specification does not describe is preserved untouched, and
    # named so the operator knows the form is not the whole picture.
    unmanaged += [name for name in values if name not in {m.name for m in info.members}]

    return FormModel(
        fields=tuple(fields),
        preserved=tuple(sorted(set(unmanaged))),
        description=info.description,
    )


class CoercionError(ValueError):
    """A submitted value does not fit the member's declared type."""


def _coerce(field: Field, raw: str) -> Any:
    """Convert a submitted string to the member's type."""
    text = raw.strip()
    if field.kind in {"integer", "number"}:
        try:
            return int(text) if field.kind == "integer" else float(text)
        except ValueError as exc:
            msg = f"{field.name!r} must be a {field.kind}, got {raw!r}"
            raise CoercionError(msg) from exc
    if field.kind == "boolean":
        if text not in {"true", "false"}:
            msg = f"{field.name!r} must be true or false, got {raw!r}"
            raise CoercionError(msg)
        return text == "true"
    return text


def merge(model: FormModel, document: Any, submitted: dict[str, str]) -> dict[str, Any]:
    """Apply submitted values onto ``document`` without disturbing the rest.

    A blank value removes an optional member; everything the form does not
    manage is carried across untouched.

    Raises:
        CoercionError: A value does not fit its member's declared type.
    """
    merged: dict[str, Any] = dict(document) if isinstance(document, dict) else {}

    for field in model.fields:
        raw = submitted.get(f"member__{field.name}", UNSET)
        if raw.strip() == UNSET:
            # Blank clears an optional member. Required ones are left alone, so
            # the form cannot produce a document it knows to be invalid.
            if not field.required:
                merged.pop(field.name, None)
            continue
        merged[field.name] = _coerce(field, raw)

    return merged
