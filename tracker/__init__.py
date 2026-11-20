import os

from flask import Flask, render_template

from . import db


def create_app(test_config=None):
    """Build and configure the Flask app."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY="dev",  # replace with a real secret before deploying
        DATABASE=os.path.join(app.instance_path, "tracker.sqlite"),
    )

    if test_config is not None:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)

    @app.route("/")
    def home():
        return render_template("home.html")

    return app
