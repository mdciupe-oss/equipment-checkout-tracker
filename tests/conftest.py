import pytest
from werkzeug.security import generate_password_hash

from tracker import create_app
from tracker.db import get_db

TEST_USERNAME = "alice"
TEST_PASSWORD = "correct-horse-battery"


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Never read the developer's real secret or database during tests.
    monkeypatch.delenv("TRACKER_SECRET_KEY", raising=False)
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-only-not-a-real-secret",
            "DATABASE": str(tmp_path / "test.sqlite"),
        },
        instance_path=str(tmp_path / "instance"),
    )
    yield app


@pytest.fixture
def client(app):
    """A browser that is NOT logged in."""
    return app.test_client()


@pytest.fixture
def make_user(app):
    """Create a user directly in the database; returns the new user's id."""
    def _make_user(username=TEST_USERNAME, password=TEST_PASSWORD,
                   department="Library", is_active=True):
        with app.app_context():
            db = get_db()
            dept_id = db.execute(
                "SELECT id FROM department WHERE name = ?", (department,)
            ).fetchone()["id"]
            cur = db.execute(
                "INSERT INTO user_account (username, password_hash, department_id, is_active)"
                " VALUES (?, ?, ?, ?)",
                (username, generate_password_hash(password), dept_id, int(is_active)),
            )
            db.commit()
            return cur.lastrowid
    return _make_user


def log_in(client, username=TEST_USERNAME, password=TEST_PASSWORD, **kwargs):
    return client.post(
        "/auth/login", data={"username": username, "password": password}, **kwargs
    )


@pytest.fixture
def logged_in(client, make_user):
    """Log the test client in as a regular user.

    Use in a test module with: pytestmark = pytest.mark.usefixtures("logged_in")
    """
    make_user()
    response = log_in(client)
    assert response.status_code == 302, "test login failed"
    return client
