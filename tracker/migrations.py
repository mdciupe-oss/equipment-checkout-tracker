"""Bring databases created by older versions of the app up to date.

Each migration has a number. SQLite stores the number of the last migration
applied in the database file itself (PRAGMA user_version), so every
migration runs at most once per database, and running this module on a
database that is already up to date does nothing.

Rules for every migration:
- Never delete or change existing data, only add to it.
- Run inside one transaction: it either completes fully or changes nothing.
- Back up the database file before changing any existing table.
"""
import os
import sqlite3
from datetime import datetime


class MigrationError(Exception):
    pass


def _columns(conn, table):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# --- Migration 1: every equipment item belongs to a department -------------

# Snapshot of equipment_item as of migration 1 (matches schema.sql).
EQUIPMENT_ITEM_V1 = """
CREATE TABLE equipment_item_new (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    category       TEXT NOT NULL,
    -- Unique across ALL departments, not per department.
    asset_tag      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    condition      TEXT NOT NULL DEFAULT 'Good',
    status         TEXT NOT NULL DEFAULT 'Available',
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    department_id  INTEGER NOT NULL REFERENCES department (id)
)
"""

OLD_EQUIPMENT_COLUMNS = "id, name, category, asset_tag, condition, status, created_at"


def migration_1_changes_data(conn):
    """True if this database still has the old equipment table to rebuild."""
    return "department_id" not in _columns(conn, "equipment_item")


def migration_1_equipment_department(conn):
    """Add a required department to equipment_item.

    Existing items are assigned to the first department (lowest id).
    SQLite cannot add a required column that references another table, so
    the table is rebuilt: new table, copy every row, swap the tables.
    """
    if migration_1_changes_data(conn):
        first = conn.execute("SELECT id FROM department ORDER BY id LIMIT 1").fetchone()
        if first is None:
            raise MigrationError("No department exists to assign existing equipment to.")

        rows_before = _count(conn, "equipment_item")
        # Remember the id counter so ids of deleted items are never reused.
        seq = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'equipment_item'"
        ).fetchone()
        conn.execute(EQUIPMENT_ITEM_V1)
        conn.execute(
            f"INSERT INTO equipment_item_new ({OLD_EQUIPMENT_COLUMNS}, department_id)"
            f" SELECT {OLD_EQUIPMENT_COLUMNS}, ? FROM equipment_item",
            (first[0],),
        )
        rows_after = _count(conn, "equipment_item_new")
        if rows_after != rows_before:
            raise MigrationError(
                f"Copied {rows_after} of {rows_before} equipment items; nothing was changed."
            )
        conn.execute("DROP TABLE equipment_item")
        conn.execute("ALTER TABLE equipment_item_new RENAME TO equipment_item")
        if seq is not None:
            conn.execute(
                "UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = 'equipment_item'",
                (seq[0],),
            )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS equipment_item_department"
        " ON equipment_item (department_id)"
    )


# (version, "will it change existing data?" check, the migration itself)
MIGRATIONS = [
    (1, migration_1_changes_data, migration_1_equipment_department),
]
LATEST_VERSION = MIGRATIONS[-1][0]


# --- Runner ----------------------------------------------------------------

def backup_path_for(db_path, version):
    root, ext = os.path.splitext(db_path)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return f"{root}.before-migration-{version}-{stamp}{ext or '.sqlite'}"


def _backup(conn, db_path, version):
    path = backup_path_for(db_path, version)
    target = sqlite3.connect(path)
    try:
        conn.backup(target)
    finally:
        target.close()
    return path


def run_migrations(db_path):
    """Apply every pending migration. Returns a list of (version, backup_path).

    backup_path is None when a migration had no existing data to change.
    An empty list means the database was already up to date.
    """
    # isolation_level=None: we open and close transactions ourselves.
    conn = sqlite3.connect(db_path, isolation_level=None)
    applied = []
    try:
        # Foreign-key enforcement must be off while tables are rebuilt, and it
        # can only be switched outside a transaction. References are checked
        # explicitly below before committing.
        conn.execute("PRAGMA foreign_keys = OFF")

        for version, changes_data, migrate in MIGRATIONS:
            if conn.execute("PRAGMA user_version").fetchone()[0] >= version:
                continue

            # Back up BEFORE the transaction: SQLite can't copy a file while
            # this same connection holds it locked for writing.
            backup = _backup(conn, db_path, version) if changes_data(conn) else None

            conn.execute("BEGIN IMMEDIATE")
            try:
                migrate(conn)
                problems = conn.execute("PRAGMA foreign_key_check").fetchall()
                if problems:
                    raise MigrationError(f"Broken references after migration {version}: {problems}")
                conn.execute(f"PRAGMA user_version = {version}")
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            applied.append((version, backup))
    finally:
        conn.close()
    return applied
