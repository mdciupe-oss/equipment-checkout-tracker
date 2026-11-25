"""Migration 1: existing equipment gets a department, nothing is lost.

Each test builds a database with an OLD table structure (copied exactly from
earlier commits), fills it, then starts the real app on it, which is when
migrations run.
"""
import sqlite3

import pytest
from werkzeug.security import generate_password_hash

from tracker import create_app
from tracker.migrations import LATEST_VERSION, run_migrations

# --- Old structures, frozen exactly as they were committed -------------------

OLD_EQUIPMENT_ITEM = """
CREATE TABLE IF NOT EXISTS equipment_item (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,
    asset_tag   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    condition   TEXT NOT NULL DEFAULT 'Good',
    status      TEXT NOT NULL DEFAULT 'Available',
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

# As of commit 62b7187 (after login was added): the shape of the real database.
OLD_WITH_LOGIN = OLD_EQUIPMENT_ITEM + """
CREATE TABLE IF NOT EXISTS department (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE COLLATE NOCASE
);
INSERT INTO department (name)
SELECT name FROM (
    SELECT 'Computer Science' AS name
    UNION ALL SELECT 'Library'
    UNION ALL SELECT 'Facilities'
)
WHERE NOT EXISTS (SELECT 1 FROM department);
CREATE TABLE IF NOT EXISTS user_account (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash  TEXT NOT NULL,
    department_id  INTEGER NOT NULL REFERENCES department (id),
    role           TEXT NOT NULL DEFAULT 'user',
    is_active      INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

OLD_SHAPES = {
    "before-login": OLD_EQUIPMENT_ITEM,  # equipment only, no departments yet
    "after-login": OLD_WITH_LOGIN,
}

# Varied values, including a retired item, a gap in the ids and fixed dates.
OLD_ITEMS = [
    (1, "Dell Laptop", "Laptop", "LAP-001", "Good", "Available", "2026-11-01 09:30:00"),
    (2, "Canon Camera", "Camera", "CAM-001", "Needs repair", "Available", "2026-11-02 10:00:00"),
    (5, "Old Projector", "Projector", "PRJ-001", "Fair", "Retired", "2026-11-03 11:15:00"),
]
OLD_COLUMNS = "id, name, category, asset_tag, condition, status, created_at"


def build_old_database(path, shape):
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SHAPES[shape])
    conn.executemany(f"INSERT INTO equipment_item ({OLD_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     OLD_ITEMS)
    # Pretend item 7 was added and deleted at some point: the id counter is at 7.
    conn.execute("UPDATE sqlite_sequence SET seq = 7 WHERE name = 'equipment_item'")
    if shape == "after-login":
        conn.execute(
            "INSERT INTO user_account (username, password_hash, department_id)"
            " VALUES ('carol', ?, 1)",
            (generate_password_hash("carols-password"),),
        )
    conn.commit()
    conn.close()


def start_app(tmp_path, db_path):
    return create_app(
        {"TESTING": True, "SECRET_KEY": "test-only", "DATABASE": str(db_path),
         "WTF_CSRF_ENABLED": False},
        instance_path=str(tmp_path / "instance"),
    )


def query(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def old_values(db_path):
    return query(db_path, f"SELECT {OLD_COLUMNS} FROM equipment_item ORDER BY id")


def everything(db_path):
    """Every row of every table, plus the version: to prove 'nothing changed'."""
    tables = [r[0] for r in query(db_path, "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    snapshot = {t: query(db_path, f"SELECT * FROM {t} ORDER BY 1") for t in tables}
    snapshot["user_version"] = query(db_path, "PRAGMA user_version")
    return snapshot


def backups(tmp_path):
    return sorted(tmp_path.glob("*.before-migration-1-*.sqlite"))


@pytest.fixture(params=list(OLD_SHAPES))
def old_db(request, tmp_path, monkeypatch):
    monkeypatch.delenv("TRACKER_SECRET_KEY", raising=False)
    path = tmp_path / "tracker.sqlite"
    build_old_database(path, request.param)
    return path


# --- The migration --------------------------------------------------------

def test_existing_items_are_kept_with_department_assigned(tmp_path, old_db):
    start_app(tmp_path, old_db)

    assert old_values(old_db) == OLD_ITEMS
    departments = query(
        old_db,
        "SELECT d.name FROM equipment_item e JOIN department d ON d.id = e.department_id",
    )
    assert departments == [("Computer Science",)] * len(OLD_ITEMS)
    assert query(old_db, "PRAGMA user_version") == [(LATEST_VERSION,)]


def test_department_is_required_after_migration(tmp_path, old_db):
    start_app(tmp_path, old_db)

    columns = {r[1]: r for r in query(old_db, "PRAGMA table_info(equipment_item)")}
    assert columns["department_id"][3] == 1  # NOT NULL
    with pytest.raises(sqlite3.IntegrityError):
        query(old_db, "INSERT INTO equipment_item (name, category, asset_tag) VALUES ('x', 'y', 'Z-1')")


def test_migration_makes_backup_of_old_file(tmp_path, old_db):
    start_app(tmp_path, old_db)

    [backup] = backups(tmp_path)
    assert old_values(backup) == OLD_ITEMS
    assert query(backup, "PRAGMA user_version") == [(0,)]
    assert "department_id" not in [r[1] for r in query(backup, "PRAGMA table_info(equipment_item)")]


def test_second_run_changes_nothing(tmp_path, old_db):
    start_app(tmp_path, old_db)
    after_first = everything(old_db)

    start_app(tmp_path, old_db)

    assert everything(old_db) == after_first
    assert len(backups(tmp_path)) == 1  # no second backup
    assert run_migrations(str(old_db)) == []  # nothing pending


def test_ids_of_deleted_items_are_not_reused(tmp_path, old_db):
    start_app(tmp_path, old_db)

    conn = sqlite3.connect(old_db)
    conn.execute(
        "INSERT INTO equipment_item (name, category, asset_tag, department_id)"
        " VALUES ('New', 'Misc', 'NEW-1', 1)"
    )
    conn.commit()
    conn.close()

    # The old id counter was at 7, so the next item is 8 (not 6).
    assert query(old_db, "SELECT id FROM equipment_item WHERE asset_tag = 'NEW-1'") == [(8,)]


def test_existing_user_sees_migrated_items(tmp_path, monkeypatch):
    monkeypatch.delenv("TRACKER_SECRET_KEY", raising=False)
    path = tmp_path / "tracker.sqlite"
    build_old_database(path, "after-login")
    client = start_app(tmp_path, path).test_client()

    client.post("/auth/login", data={"username": "carol", "password": "carols-password"})
    page = client.get("/items/").data

    for item in OLD_ITEMS:
        assert item[1].encode() in page


def test_users_are_kept(tmp_path, monkeypatch):
    monkeypatch.delenv("TRACKER_SECRET_KEY", raising=False)
    path = tmp_path / "tracker.sqlite"
    build_old_database(path, "after-login")
    before = query(path, "SELECT * FROM user_account")

    start_app(tmp_path, path)

    assert query(path, "SELECT * FROM user_account") == before


# --- New databases --------------------------------------------------------

def test_new_database_needs_no_backup_and_is_up_to_date(tmp_path, monkeypatch):
    monkeypatch.delenv("TRACKER_SECRET_KEY", raising=False)
    path = tmp_path / "tracker.sqlite"

    start_app(tmp_path, path)

    assert query(path, "PRAGMA user_version") == [(LATEST_VERSION,)]
    assert backups(tmp_path) == []
    assert run_migrations(str(path)) == []


def structure(db_path):
    """Columns, indexes and references of every table (ignores formatting)."""
    result = {}
    tables = [r[0] for r in query(db_path, "SELECT name FROM sqlite_master WHERE type='table'"
                                           " AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for t in tables:
        indexes = []
        for idx in query(db_path, f"PRAGMA index_list({t})"):
            cols = tuple(r[2] for r in query(db_path, f"PRAGMA index_info({idx[1]})"))
            indexes.append((idx[2], cols))  # (unique?, columns)
        result[t] = {
            "columns": query(db_path, f"PRAGMA table_info({t})"),
            "indexes": sorted(indexes),
            "references": query(db_path, f"PRAGMA foreign_key_list({t})"),
        }
    return result


def test_migrated_database_matches_new_database(tmp_path, old_db):
    new_path = tmp_path / "fresh.sqlite"
    start_app(tmp_path, new_path)
    start_app(tmp_path, old_db)

    assert structure(old_db) == structure(new_path)
