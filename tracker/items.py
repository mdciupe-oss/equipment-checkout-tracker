import sqlite3

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .auth import require_login_for_blueprint
from .db import get_db

bp = Blueprint("items", __name__, url_prefix="/items")
require_login_for_blueprint(bp)

CONDITIONS = ["Good", "Fair", "Needs repair"]
STATUS_AVAILABLE = "Available"
STATUS_RETIRED = "Retired"
STATUSES = [STATUS_AVAILABLE, STATUS_RETIRED]


# --- Access rule -----------------------------------------------------------

def item_scope():
    """THE rule for which equipment the current user may see and change.

    Returns an SQL condition and its parameters. Every equipment query below
    uses it, so this is the only place to change when admins are added, e.g.:
        if g.user["role"] == ROLE_ADMIN:
            return "1 = 1", []
    """
    return "department_id = ?", [g.user["department_id"]]


# --- Data access -----------------------------------------------------------

ITEM_COLUMNS = "id, name, category, asset_tag, condition, status, department_id"


def list_items():
    condition, params = item_scope()
    return get_db().execute(
        f"SELECT {ITEM_COLUMNS} FROM equipment_item"
        f" WHERE {condition} ORDER BY name COLLATE NOCASE",
        params,
    ).fetchall()


def get_item(item_id):
    """The item, or None if it doesn't exist OR the user may not access it."""
    condition, params = item_scope()
    return get_db().execute(
        f"SELECT {ITEM_COLUMNS} FROM equipment_item WHERE id = ? AND {condition}",
        [item_id, *params],
    ).fetchone()


def asset_tag_exists(asset_tag, exclude_id=None):
    """True if another item uses this tag. exclude_id skips the item being edited.

    Deliberately NOT limited by item_scope(): asset tags are unique across
    all departments.
    """
    row = get_db().execute(
        "SELECT 1 FROM equipment_item WHERE asset_tag = ? AND id IS NOT ?",
        (asset_tag, exclude_id),
    ).fetchone()
    return row is not None


def insert_item(name, category, asset_tag, condition):
    # New items always belong to the logged-in user's department.
    db = get_db()
    db.execute(
        "INSERT INTO equipment_item"
        " (name, category, asset_tag, condition, status, department_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (name, category, asset_tag, condition, STATUS_AVAILABLE, g.user["department_id"]),
    )
    db.commit()


def update_item(item_id, name, category, asset_tag, condition):
    # The scope is applied again here as a second line of defence.
    scope, params = item_scope()
    db = get_db()
    db.execute(
        "UPDATE equipment_item SET name = ?, category = ?, asset_tag = ?, condition = ?"
        f" WHERE id = ? AND {scope}",
        [name, category, asset_tag, condition, item_id, *params],
    )
    db.commit()


def set_status(item_id, status):
    scope, params = item_scope()
    db = get_db()
    db.execute(
        f"UPDATE equipment_item SET status = ? WHERE id = ? AND {scope}",
        [status, item_id, *params],
    )
    db.commit()


def get_item_or_404(item_id):
    """Every view that works on one item starts here.

    Another department's item gives the same 404 as a missing one, so users
    can't discover which item ids exist elsewhere.
    """
    item = get_item(item_id)
    if item is None:
        abort(404)
    return item


# --- Validation ------------------------------------------------------------

def clean_item_form(form):
    """Return the submitted fields with surrounding whitespace removed."""
    return {
        "name": form.get("name", "").strip(),
        "category": form.get("category", "").strip(),
        "asset_tag": form.get("asset_tag", "").strip(),
        "condition": form.get("condition", "").strip(),
    }


def duplicate_tag_message(asset_tag):
    return f"Asset tag \"{asset_tag}\" is already in use."


def validate_item(data, item_id=None):
    """Return a dict of {field: error message}. Empty dict means valid.

    Pass item_id when editing so the item's own asset tag isn't a duplicate.
    """
    errors = {}
    if not data["name"]:
        errors["name"] = "Name is required."
    if not data["category"]:
        errors["category"] = "Category is required."
    if not data["asset_tag"]:
        errors["asset_tag"] = "Asset tag is required."
    elif asset_tag_exists(data["asset_tag"], exclude_id=item_id):
        errors["asset_tag"] = duplicate_tag_message(data["asset_tag"])
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
                errors["asset_tag"] = duplicate_tag_message(data["asset_tag"])
            else:
                flash(f"Added \"{data['name']}\".")
                return redirect(url_for("items.index"))

    return render_form(data, errors, heading="Add an item", submit_label="Add item")


@bp.route("/<int:item_id>/edit", methods=["GET", "POST"])
def edit(item_id):
    item = get_item_or_404(item_id)
    if item["status"] == STATUS_RETIRED:
        flash(f"\"{item['name']}\" is retired. Retired items can't be edited.")
        return redirect(url_for("items.index"))

    data = {key: item[key] for key in ("name", "category", "asset_tag", "condition")}
    errors = {}

    if request.method == "POST":
        data = clean_item_form(request.form)
        errors = validate_item(data, item_id=item_id)
        if not errors:
            try:
                update_item(item_id, **data)
            except sqlite3.IntegrityError:
                errors["asset_tag"] = duplicate_tag_message(data["asset_tag"])
            else:
                flash(f"Saved \"{data['name']}\".")
                return redirect(url_for("items.index"))

    return render_form(data, errors, heading="Edit item", submit_label="Save changes")


@bp.route("/<int:item_id>/retire", methods=["POST"])
def retire(item_id):
    item = get_item_or_404(item_id)
    if item["status"] == STATUS_RETIRED:
        flash(f"\"{item['name']}\" is already retired.")
    else:
        set_status(item_id, STATUS_RETIRED)
        flash(f"Retired \"{item['name']}\".")
    return redirect(url_for("items.index"))


@bp.route("/<int:item_id>/reactivate", methods=["POST"])
def reactivate(item_id):
    item = get_item_or_404(item_id)
    if item["status"] != STATUS_RETIRED:
        flash(f"\"{item['name']}\" is not retired.")
    else:
        set_status(item_id, STATUS_AVAILABLE)
        flash(f"Reactivated \"{item['name']}\". It is available again.")
    return redirect(url_for("items.index"))


def render_form(data, errors, heading, submit_label):
    status_code = 400 if errors else 200
    return render_template(
        "items/form.html",
        data=data,
        errors=errors,
        conditions=CONDITIONS,
        heading=heading,
        submit_label=submit_label,
    ), status_code
