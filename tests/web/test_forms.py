"""Tests for the guided editor, whose defining property is that it preserves."""

from __future__ import annotations

from typing import Any

import pytest
from flask.testing import FlaskClient

from freeunit_ui.web.forms import CoercionError, build, merge

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
    token = _token(writer)
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


def test_a_bad_value_is_reported_without_writing(writer: FlaskClient, recorder: Any) -> None:
    token = _token(writer)
    response = writer.post(
        "/form/applications/blog",
        data={"csrf_token": token, "baseline": "x", "member__threads": "many", "action": "apply"},
    )
    assert response.status_code == 400
    assert "must be a integer" in response.get_data(as_text=True)
    assert recorder.writes == []


def test_form_routes_absent_when_writes_are_disabled(web: FlaskClient) -> None:
    assert web.get("/form/applications/blog").status_code == 404


def _token(client: FlaskClient, url: str = "/form/applications/blog") -> str:
    body = client.get(url).get_data(as_text=True)
    marker = 'name="csrf_token" value="'
    start = body.index(marker) + len(marker)
    return body[start : body.index('"', start)]
