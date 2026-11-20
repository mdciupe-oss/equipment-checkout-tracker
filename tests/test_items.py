import pytest

from tracker.db import get_db


def valid_item(**overrides):
    item = {
        "name": "Dell Laptop",
        "category": "Laptop",
        "asset_tag": "LAP-001",
        "condition": "Good",
    }
    item.update(overrides)
    return item


def item_count(app):
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) FROM equipment_item").fetchone()[0]


def test_add_item_success(client, app):
    response = client.post("/items/new", data=valid_item(), follow_redirects=True)

    assert response.status_code == 200
    assert response.request.path == "/items/"
    assert b"Dell Laptop" in response.data
    assert b"LAP-001" in response.data

    with app.app_context():
        row = get_db().execute("SELECT * FROM equipment_item").fetchone()
    assert row["name"] == "Dell Laptop"
    assert row["category"] == "Laptop"
    assert row["asset_tag"] == "LAP-001"
    assert row["condition"] == "Good"
    assert row["status"] == "Available"


@pytest.mark.parametrize("name", ["", "   "])
def test_missing_name_is_rejected(client, app, name):
    response = client.post("/items/new", data=valid_item(name=name))

    assert response.status_code == 400
    assert b"Name is required." in response.data
    assert item_count(app) == 0


@pytest.mark.parametrize("category", ["", "   "])
def test_missing_category_is_rejected(client, app, category):
    response = client.post("/items/new", data=valid_item(category=category))

    assert response.status_code == 400
    assert b"Category is required." in response.data
    assert item_count(app) == 0


@pytest.mark.parametrize("duplicate_tag", ["LAP-001", "lap-001", " LAP-001 "])
def test_duplicate_asset_tag_is_rejected(client, app, duplicate_tag):
    client.post("/items/new", data=valid_item())
    assert item_count(app) == 1

    response = client.post(
        "/items/new", data=valid_item(name="Other Laptop", asset_tag=duplicate_tag)
    )

    assert response.status_code == 400
    assert b"is already in use." in response.data
    assert item_count(app) == 1


def test_missing_asset_tag_is_rejected(client, app):
    response = client.post("/items/new", data=valid_item(asset_tag=""))

    assert response.status_code == 400
    assert b"Asset tag is required." in response.data
    assert item_count(app) == 0


def test_rejected_form_keeps_entered_values(client):
    response = client.post("/items/new", data=valid_item(name=""))

    assert b'value="Laptop"' in response.data
    assert b'value="LAP-001"' in response.data
