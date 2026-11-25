import os

from flask import Flask, render_template

from . import auth, db, items

SECRET_KEY_ENV_VAR = "TRACKER_SECRET_KEY"

MISSING_SECRET_MESSAGE = f"""No secret key configured.
Set the {SECRET_KEY_ENV_VAR} environment variable, or create instance/config.py with:
    SECRET_KEY = "<a long random string>"
See "Run it locally" in the README for a one-line command that creates it.
"""


def create_app(test_config=None, instance_path=None):
    """Build and configure the Flask app.

    The secret key comes from, in order of precedence:
    test_config, the TRACKER_SECRET_KEY environment variable,
    then instance/config.py (which git ignores). It is never set in code.
    """
    app = Flask(__name__, instance_path=instance_path, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "tracker.sqlite"),
    )
    app.config.from_pyfile("config.py", silent=True)

    if os.environ.get(SECRET_KEY_ENV_VAR):
        app.config["SECRET_KEY"] = os.environ[SECRET_KEY_ENV_VAR]

    if test_config is not None:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(MISSING_SECRET_MESSAGE)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(items.bp)

    @app.route("/")
    def home():
        return render_template("home.html")

    return app
