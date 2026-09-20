"""Tests for the guided editor, whose defining property is that it preserves."""

from __future__ import annotations

from typing import Any

import pytest
from flask.testing import FlaskClient

from freeunit_ui.web.forms import CoercionError, Field, FormModel, build, merge
from tests.web.conftest import token_from

APP = {
    "type": "python 3",
    "module": "blog.wsgi",
    "processes": {"max": 8, "spare": 2},
    "environment": {"LANG": "C"},
    "invented_later": "keep me",
}


def test_scalar_members_are_editable() -> None:
    model = build(["applications", "blog"], APP)
    editable = {f.name for f in model.fields}
    assert {"module", "callable", "user", "threads"} <= editable


def test_objects_and_unknown_members_are_not_managed() -> None:
    model = build(["applications", "blog"], APP)
    assert "processes" in model.preserved
    assert "environment" in model.preserved
    assert "invented_later" in model.preserved
    assert "processes" not in {f.name for f in model.fields}


def test_merging_leaves_everything_it_does_not_manage() -> None:
    # The property the whole design rests on: a form round trip must not lose
    # objects, arrays, or members the specification has never heard of.
    model = build(["applications", "blog"], APP)
    merged = merge(model, APP, {"member__module": "new.wsgi", "member__type": "python 3"})
    assert merged["processes"] == APP["processes"]
    assert merged["environment"] == APP["environment"]
    assert merged["invented_later"] == "keep me"
    assert merged["module"] == "new.wsgi"


def test_an_untouched_round_trip_changes_nothing() -> None:
    model = build(["applications", "blog"], APP)
    submitted = {f"member__{f.name}": f.value for f in model.fields}
    assert merge(model, APP, submitted) == APP


def test_an_array_valued_member_is_not_offered_as_a_field() -> None:
    # `path` is string-or-array in the specification. A $ref resolves to a
    # bare "object" in the schema info, so the union can read as
    # string-editable even when the value actually stored is an array - the
    # runtime value, not the declared type, has to decide.
    document = {**APP, "path": ["/srv/blog/a", "/srv/blog/b"]}
    model = build(["applications", "blog"], document)
    assert "path" not in {f.name for f in model.fields}
    assert "path" in model.preserved


def test_an_array_valued_member_survives_an_untouched_round_trip() -> None:
    # Without the runtime-value check, str() on the list turns it into its
    # Python repr, e.g. "['/srv/blog/a', '/srv/blog/b']", which a submission
    # that never touched the field would then write back as a literal
    # string - destroying the array on a no-op edit.
    document = {**APP, "path": ["/srv/blog/a", "/srv/blog/b"]}
    model = build(["applications", "blog"], document)
    submitted = {f"member__{f.name}": f.value for f in model.fields}
    assert merge(model, document, submitted)["path"] == ["/srv/blog/a", "/srv/blog/b"]


def test_blank_removes_an_optional_member() -> None:
    document = {**APP, "callable": "application"}
    model = build(["applications", "blog"], document)
    merged = merge(model, document, {"member__module": "blog.wsgi", "member__callable": ""})
    assert "callable" not in merged


def test_blank_never_removes_a_required_member() -> None:
    # The form must not be able to produce a document it knows is invalid.
    model = build(["applications", "blog"], APP)
    merged = merge(model, APP, {"member__module": "", "member__type": ""})
    assert merged["module"] == "blog.wsgi"
    assert merged["type"] == "python 3"


def test_numbers_and_booleans_are_coerced() -> None:
    model = build(["applications", "blog"], APP)
    merged = merge(model, APP, {"member__threads": "4"})
    assert merged["threads"] == 4
    assert isinstance(merged["threads"], int)


def test_a_bad_number_is_rejected() -> None:
    model = build(["applications", "blog"], APP)
    with pytest.raises(CoercionError, match="threads"):
        merge(model, APP, {"member__threads": "several"})


def test_a_whole_numbered_float_survives_an_untouched_integer_round_trip() -> None:
    # A member the specification declares an integer can still be stored as a
    # float - an operator could have set "threads": 4.0 through the JSON
    # editor. This form then renders it as "4.0", and resubmitting that
    # unchanged must not fail a coercion the operator never asked for.
    document = {**APP, "threads": 4.0}
    model = build(["applications", "blog"], document)
    submitted = {f"member__{f.name}": f.value for f in model.fields}
    assert merge(model, document, submitted)["threads"] == 4


