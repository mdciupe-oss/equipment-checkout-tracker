"""CSRF protection, tested with the token check switched ON.

This module overrides the shared `app` fixture, so the shared `client` and
`make_user` fixtures from conftest.py use the protected app automatically.
"""
import re

import pytest

from tracker import create_app
from tracker.db import get_db

from conftest import TEST_PASSWORD, TEST_USERNAME

CSRF_REJECTED = b"This form has expired or was sent from another site."
TOKEN_RE = re.compile(rb'name="csrf_token" value="([^"]+)"')
POST_FORM_RE = re.compile(rb'<form[^>]*method="post"[^>]*>(.*?)</form>', re.S | re.I)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("TRACKER_SECRET_KEY", raising=False)
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-only-not-a-real-secret",
            "DATABASE": str(tmp_path / "test.sqlite"),
            "WTF_CSRF_ENABLED": True,
        },
        instance_path=str(tmp_path / "instance"),
    )


def token_from(client, path):
    """Load a page the way a browser would and read its CSRF token."""
    response = client.get(path)
    match = TOKEN_RE.search(response.data)
    assert match, f"no CSRF token on {path}"
    return match.group(1).decode()


def log_in_with_token(client):
    return client.post("/auth/login", data={
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD,
        "csrf_token": token_from(client, "/auth/login"),
    })


def add_item_row(app, asset_tag="LAP-001", status="Available"):
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO equipment_item (name, category, asset_tag, status)"
            " VALUES ('Dell Laptop', 'Laptop', ?, ?)",
            (asset_tag, status),
        )
        db.commit()


def item_rows(app):
    with app.app_context():
        return [dict(r) for r in get_db().execute("SELECT * FROM equipment_item ORDER BY id")]


def user_count(app):
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) FROM user_account").fetchone()[0]


@pytest.fixture
def logged_in(client, make_user):
    make_user()
    assert log_in_with_token(client).status_code == 302
    return client


def is_logged_in(client):
    return client.get("/items/").status_code == 200


# --- Every action is rejected without a token ---------------------------------

@pytest.mark.parametrize("path, data", [
    pytest.param("/items/new",
                 {"name": "X", "category": "Y", "asset_tag": "NEW-1", "condition": "Good"},
                 id="add-item"),
    pytest.param("/items/1/edit",
                 {"name": "Changed", "category": "Y", "asset_tag": "LAP-001", "condition": "Fair"},
                 id="edit-item"),
    pytest.param("/items/1/retire", {}, id="retire"),
    pytest.param("/items/2/reactivate", {}, id="reactivate"),
])
def test_item_actions_without_token_are_rejected(logged_in, app, path, data):
    add_item_row(app, "LAP-001")
    add_item_row(app, "LAP-002", status="Retired")
    before = item_rows(app)

    response = logged_in.post(path, data=data)

    assert response.status_code == 400
    assert CSRF_REJECTED in response.data
    assert item_rows(app) == before


def test_logout_without_token_is_rejected(logged_in):
    response = logged_in.post("/auth/logout")

    assert response.status_code == 400
    assert is_logged_in(logged_in)


def test_login_without_token_is_rejected(client, make_user):
    make_user()

    response = client.post("/auth/login", data={
        "username": TEST_USERNAME, "password": TEST_PASSWORD,
    })

    assert response.status_code == 400
    assert not is_logged_in(client)


def test_register_without_token_is_rejected(client, app):
    response = client.post("/auth/register", data={
        "username": "bob", "password": TEST_PASSWORD,
        "confirm_password": TEST_PASSWORD, "department_id": "1",
    })

    assert response.status_code == 400
    assert user_count(app) == 0


def test_token_from_another_session_is_rejected(app, make_user):
    make_user()
    attacker = app.test_client()
    victim = app.test_client()
    attacker_token = token_from(attacker, "/auth/login")
    victim.get("/auth/login")  # the victim has their own session and token

    response = victim.post("/auth/login", data={
        "username": TEST_USERNAME, "password": TEST_PASSWORD,
        "csrf_token": attacker_token,
    })

    assert response.status_code == 400
    assert not is_logged_in(victim)


# --- With a valid token, things work ---------------------------------------

def test_login_with_token_works(client, make_user):
    make_user()

    response = log_in_with_token(client)

    assert response.status_code == 302
    assert is_logged_in(client)


def test_add_item_with_token_works(logged_in, app):
    response = logged_in.post("/items/new", data={
        "name": "Dell Laptop", "category": "Laptop",
        "asset_tag": "LAP-001", "condition": "Good",
        "csrf_token": token_from(logged_in, "/items/new"),
    })

    assert response.status_code == 302
    assert len(item_rows(app)) == 1


# --- No form is missing its token -------------------------------------------------

def assert_every_post_form_has_token(response, path):
    forms = POST_FORM_RE.findall(response.data)
    assert forms, f"expected at least one POST form on {path}"
    for form in forms:
        assert b'name="csrf_token"' in form, f"a POST form on {path} has no CSRF token"


@pytest.mark.parametrize("path", ["/auth/login", "/auth/register"])
def test_logged_out_pages_have_token_in_every_form(client, path):
    assert_every_post_form_has_token(client.get(path), path)


@pytest.mark.parametrize("path", ["/", "/items/", "/items/new", "/items/1/edit"])
def test_logged_in_pages_have_token_in_every_form(logged_in, app, path):
    # One available and one retired item, so both Retire and Reactivate forms render.
    add_item_row(app, "LAP-001")
    add_item_row(app, "LAP-002", status="Retired")

    assert_every_post_form_has_token(logged_in.get(path), path)
