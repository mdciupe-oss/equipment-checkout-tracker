import sqlite3

from flask import current_app, g


def get_db():
    """Return a SQLite connection for the current request, opening one if needed."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(exception=None):
    """Close the connection at the end of the request, if one was opened."""
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)
