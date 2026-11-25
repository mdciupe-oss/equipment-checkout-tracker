import sqlite3

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .auth import require_login_for_blueprint
from .db import get_db

bp = Blueprint("items", __name__, url_prefix="/items")
require_login_for_blueprint(bp)

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


def get_item(item_id):
    return get_db().execute(
        "SELECT id, name, category, asset_tag, condition, status"
        " FROM equipment_item WHERE id = ?",
        (item_id,),
    ).fetchone()


def asset_tag_exists(asset_tag, exclude_id=None):
    """True if another item uses this tag. exclude_id skips the item being edited."""
    row = get_db().execute(
        "SELECT 1 FROM equipment_item WHERE asset_tag = ? AND id IS NOT ?",
        (asset_tag, exclude_id),
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


def update_item(item_id, name, category, asset_tag, condition):
    db = get_db()
    db.execute(
        "UPDATE equipment_item SET name = ?, category = ?, asset_tag = ?, condition = ?"
        " WHERE id = ?",
        (name, category, asset_tag, condition, item_id),
    )
    db.commit()


def set_status(item_id, status):
    db = get_db()
    db.execute("UPDATE equipment_item SET status = ? WHERE id = ?", (status, item_id))
    db.commit()


def get_item_or_404(item_id):
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
