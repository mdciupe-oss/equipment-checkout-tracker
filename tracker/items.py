import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .db import get_db

bp = Blueprint("items", __name__, url_prefix="/items")

CONDITIONS = ["Good", "Fair", "Needs repair"]
STATUS_AVAILABLE = "Available"
STATUS_RETIRED = "Retired"
STATUSES = [STATUS_AVAILABLE, STATUS_RETIRED]


# --- Data access -----------------------------------------------------------
# All item queries live here, so adding a department filter later is local.

def list_items():
    return get_db().execute(
        "SELECT id, name, category, asset_tag, condition, status"
        " FROM equipment_item ORDER BY name COLLATE NOCASE"
    ).fetchall()


def asset_tag_exists(asset_tag):
    row = get_db().execute(
        "SELECT 1 FROM equipment_item WHERE asset_tag = ?", (asset_tag,)
    ).fetchone()
    return row is not None


def insert_item(name, category, asset_tag, condition):
    db = get_db()
    db.execute(
        "INSERT INTO equipment_item (name, category, asset_tag, condition, status)"
        " VALUES (?, ?, ?, ?, ?)",
        (name, category, asset_tag, condition, STATUS_AVAILABLE),
    )
    db.commit()


# --- Validation ------------------------------------------------------------

def clean_item_form(form):
    """Return the submitted fields with surrounding whitespace removed."""
    return {
        "name": form.get("name", "").strip(),
        "category": form.get("category", "").strip(),
        "asset_tag": form.get("asset_tag", "").strip(),
        "condition": form.get("condition", "").strip(),
    }


def validate_item(data):
    """Return a dict of {field: error message}. Empty dict means valid."""
    errors = {}
    if not data["name"]:
        errors["name"] = "Name is required."
    if not data["category"]:
        errors["category"] = "Category is required."
    if not data["asset_tag"]:
        errors["asset_tag"] = "Asset tag is required."
    elif asset_tag_exists(data["asset_tag"]):
        errors["asset_tag"] = f"Asset tag \"{data['asset_tag']}\" is already in use."
    if data["condition"] not in CONDITIONS:
        errors["condition"] = "Choose a condition from the list."
    return errors


# --- Views -----------------------------------------------------------------

@bp.route("/")
def index():
    return render_template("items/index.html", items=list_items())


@bp.route("/new", methods=["GET", "POST"])
def new():
    data = {"name": "", "category": "", "asset_tag": "", "condition": CONDITIONS[0]}
    errors = {}

    if request.method == "POST":
        data = clean_item_form(request.form)
        errors = validate_item(data)
        if not errors:
            try:
                insert_item(**data)
            except sqlite3.IntegrityError:
                # Backstop in case another request added the same tag meanwhile.
                errors["asset_tag"] = f"Asset tag \"{data['asset_tag']}\" is already in use."
            else:
                flash(f"Added \"{data['name']}\".")
                return redirect(url_for("items.index"))

    status_code = 400 if errors else 200
    return render_template(
        "items/new.html", data=data, errors=errors, conditions=CONDITIONS
    ), status_code