def test_a_non_whole_float_is_still_rejected_for_an_integer_member() -> None:
    model = build(["applications", "blog"], APP)
    with pytest.raises(CoercionError, match="threads"):
        merge(model, APP, {"member__threads": "4.5"})


@pytest.mark.parametrize("value", ["1_000", "+5", "inf", "nan", "infinity"])
def test_python_only_numeric_literals_are_rejected_for_an_integer_member(value: str) -> None:
    # int()/float() also parse digit-group underscores, a leading "+", and
    # the non-finite spellings - all valid Python literals, none valid JSON,
    # and none likely what someone typing that text actually meant.
    model = build(["applications", "blog"], APP)
    with pytest.raises(CoercionError, match="threads"):
        merge(model, APP, {"member__threads": value})


def _number_model() -> FormModel:
    # No bundled specification member is currently typed "number", so this
    # kind is exercised directly rather than through build().
    field = Field(name="weight", kind="number", description="", required=False, value="1.0")
    return FormModel(fields=(field,))


def test_a_number_field_is_coerced_to_float() -> None:
    merged = merge(_number_model(), {}, {"member__weight": "0.5"})
    assert merged["weight"] == 0.5


@pytest.mark.parametrize("value", ["1_000.0", "+5.0", "inf", "nan", "infinity"])
def test_python_only_numeric_literals_are_rejected_for_a_number_member(value: str) -> None:
    with pytest.raises(CoercionError, match="weight"):
        merge(_number_model(), {}, {"member__weight": value})


def test_scientific_notation_survives_a_number_round_trip() -> None:
    # str(1e-05) == "1e-05" - the text this form would actually render for a
    # small stored float - so the strict number pattern must still accept it.
    field = Field(name="weight", kind="number", description="", required=False, value="1e-05")
    model = FormModel(fields=(field,))
    merged = merge(model, {}, {"member__weight": field.value})
    assert merged["weight"] == 1e-05


def test_enum_members_offer_their_choices() -> None:
    model = build(["applications", "blog"], APP)
    kind = next(f for f in model.fields if f.name == "type")
    assert kind.kind == "enum"
    assert "python" in kind.choices


def test_undescribed_paths_have_no_form() -> None:
    assert not build(["nowhere"], {}).usable


# --- through the interface -------------------------------------------------


def test_guided_editor_renders(writer: FlaskClient) -> None:
    body = writer.get("/form/applications/blog").get_data(as_text=True)
    assert "Guided" in body
    assert 'name="member__module"' in body


def test_both_modes_link_to_each_other(writer: FlaskClient) -> None:
    guided = writer.get("/form/applications/blog").get_data(as_text=True)
    raw = writer.get("/edit/applications/blog").get_data(as_text=True)
    assert "/edit/applications/blog" in guided
    assert "/form/applications/blog" in raw


def test_the_form_says_what_it_will_not_touch(writer: FlaskClient) -> None:
    body = writer.get("/form/applications/blog").get_data(as_text=True)
    assert "Left untouched by this form" in body
    assert "<code>processes</code>" in body


def test_applying_from_the_form_preserves_unmanaged_members(
    writer: FlaskClient, recorder: Any
) -> None:
    from freeunit_ui.web.writes import baseline_digest
    from tests.conftest import CONFIG_PAYLOAD

    stored = CONFIG_PAYLOAD["applications"]["blog"]
    token = token_from(writer, "/form/applications/blog")
    response = writer.post(
        "/form/applications/blog",
        data={
            "csrf_token": token,
            "baseline": baseline_digest(stored),
            "member__type": stored["type"],
            "member__path": "/srv/moved",
            "action": "apply",
            "confirm": "yes",
            "reason": "moved the checkout",
        },
    )
    assert response.status_code == 302
    method, path, body = recorder.writes[0]
    assert (method, path) == ("PUT", "/config/applications/blog")
    assert body["path"] == "/srv/moved"
    # everything the form does not manage survived
    assert body["type"] == stored["type"]


def _hidden_field(body: str, name: str) -> str:
    marker = f'name="{name}" value="'
    start = body.index(marker) + len(marker)
    return body[start : body.index('"', start)]


