"""Endpoints that change the FreeUnit configuration.

This blueprint is registered only when ``enable_writes`` is set. When it is not,
these routes do not exist: there is no endpoint to reach, rather than an
endpoint that declines.

Every change follows the same sequence, and the order matters:

1. verify the CSRF token,
2. re-read the subtree and compare it with the baseline the form was built from,
   because the control API offers no ``ETag`` and two operators would otherwise
   silently overwrite each other,
3. snapshot the whole configuration, because the API has no undo,
4. apply, and surface the API's own validation error if it refuses.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from flask import Blueprint, redirect, render_template, request, url_for
from werkzeug.wrappers import Response

from freeunit_ui.diff import compare
from freeunit_ui.extensions import get_client, get_snapshots, get_write_client
from freeunit_ui.schema import SPEC_VERSION, describe
from freeunit_ui.schema import scaffolds as scaffold_catalogue
from freeunit_ui.schema.validation import check as check_document
from freeunit_ui.unit.errors import UnitAPIError

from .auth import current_identity
from .csrf import FIELD_NAME, CsrfError, issue_token, validate
from .forms import CoercionError
from .forms import build as build_form
from .forms import merge as merge_form
from .paths import breadcrumbs, split_config_path, to_api_path

bp = Blueprint("writes", __name__)

# Configuration members are named by the operator, so an action word must never
# appear as a segment inside a configuration path: an application called "edit"
# would otherwise be unreachable. Editing lives under its own /edit prefix, with
# the same URL serving the form and receiving the change, and snapshots sit at
# the top level rather than under /edit for the same reason.


class ConflictError(Exception):
    """The configuration changed between loading the form and submitting it."""


def baseline_digest(payload: Any) -> str:
    """Return a stable digest of a configuration subtree.

    Keys are sorted so that a document which is semantically unchanged does not
    read as a conflict merely because unitd serialised it differently.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_or_absent(api_path: str) -> tuple[Any, bool]:
    """Return the value at ``api_path``, or ``(None, True)`` when it does not exist.

    A path that does not exist yet is how a new listener or application is
    created, so it is a normal case rather than an error.
    """
    try:
        with get_client() as client:
            return client.get_json(api_path), False
    except UnitAPIError as error:
        if error.status_code == 404:
            return None, True
        raise


def _render_form(
    segments: list[str],
    *,
    document: str,
    baseline: str,
    absent: bool = False,
    error: str | None = None,
    findings: list[Any] | None = None,
    awaiting_confirmation: bool = False,
    reason: str = "",
) -> str:
    """Render the editing form in any of its states."""
    return render_template(
        "edit.html",
        segments=segments,
        crumbs=breadcrumbs(segments),
        subpath="/".join(segments),
        document=document,
        baseline=baseline,
        csrf_token=issue_token(),
        absent=absent,
        error=error,
        findings=findings or [],
        awaiting_confirmation=awaiting_confirmation,
        reason=reason,
        scaffolds=scaffold_catalogue.for_path(segments),
        info=describe(segments),
        spec_version=SPEC_VERSION,
    )


@bp.get("/edit/")
@bp.get("/edit/<path:subpath>")
def edit(subpath: str = "") -> str:
    """Show the editing form for a configuration subtree."""
    segments = split_config_path(subpath)
    payload, absent = _read_or_absent(to_api_path(segments))

    chosen = scaffold_catalogue.get(request.args.get("template", ""))
    document = chosen.as_json() if chosen else json.dumps(payload, indent=2, ensure_ascii=False)

    return _render_form(
        segments,
        document="" if absent and not chosen else document,
        baseline=baseline_digest(payload),
        absent=absent,
    )


@bp.post("/edit/")
@bp.post("/edit/<path:subpath>")
def apply(subpath: str = "") -> Response | str | tuple[str, int]:
    """Validate, snapshot and apply an edited subtree."""
    validate(request.form.get(FIELD_NAME))
    segments = split_config_path(subpath)
    api_path = to_api_path(segments)

    submitted = request.form.get("document", "")
    baseline = request.form.get("baseline", "")
    try:
        document = json.loads(submitted)
    except ValueError as exc:
        return (
            _render_form(
                segments,
                document=submitted,
                baseline=baseline,
                error=f"That is not valid JSON: {exc}",
                reason=request.form.get("reason", ""),
            ),
            400,
        )

    # Advisory only. The bundled specification is pinned to one release while
    # the server is not, so findings warn and ask rather than refuse: the
    # operator can always proceed, and unitd remains the authority.
    findings = check_document(segments, document)
    confirmed = request.form.get("confirm") == "yes"
    if request.form.get("action") == "check" or (findings and not confirmed):
        return _render_form(
            segments,
            document=submitted,
            baseline=baseline,
            findings=findings,
            awaiting_confirmation=bool(findings),
            reason=request.form.get("reason", ""),
        )

    return _commit(segments, api_path, document, baseline, request.form.get("reason", ""))


