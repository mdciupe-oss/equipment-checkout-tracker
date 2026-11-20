import pytest

from tracker.db import get_db


@pytest.fixture
def item(client, app):
    """One saved, available item; returns its database row."""
    client.post("/items/new", data={
        "name": "Dell Laptop",
        "category": "Laptop",
        "asset_tag": "LAP-001",
        "condition": "Good",
    })
    return get_row(app, 1)


def get_row(app, item_id):
    with app.app_context():
        return get_db().execute(
            "SELECT * FROM equipment_item WHERE id = ?", (item_id,)
        ).fetchone()


def retire(client, item):
    return client.post(f"/items/{item['id']}/retire")


def test_retire_sets_status_to_retired(client, app, item):
    assert item["status"] == "Available"

    response = retire(client, item)

    assert response.status_code == 302
    assert get_row(app, item["id"])["status"] == "Retired"


def test_retired_item_still_exists(client, app, item):
    retire(client, item)

    row = get_row(app, item["id"])
    assert row is not None
    assert row["name"] == "Dell Laptop"
    assert row["asset_tag"] == "LAP-001"

    response = client.get("/items/")
    assert b"Dell Laptop" in response.data
    assert b'class="badge-retired">Retired</span>' in response.data


def test_opening_edit_form_for_retired_item_is_rejected(client, item):
    retire(client, item)

    response = client.get(f"/items/{item['id']}/edit", follow_redirects=True)

    assert response.request.path == "/items/"
    assert b"Retired items can&#39;t be edited." in response.data
    assert b"Save changes" not in response.data


def test_submitting_edit_for_retired_item_is_rejected(client, app, item):
    retire(client, item)
    before = get_row(app, item["id"])

    response = client.post(
        f"/items/{item['id']}/edit",
        data={"name": "Changed", "category": "Changed",
              "asset_tag": "NEW-001", "condition": "Fair"},
        follow_redirects=True,
    )

    assert response.request.path == "/items/"
    assert b"Retired items can&#39;t be edited." in response.data
    assert dict(get_row(app, item["id"])) == dict(before)


def test_retired_row_has_no_edit_or_retire_buttons(client, item):
    retire(client, item)

    response = client.get("/items/")

    assert f"/items/{item['id']}/edit".encode() not in response.data
    assert f"/items/{item['id']}/retire".encode() not in response.data


def test_retiring_already_retired_item_changes_nothing(client, app, item):
    retire(client, item)

    response = client.post(f"/items/{item['id']}/retire", follow_redirects=True)

    assert b"is already retired." in response.data
    assert get_row(app, item["id"])["status"] == "Retired"


def test_retire_missing_item_returns_404(client):
    assert client.post("/items/9999/retire").status_code == 404


def test_retire_requires_post(client, app, item):
    response = client.get(f"/items/{item['id']}/retire")

    assert response.status_code == 405
    assert get_row(app, item["id"])["status"] == "Available"


# --- Reactivate ------------------------------------------------------------

def reactivate(client, item, **kwargs):
    return client.post(f"/items/{item['id']}/reactivate", **kwargs)


def test_retired_row_has_reactivate_button(client, item):
    retire(client, item)

    response = client.get("/items/")

    assert f"/items/{item['id']}/reactivate".encode() in response.data


def test_reactivate_sets_status_back_to_available(client, app, item):
    retire(client, item)
    before = get_row(app, item["id"])

    response = reactivate(client, item, follow_redirects=True)

    assert response.request.path == "/items/"
    assert b"It is available again." in response.data
    after = get_row(app, item["id"])
    assert after["status"] == "Available"
    assert {**dict(before), "status": "Available"} == dict(after)


def test_reactivated_item_can_be_edited_again(client, app, item):
    retire(client, item)
    reactivate(client, item)

    response = client.post(
        f"/items/{item['id']}/edit",
        data={"name": "Dell Laptop (repaired)", "category": "Laptop",
              "asset_tag": "LAP-001", "condition": "Good"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert get_row(app, item["id"])["name"] == "Dell Laptop (repaired)"


def test_reactivating_available_item_changes_nothing(client, app, item):
    response = reactivate(client, item, follow_redirects=True)

    assert b"is not retired." in response.data
    assert dict(get_row(app, item["id"])) == dict(item)


def test_reactivate_missing_item_returns_404(client):
    assert client.post("/items/9999/reactivate").status_code == 404


def test_reactivate_requires_post(client, app, item):
    retire(client, item)

    response = client.get(f"/items/{item['id']}/reactivate")

    assert response.status_code == 405
    assert get_row(app, item["id"])["status"] == "Retired"