def test_check_then_confirm_applies_a_real_change(writer: FlaskClient, recorder: Any) -> None:
    # Regression test: _render_structured used to recompute the baseline from
    # whatever it was handed at each step - the merged document on the check
    # branch - rather than carrying the operator's submitted baseline
    # forward. Since the merged document differs from the server's stored
    # value by definition (that is the whole point of the edit), the
    # baseline threaded into the eventual _commit() never matched, and a
    # real edit through Check could not be confirmed: every attempt 409'd.
    from freeunit_ui.web.writes import baseline_digest
    from tests.conftest import CONFIG_PAYLOAD

    stored = CONFIG_PAYLOAD["applications"]["blog"]
    token = token_from(writer, "/form/applications/blog")
    checked = writer.post(
        "/form/applications/blog",
        data={
            "csrf_token": token,
            "baseline": baseline_digest(stored),
            "member__type": stored["type"],
            "member__path": "/srv/moved",
            "action": "check",
        },
    )
    assert checked.status_code == 200
    body = checked.get_data(as_text=True)
    carried_baseline = _hidden_field(body, "baseline")

    confirmed = writer.post(
        "/form/applications/blog",
        data={
            "csrf_token": token,
            "baseline": carried_baseline,
            "member__type": stored["type"],
            "member__path": "/srv/moved",
            "action": "apply",
            "confirm": "yes",
        },
    )
    assert confirmed.status_code == 302
    method, path, applied = recorder.writes[0]
    assert (method, path) == ("PUT", "/config/applications/blog")
    assert applied["path"] == "/srv/moved"


def test_a_concurrent_change_is_a_conflict_after_check(writer: FlaskClient, recorder: Any) -> None:
    # The other direction of the same bug: recomputing the baseline at each
    # step doesn't just cause false conflicts, it can also paper over a real
    # one, since a fresh recompute always matches whatever is in front of it
    # rather than what the operator actually started editing from.
    from freeunit_ui.web.writes import baseline_digest
    from tests.conftest import CONFIG_PAYLOAD

    stored = CONFIG_PAYLOAD["applications"]["blog"]
    token = token_from(writer, "/form/applications/blog")
    original_baseline = baseline_digest(stored)

    # Another operator's change lands after this form was loaded.
    recorder.routes["/config/applications/blog"] = {**stored, "path": "/srv/elsewhere"}

    checked = writer.post(
        "/form/applications/blog",
        data={
            "csrf_token": token,
            "baseline": original_baseline,
            "member__type": stored["type"],
            "member__path": "/srv/moved",
            "action": "check",
        },
    )
    assert checked.status_code == 200
    carried_baseline = _hidden_field(checked.get_data(as_text=True), "baseline")

    confirmed = writer.post(
        "/form/applications/blog",
        data={
            "csrf_token": token,
            "baseline": carried_baseline,
            "member__type": stored["type"],
            "member__path": "/srv/moved",
            "action": "apply",
            "confirm": "yes",
        },
    )
    assert confirmed.status_code == 409
    assert recorder.writes == []


def test_form_apply_refuses_a_non_object_document(writer: FlaskClient, recorder: Any) -> None:
    # merge() defaults a non-dict document to {} - the guided editor's whole
    # premise is that it never replaces a document, so a hand-crafted POST to
    # a path holding a list must be refused rather than silently replacing it
    # with an empty object. The template hides the form itself in this case,
    # which is a display choice, not enforcement.
    recorder.routes["/config/routes"] = ["one", "two"]
    token = token_from(writer, "/form/applications/blog")
    response = writer.post(
        "/form/routes",
        data={"csrf_token": token, "baseline": "x", "action": "apply", "confirm": "yes"},
    )
    assert response.status_code == 400
    assert recorder.writes == []


def test_a_bad_value_is_reported_without_writing(writer: FlaskClient, recorder: Any) -> None:
    token = token_from(writer, "/form/applications/blog")
    response = writer.post(
        "/form/applications/blog",
        data={"csrf_token": token, "baseline": "x", "member__threads": "many", "action": "apply"},
    )
    assert response.status_code == 400
    assert "must be a integer" in response.get_data(as_text=True)
    assert recorder.writes == []


def test_form_routes_absent_when_writes_are_disabled(web: FlaskClient) -> None:
    assert web.get("/form/applications/blog").status_code == 404
