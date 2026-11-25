import sqlite3

from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__, url_prefix="/auth")

ROLE_USER = "user"
ROLE_ADMIN = "admin"
ROLES = [ROLE_USER, ROLE_ADMIN]

MIN_PASSWORD_LENGTH = 8
LOGIN_FAILED_MESSAGE = "Incorrect username or password."


# --- Data access -----------------------------------------------------------

def list_departments():
    return get_db().execute(
        "SELECT id, name FROM department ORDER BY name COLLATE NOCASE"
    ).fetchall()


def department_exists(department_id):
    row = get_db().execute(
        "SELECT 1 FROM department WHERE id = ?", (department_id,)
    ).fetchone()
    return row is not None


def get_user_by_username(username):
    return get_db().execute(
        "SELECT * FROM user_account WHERE username = ?", (username,)
    ).fetchone()


def get_user(user_id):
    return get_db().execute(
        "SELECT u.id, u.username, u.department_id, u.role, u.is_active,"
        " d.name AS department_name"
        " FROM user_account u JOIN department d ON d.id = u.department_id"
        " WHERE u.id = ?",
        (user_id,),
    ).fetchone()


def create_user(username, password, department_id):
    db = get_db()
    db.execute(
        "INSERT INTO user_account (username, password_hash, department_id)"
        " VALUES (?, ?, ?)",
        (username, generate_password_hash(password), department_id),
    )
    db.commit()


# --- Login state -----------------------------------------------------------

@bp.before_app_request
def load_logged_in_user():
    """Make the current user (or None) available as g.user on every request."""
    user_id = session.get("user_id")
    g.user = get_user(user_id) if user_id is not None else None
    if g.user is not None and not g.user["is_active"]:
        # Account was deactivated after logging in: end the session.
        session.clear()
        g.user = None


def require_login_for_blueprint(blueprint):
    """Protect every route of a blueprint, including ones added later.

    Logged-out visitors are sent to the login page, which returns them to the
    page they asked for afterwards.
    """
    @blueprint.before_request
    def check_login():
        if g.user is None:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))


def is_safe_next(target):
    """Only allow redirects to paths on this site (blocks //evil.com etc.)."""
    return (
        bool(target)
        and target.startswith("/")
        and not target.startswith("//")
        and "\\" not in target
    )


# --- Validation ------------------------------------------------------------

def validate_registration(data):
    errors = {}
    if not data["username"]:
        errors["username"] = "Username is required."
    elif get_user_by_username(data["username"]) is not None:
        errors["username"] = f"Username \"{data['username']}\" is already taken."

    if len(data["password"]) < MIN_PASSWORD_LENGTH:
        errors["password"] = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    elif data["password"] != data["confirm_password"]:
        errors["confirm_password"] = "Passwords do not match."

    if not data["department_id"].isdigit() or not department_exists(int(data["department_id"])):
        errors["department_id"] = "Choose a department from the list."
    return errors


# --- Views -----------------------------------------------------------------

@bp.route("/register", methods=["GET", "POST"])
def register():
    data = {"username": "", "department_id": ""}
    errors = {}

    if request.method == "POST":
        data = {
            "username": request.form.get("username", "").strip(),
            # Passwords are not stripped: spaces may be part of them.
            "password": request.form.get("password", ""),
            "confirm_password": request.form.get("confirm_password", ""),
            "department_id": request.form.get("department_id", "").strip(),
        }
        errors = validate_registration(data)
        if not errors:
            try:
                create_user(data["username"], data["password"], int(data["department_id"]))
            except sqlite3.IntegrityError:
                errors["username"] = f"Username \"{data['username']}\" is already taken."
            else:
                flash("Account created. Please log in.")
                return redirect(url_for("auth.login"))

    return render_template(
        "auth/register.html",
        data=data,
        errors=errors,
        departments=list_departments(),
        min_length=MIN_PASSWORD_LENGTH,
    ), (400 if errors else 200)


@bp.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.values.get("next", "")
    username = ""
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_user_by_username(username)

        if user is None or not check_password_hash(user["password_hash"], password):
            error = LOGIN_FAILED_MESSAGE
        elif not user["is_active"]:
            error = "This account is inactive. Contact an administrator."
        else:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(next_url if is_safe_next(next_url) else url_for("items.index"))

    return render_template(
        "auth/login.html", username=username, error=error, next_url=next_url
    ), (401 if error else 200)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("home"))
