-- The current database structure. Every statement here is safe to run on an
-- existing database: tables are only created if missing, nothing is altered
-- or deleted. Databases created by an older version are brought up to date
-- by tracker/migrations.py, which runs right after this file.
-- Allowed values for condition, status and role are enforced in Python,
-- so new values can be added without rebuilding a table.

CREATE TABLE IF NOT EXISTS department (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE COLLATE NOCASE
);

-- Sample departments, added only when the table is empty so that later
-- renames or removals by an admin are not undone on the next start.
INSERT INTO department (name)
SELECT name FROM (
    SELECT 'Computer Science' AS name
    UNION ALL SELECT 'Library'
    UNION ALL SELECT 'Facilities'
)
WHERE NOT EXISTS (SELECT 1 FROM department);

-- Keep in step with migration 1 in tracker/migrations.py.
CREATE TABLE IF NOT EXISTS equipment_item (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    category       TEXT NOT NULL,
    -- Unique across ALL departments, not per department.
    asset_tag      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    condition      TEXT NOT NULL DEFAULT 'Good',
    status         TEXT NOT NULL DEFAULT 'Available',
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    department_id  INTEGER NOT NULL REFERENCES department (id)
);

CREATE TABLE IF NOT EXISTS user_account (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash  TEXT NOT NULL,
    department_id  INTEGER NOT NULL REFERENCES department (id),
    role           TEXT NOT NULL DEFAULT 'user',
    is_active      INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