def _commit(
    segments: list[str], api_path: str, document: Any, baseline: str, reason: str
) -> Response:
    """Snapshot, apply, verify and redirect. Shared by both editing modes."""
    current, _ = _read_or_absent(api_path)
    if baseline_digest(current) != baseline:
        msg = (
            "The configuration changed while you were editing it. Reload the form "
            "to see the current value before applying your change."
        )
        raise ConflictError(msg)

    with get_client() as reader:
        snapshot = get_snapshots().save(
            reader.get_config(), author=current_identity(), reason=reason.strip() or None
        )

    with get_write_client() as writer:
        writer.put_json(api_path, document)

    stored, _ = _read_or_absent(api_path)
    outcome = "applied" if baseline_digest(stored) == baseline_digest(document) else "differs"
    return redirect(
        url_for("web.config", subpath="/".join(segments), undo=snapshot.name, outcome=outcome)
    )


@bp.get("/form/")
@bp.get("/form/<path:subpath>")
def form(subpath: str = "") -> str:
    """Show the structured editor for the members the specification describes."""
    segments = split_config_path(subpath)
    payload, absent = _read_or_absent(to_api_path(segments))
    return _render_structured(segments, payload, absent=absent)


def _render_structured(
    segments: list[str],
    payload: Any,
    *,
    absent: bool = False,
    error: str | None = None,
    findings: list[Any] | None = None,
    awaiting_confirmation: bool = False,
    reason: str = "",
    overrides: dict[str, str] | None = None,
) -> str:
    """Render the structured editor in any of its states."""
    model = build_form(segments, payload)
    return render_template(
        "form.html",
        segments=segments,
        crumbs=breadcrumbs(segments),
        subpath="/".join(segments),
        model=model,
        overrides=overrides or {},
        baseline=baseline_digest(payload),
        csrf_token=issue_token(),
        absent=absent,
        error=error,
        findings=findings or [],
        awaiting_confirmation=awaiting_confirmation,
        reason=reason,
        spec_version=SPEC_VERSION,
    )


@bp.post("/form/")
@bp.post("/form/<path:subpath>")
def form_apply(subpath: str = "") -> Response | str | tuple[str, int]:
    """Merge submitted fields into the stored document and apply."""
    validate(request.form.get(FIELD_NAME))
    segments = split_config_path(subpath)
    api_path = to_api_path(segments)
    baseline = request.form.get("baseline", "")
    reason = request.form.get("reason", "")
    submitted = {key: value for key, value in request.form.items() if key.startswith("member__")}

    payload, absent = _read_or_absent(api_path)
    model = build_form(segments, payload)
    try:
        document = merge_form(model, payload, submitted)
    except CoercionError as exc:
        return (
            _render_structured(
                segments,
                payload,
                absent=absent,
                error=str(exc),
                reason=reason,
                overrides=submitted,
            ),
            400,
        )

    findings = check_document(segments, document)
    confirmed = request.form.get("confirm") == "yes"
    if request.form.get("action") == "check" or (findings and not confirmed):
        return _render_structured(
            segments,
            document,
            absent=absent,
            findings=findings,
            awaiting_confirmation=bool(findings),
            reason=reason,
            overrides=submitted,
        )

    return _commit(segments, api_path, document, baseline, reason)


@bp.get("/snapshots")
def snapshots() -> str:
    """List stored configuration snapshots."""
    return render_template(
        "snapshots.html", snapshots=get_snapshots().list(), csrf_token=issue_token()
    )


@bp.get("/snapshots/<name>/diff")
def diff(name: str) -> str:
    """Show what changed between a snapshot and the running configuration.

    ``against`` compares two snapshots instead, which is how a change made
    between two known points is isolated.
    """
    store = get_snapshots()
    snapshot = store.get(name)

    other = request.args.get("against", "")
    if other:
        comparison = store.get(other)
        later, later_label = comparison.load(), comparison.name
    else:
        with get_client() as reader:
            later = reader.get_config()
        later_label = "running configuration"

    return render_template(
        "diff.html",
        snapshot=snapshot,
        later_label=later_label,
        changes=compare(snapshot.load(), later),
        others=[s for s in store.list() if s.name != name],
    )


@bp.post("/snapshots/<name>/restore")
def restore(name: str) -> Response:
    """Restore a stored snapshot over the whole configuration."""
    validate(request.form.get(FIELD_NAME))
    store = get_snapshots()
    document = store.get(name).load()

    # Snapshot the state we are about to replace, so restoring is itself undoable.
    with get_client() as reader:
        store.save(
            reader.get_config(),
            author=current_identity(),
            reason=f"before restoring snapshot {name}",
        )

    with get_write_client() as writer:
        writer.put_json("/config", document)

    return redirect(url_for("web.config"))


@bp.app_errorhandler(CsrfError)
def _csrf_failed(error: CsrfError) -> tuple[str, int]:
    """Render a 400 for a missing or mismatched CSRF token."""
    return (
        render_template(
            "error.html",
            title="Request rejected",
            detail=str(error),
            hint="This protects against another site submitting changes on your behalf.",
        ),
        400,
    )


@bp.app_errorhandler(ConflictError)
def _conflict(error: ConflictError) -> tuple[str, int]:
    """Render a 409 when the configuration moved under the editor."""
    return render_template("error.html", title="Configuration changed", detail=str(error)), 409
