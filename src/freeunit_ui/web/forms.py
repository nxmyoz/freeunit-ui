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

import re
from dataclasses import dataclass
from typing import Any

from freeunit_ui.schema import Member, describe

#: Scalar JSON types this form can render as an input.
_EDITABLE = {"string", "integer", "number", "boolean"}

#: A JSON number (RFC 8259), stricter than Python's own int()/float(): no
#: digit-group underscores, no leading "+", no "inf"/"nan" - all valid Python
#: numeric literals, none of them valid JSON, and none of them what a person
#: typing "1_000" or "+5" into a number field is likely to have meant.
_JSON_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")

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
    """Render a stored value for an input.

    ``build`` is expected to route a list or dict value to ``preserved``
    before it ever reaches here, regardless of what the schema's declared
    type said a member should be - the check below exists so that a future
    caller which skips that step fails loudly instead of stringifying a
    container into something that reads as a plausible scalar. ``str()`` on
    a list produces its Python repr, e.g. ``"['/srv/a', '/srv/b']"``, which
    an untouched round trip would then write back as a literal string,
    silently destroying the array.
    """
    if value is None:
        return UNSET
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list | dict):
        msg = f"cannot render a {type(value).__name__} as a form field"
        raise TypeError(msg)
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
        current = values.get(member.name)
        # _kind classifies by the *declared* type, which for a union like
        # "array or string" can read as manageable text even when the value
        # actually stored is an array - a $ref resolves to a bare "object" in
        # the schema info, so "array or string" can end up looking like
        # "object or string", which passes the string-editable check. The
        # runtime value is the ground truth regardless of what the schema
        # says it could be, so a container is always left to the JSON editor.
        if kind == "other" or isinstance(current, list | dict):
            if member.name in values:
                unmanaged.append(member.name)
            continue
        fields.append(
            Field(
                name=member.name,
                kind=kind,
                description=member.description,
                required=member.required,
                value=_as_text(current),
                choices=member.enum,
                default=member.default,
            )
        )

    # Anything the specification does not describe is preserved untouched, and
    # named so the operator knows the form is not the whole picture.
    described = {m.name for m in info.members}
    unmanaged += [name for name in values if name not in described]

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
    if field.kind == "integer":
        return _coerce_integer(field, text, raw)
    if field.kind == "number":
        if not _JSON_NUMBER.fullmatch(text):
            msg = f"{field.name!r} must be a {field.kind}, got {raw!r}"
            raise CoercionError(msg)
        return float(text)
    if field.kind == "boolean":
        if text not in {"true", "false"}:
            msg = f"{field.name!r} must be true or false, got {raw!r}"
            raise CoercionError(msg)
        return text == "true"
    return text


def _coerce_integer(field: Field, text: str, raw: str) -> int:
    """Convert a submitted string to an int, tolerating a whole-numbered float.

    A member the specification declares an integer can still be stored as a
    float - an operator could have set it to ``4.0`` through the JSON editor,
    which a JSON number written with a decimal point deserialises to in
    Python. This form then renders it as the text ``"4.0"``, and an untouched
    round trip must survive submitting that back rather than failing a
    coercion it never asked for.
    """
    if not _JSON_NUMBER.fullmatch(text):
        msg = f"{field.name!r} must be a integer, got {raw!r}"
        raise CoercionError(msg)
    if "." not in text and "e" not in text and "E" not in text:
        return int(text)
    as_float = float(text)
    if not as_float.is_integer():
        msg = f"{field.name!r} must be a integer, got {raw!r}"
        raise CoercionError(msg)
    return int(as_float)


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
