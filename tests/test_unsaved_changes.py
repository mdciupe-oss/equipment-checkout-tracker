"""The warning itself runs in the browser (JavaScript), which Flask's test
client can't execute. These tests check the server side of the contract:
the forms opt in to the guard, rejected forms start as "unsaved", and the
script is served. The click-and-leave behaviour is covered by manual steps."""

import pytest

pytestmark = pytest.mark.usefixtures("logged_in")


def add_item(client):
    client.post("/items/new", data={
        "name": "Dell Laptop", "category": "Laptop",
        "asset_tag": "LAP-001", "condition": "Good",
    })


def test_add_form_has_unsaved_changes_guard(client):
    response = client.get("/items/new")

    assert b"data-unsaved-guard" in response.data
    assert b"data-start-dirty" not in response.data
    assert b"unsaved_changes.js" in response.data


def test_edit_form_has_unsaved_changes_guard(client):
    add_item(client)

    response = client.get("/items/1/edit")

    assert b"data-unsaved-guard" in response.data
    assert b"data-start-dirty" not in response.data


def test_rejected_add_form_starts_as_unsaved(client):
    response = client.post("/items/new", data={
        "name": "", "category": "Laptop", "asset_tag": "LAP-001", "condition": "Good",
    })

    assert response.status_code == 400
    assert b"data-start-dirty" in response.data


def test_rejected_edit_form_starts_as_unsaved(client):
    add_item(client)

    response = client.post("/items/1/edit", data={
        "name": "Dell Laptop", "category": "", "asset_tag": "LAP-001", "condition": "Good",
    })

    assert response.status_code == 400
    assert b"data-start-dirty" in response.data


def test_unsaved_changes_script_is_served(client):
    response = client.get("/static/unsaved_changes.js")

    assert response.status_code == 200
    assert b"beforeunload" in response.data
