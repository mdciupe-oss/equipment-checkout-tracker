import pytest
from werkzeug.security import check_password_hash

from tracker.db import get_db

from conftest import TEST_PASSWORD, TEST_USERNAME, log_in


def department_id(app, name="Library"):
    with app.app_context():
        return get_db().execute(
            "SELECT id FROM department WHERE name = ?", (name,)
        ).fetchone()["id"]


def register(client, app, **overrides):
    data = {
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD,
        "confirm_password": TEST_PASSWORD,
        "department_id": str(department_id(app)),
    }
    data.update(overrides)
    return client.post("/auth/register", data=data)


def user_row(app, username=TEST_USERNAME):
    with app.app_context():
        return get_db().execute(
            "SELECT * FROM user_account WHERE username = ?", (username,)
        ).fetchone()


def user_count(app):
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) FROM user_account").fetchone()[0]


# --- Logged-out visitors -----------------------------------------------------

@pytest.mark.parametrize("method, path", [
    ("GET", "/items/"),
    ("GET", "/items/new"),
    ("POST", "/items/new"),
    ("GET", "/items/1/edit"),
    ("POST", "/items/1/edit"),
    ("POST", "/items/1/retire"),
    ("POST", "/items/1/reactivate"),
])
def test_logged_out_visitor_is_redirected_to_login(client, method, path):
    response = client.open(path, method=method)

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/auth/login")


def test_logged_out_visitor_cannot_add_item(client, app):
    client.post("/items/new", data={
        "name": "Laptop", "category": "Laptop", "asset_tag": "LAP-001", "condition": "Good",
    })

    with app.app_context():
        count = get_db().execute("SELECT COUNT(*) FROM equipment_item").fetchone()[0]
    assert count == 0


def test_home_page_is_public(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Log in" in response.data


# --- Register and log in -------------------------------------------------------

def test_register_then_log_in(client, app):
    response = register(client, app)
    assert response.status_code == 302
    assert response.headers["Location"] == "/auth/login"

    response = log_in(client, follow_redirects=True)
    assert response.status_code == 200
    assert response.request.path == "/items/"
    assert b"alice (Library)" in response.data
    assert b"Log out" in response.data


def test_new_user_gets_default_role_active_flag_and_department(client, app):
    register(client, app)

    row = user_row(app)
    assert row["role"] == "user"
    assert row["is_active"] == 1
    assert row["department_id"] == department_id(app)


def test_three_sample_departments_exist(client, app):
    with app.app_context():
        names = [r["name"] for r in get_db().execute("SELECT name FROM department")]
    assert sorted(names) == ["Computer Science", "Facilities", "Library"]


def test_register_page_lists_departments(client):
    response = client.get("/auth/register")

    for name in (b"Computer Science", b"Library", b"Facilities"):
        assert name in response.data


def test_log_out(logged_in, app):
    client = logged_in

    response = client.post("/auth/logout", follow_redirects=True)

    assert b"You have been logged out." in response.data
    assert client.get("/items/").status_code == 302


def test_logout_requires_post(logged_in):
    assert logged_in.get("/auth/logout").status_code == 405


def test_login_returns_to_requested_page(client, make_user):
    make_user()

    redirect = client.get("/items/new")
    login_url = redirect.headers["Location"]
    assert "next=/items/new" in login_url

    response = client.post(login_url, data={
        "username": TEST_USERNAME, "password": TEST_PASSWORD,
    })
    assert response.headers["Location"] == "/items/new"


@pytest.mark.parametrize("evil_next", ["https://evil.example/", "//evil.example/", "/\\evil.example"])
def test_login_ignores_offsite_next(client, make_user, evil_next):
    make_user()

    response = client.post("/auth/login", data={
        "username": TEST_USERNAME, "password": TEST_PASSWORD, "next": evil_next,
    })

    assert response.headers["Location"] == "/items/"


# --- Wrong password and other login failures ----------------------------------

def test_wrong_password_is_rejected(client, make_user):
    make_user()

    response = log_in(client, password="wrong-password")

    assert response.status_code == 401
    assert b"Incorrect username or password." in response.data
    assert client.get("/items/").status_code == 302  # still logged out


def test_unknown_username_gets_same_message(client):
    response = log_in(client, username="nobody")

    assert response.status_code == 401
    assert b"Incorrect username or password." in response.data


def test_inactive_user_cannot_log_in(client, make_user):
    make_user(is_active=False)

    response = log_in(client)

    assert response.status_code == 401
    assert b"This account is inactive." in response.data
    assert client.get("/items/").status_code == 302


def test_user_deactivated_while_logged_in_is_logged_out(logged_in, app):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE user_account SET is_active = 0 WHERE username = ?", (TEST_USERNAME,))
        db.commit()

    assert logged_in.get("/items/").status_code == 302


# --- Password storage -------------------------------------------------------

def test_stored_password_is_hashed_not_plain_text(client, app):
    register(client, app)

    stored = user_row(app)["password_hash"]
    assert stored != TEST_PASSWORD
    assert TEST_PASSWORD not in stored
    assert stored.startswith(("scrypt:", "pbkdf2:"))
    assert check_password_hash(stored, TEST_PASSWORD)


def test_same_password_gives_different_hashes(client, app):
    register(client, app, username="alice")
    register(client, app, username="bob")

    assert user_row(app, "alice")["password_hash"] != user_row(app, "bob")["password_hash"]


# --- Registration rules -------------------------------------------------------

@pytest.mark.parametrize("overrides, message", [
    pytest.param({"username": ""}, b"Username is required.",
                 id="missing-username"),
    pytest.param({"username": "   "}, b"Username is required.",
                 id="blank-username"),
    pytest.param({"password": "short", "confirm_password": "short"}, b"at least 8 characters.",
                 id="password-too-short"),
    pytest.param({"confirm_password": "something-else"}, b"Passwords do not match.",
                 id="passwords-do-not-match"),
    pytest.param({"department_id": ""}, b"Choose a department from the list.",
                 id="missing-department"),
    pytest.param({"department_id": "9999"}, b"Choose a department from the list.",
                 id="unknown-department"),
])
def test_invalid_registration_is_rejected(client, app, overrides, message):
    response = register(client, app, **overrides)

    assert response.status_code == 400
    assert message in response.data
    assert user_count(app) == 0


@pytest.mark.parametrize("duplicate", ["alice", "ALICE"])
def test_duplicate_username_is_rejected(client, app, duplicate):
    register(client, app)

    response = register(client, app, username=duplicate)

    assert response.status_code == 400
    assert b"is already taken." in response.data
    assert user_count(app) == 1


def test_rejected_registration_does_not_echo_password(client, app):
    response = register(client, app, confirm_password="something-else")

    assert TEST_PASSWORD.encode() not in response.data
