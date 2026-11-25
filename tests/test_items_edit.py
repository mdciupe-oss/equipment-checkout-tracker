import pytest

from tracker.db import get_db

pytestmark = pytest.mark.usefixtures("logged_in")


def add_item(client, **overrides):
    item = {
        "name": "Dell Laptop",
        "category": "Laptop",
        "asset_tag": "LAP-001",
        "condition": "Good",
    }
    item.update(overrides)
    client.post("/items/new", data=item)


def get_item_row(app, asset_tag):
    with app.app_context():
        return get_db().execute(
            "SELECT * FROM equipment_item WHERE asset_tag = ?", (asset_tag,)
        ).fetchone()


@pytest.fixture
def item(client, app):
    """One saved item; returns its database row."""
    add_item(client)
    return get_item_row(app, "LAP-001")


def edit_url(item):
    return f"/items/{item['id']}/edit"


def edited(item, **overrides):
    data = {key: item[key] for key in ("name", "category", "asset_tag", "condition")}
    data.update(overrides)
    return data


def assert_unchanged(app, item):
    with app.app_context():
        row = get_db().execute(
            "SELECT * FROM equipment_item WHERE id = ?", (item["id"],)
        ).fetchone()
    assert dict(row) == dict(item)


def test_list_page_links_to_edit(client, item):
    response = client.get("/items/")

    assert edit_url(item).encode() in response.data


def test_edit_form_is_prefilled(client, item):
    response = client.get(edit_url(item))

    assert response.status_code == 200
    assert b'value="Dell Laptop"' in response.data
    assert b'value="Laptop"' in response.data
    assert b'value="LAP-001"' in response.data
    assert b'<option value="Good" selected>' in response.data


def test_edit_item_success(client, app, item):
    response = client.post(
        edit_url(item),
        data=edited(item, name="Dell Latitude", category="Laptops",
                    asset_tag="LAP-999", condition="Fair"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert response.request.path == "/items/"
    assert b"Dell Latitude" in response.data

    with app.app_context():
        row = get_db().execute(
            "SELECT * FROM equipment_item WHERE id = ?", (item["id"],)
        ).fetchone()
    assert row["name"] == "Dell Latitude"
    assert row["category"] == "Laptops"
    assert row["asset_tag"] == "LAP-999"
    assert row["condition"] == "Fair"
    assert row["status"] == "Available"


def test_edit_keeping_own_asset_tag_is_allowed(client, app, item):
    response = client.post(
        edit_url(item), data=edited(item, name="Renamed Laptop"), follow_redirects=True
    )

    assert response.status_code == 200
    assert b"is already in use." not in response.data
    row = get_item_row(app, "LAP-001")
    assert row["id"] == item["id"]
    assert row["name"] == "Renamed Laptop"


@pytest.mark.parametrize("name", ["", "   "])
def test_edit_missing_name_is_rejected(client, app, item, name):
    response = client.post(edit_url(item), data=edited(item, name=name))

    assert response.status_code == 400
    assert b"Name is required." in response.data
    assert_unchanged(app, item)


@pytest.mark.parametrize("category", ["", "   "])
def test_edit_missing_category_is_rejected(client, app, item, category):
    response = client.post(edit_url(item), data=edited(item, category=category))

    assert response.status_code == 400
    assert b"Category is required." in response.data
    assert_unchanged(app, item)


@pytest.mark.parametrize("other_tag", ["CAM-001", "cam-001"])
def test_edit_asset_tag_used_by_other_item_is_rejected(client, app, item, other_tag):
    add_item(client, name="Canon Camera", category="Camera", asset_tag="CAM-001")

    response = client.post(edit_url(item), data=edited(item, asset_tag=other_tag))

    assert response.status_code == 400
    assert b"is already in use." in response.data
    assert_unchanged(app, item)


def test_edit_missing_item_returns_404(client):
    response = client.get("/items/9999/edit")

    assert response.status_code == 404
