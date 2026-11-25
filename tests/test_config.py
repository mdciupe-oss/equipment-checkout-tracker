import pytest

from tracker import create_app


@pytest.fixture
def instance_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("TRACKER_SECRET_KEY", raising=False)
    path = tmp_path / "instance"
    path.mkdir()
    return path


def test_app_refuses_to_start_without_secret_key(instance_dir):
    with pytest.raises(RuntimeError, match="No secret key configured"):
        create_app(instance_path=str(instance_dir))


def test_secret_key_from_instance_config_file(instance_dir):
    (instance_dir / "config.py").write_text('SECRET_KEY = "from-file"\n')

    app = create_app(instance_path=str(instance_dir))

    assert app.config["SECRET_KEY"] == "from-file"


def test_environment_variable_overrides_config_file(instance_dir, monkeypatch):
    (instance_dir / "config.py").write_text('SECRET_KEY = "from-file"\n')
    monkeypatch.setenv("TRACKER_SECRET_KEY", "from-env")

    app = create_app(instance_path=str(instance_dir))

    assert app.config["SECRET_KEY"] == "from-env"
