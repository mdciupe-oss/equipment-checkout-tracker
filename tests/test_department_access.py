"""Each user only sees and changes equipment in their own department.

Alice works in Library and owns LIB-001. Bob works in Facilities and owns
FAC-001. Each test checks that one of them cannot reach the other's item,
including by typing the item's URL directly.
"""
import pytest

from tracker.db import get_db

from conftest import log_in

PASSWORD = "correct-horse-battery"


def add(client, name, asset_tag, **extra):
    return client.post("/items/new", data={
        "name": name, "category": "Misc", "asset_tag": asset_tag,
        "condition": "Good", **extra,
    })


def row(app, asset_tag):
    with app.app_context():
        found = get_db().execute(
            "SELECT e.*, d.name AS department FROM equipment_item e"
            " JOIN department d ON d.id = e.department_id WHERE asset_tag = ?",
            (asset_tag,),
        ).fetchone()
        return dict(found) if found else None


def all_rows(app):
    with app.app_context():
        return [dict(r) for r in get_db().execute("SELECT * FROM equipment_item ORDER BY id")]


@pytest.fixture
def alice(app, make_user):
    make_user("alice", PASSWORD, department="Library")
    client = app.test_client()
    log_in(client, "alice", PASSWORD)
    add(client, "Library Laptop", "LIB-001")
    return client


@pytest.fixture
def bob(app, make_user):
    make_user("bob", PASSWORD, department="Facilities")
    client = app.test_client()
    log_in(client, "bob", PASSWORD)
    add(client, "Facilities Drill", "FAC-001")
    return client


@pytest.fixture
def bobs_item(app, bob):
    return row(app, "FAC-001")


# --- Seeing ---------------------------------------------------------------

def test_list_shows_only_own_department(alice, bob):
    alice_page = alice.get("/items/").data
    bob_page = bob.get("/items/").data

    assert b"Library Laptop" in alice_page
    assert b"Facilities Drill" not in alice_page
    assert b"Facilities Drill" in bob_page
    assert b"Library Laptop" not in bob_page


def test_list_has_no_links_to_other_departments_items(alice, bobs_item):
    page = alice.get("/items/").data

    assert f"/items/{bobs_item['id']}/".encode() not in page


# --- Adding ---------------------------------------------------------------

def test_new_item_gets_users_department(app, alice, bob):
    assert row(app, "LIB-001")["department"] == "Library"
    assert row(app, "FAC-001")["department"] == "Facilities"


def test_department_sent_in_form_is_ignored(app, alice, bob):
    facilities_id = row(app, "FAC-001")["department_id"]

    add(alice, "Sneaky Laptop", "LIB-002", department_id=str(facilities_id))

    assert row(app, "LIB-002")["department"] == "Library"


# --- Typed URLs to another department's item return 404 ---------------------

def test_open_edit_form_of_other_department_item_is_not_found(alice, bobs_item):
    response = alice.get(f"/items/{bobs_item['id']}/edit")

    assert response.status_code == 404
    assert b"Facilities Drill" not in response.data


def test_submit_edit_of_other_department_item_is_not_found(app, alice, bobs_item):
    response = alice.post(f"/items/{bobs_item['id']}/edit", data={
        "name": "Hacked", "category": "Hacked", "asset_tag": "FAC-001", "condition": "Fair",
    })

    assert response.status_code == 404
    assert row(app, "FAC-001") == bobs_item


def test_retire_other_department_item_is_not_found(app, alice, bobs_item):
    response = alice.post(f"/items/{bobs_item['id']}/retire")

    assert response.status_code == 404
    assert row(app, "FAC-001")["status"] == "Available"


def test_reactivate_other_department_item_is_not_found(app, alice, bob, bobs_item):
    bob.post(f"/items/{bobs_item['id']}/retire")
    before = row(app, "FAC-001")
    assert before["status"] == "Retired"

    response = alice.post(f"/items/{bobs_item['id']}/reactivate")

    assert response.status_code == 404
    assert row(app, "FAC-001") == before


def test_other_department_item_looks_the_same_as_missing_item(alice, bobs_item):
    other = alice.get(f"/items/{bobs_item['id']}/edit")
    missing = alice.get("/items/9999/edit")

    assert other.status_code == missing.status_code == 404
    assert other.data == missing.data


# --- Own department still works -------------------------------------------

def test_user_can_edit_retire_and_reactivate_own_item(app, alice, bob):
    own = row(app, "LIB-001")

    alice.post(f"/items/{own['id']}/edit", data={
        "name": "Library Laptop 2", "category": "Misc", "asset_tag": "LIB-001", "condition": "Fair",
    })
    assert row(app, "LIB-001")["name"] == "Library Laptop 2"

    alice.post(f"/items/{own['id']}/retire")
    assert row(app, "LIB-001")["status"] == "Retired"

    alice.post(f"/items/{own['id']}/reactivate")
    assert row(app, "LIB-001")["status"] == "Available"


# --- Asset tags are unique across ALL departments -----------------------------

@pytest.mark.parametrize("tag", ["FAC-001", "fac-001"])
def test_cannot_add_asset_tag_used_in_other_department(app, alice, bob, tag):
    before = all_rows(app)

    response = add(alice, "Another Drill", tag)

    assert response.status_code == 400
    assert b"is already in use." in response.data
    assert all_rows(app) == before


def test_cannot_edit_to_asset_tag_used_in_other_department(app, alice, bob):
    own = row(app, "LIB-001")

    response = alice.post(f"/items/{own['id']}/edit", data={
        "name": own["name"], "category": own["category"],
        "asset_tag": "FAC-001", "condition": own["condition"],
    })

    assert response.status_code == 400
    assert b"is already in use." in response.data
    assert row(app, "LIB-001") == own
