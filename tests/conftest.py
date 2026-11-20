import pytest

from tracker import create_app


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.sqlite"),
    })
    yield app


@pytest.fixture
def client(app):
    return app.test_client()
