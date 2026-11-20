-- Allowed values for condition and status are enforced in tracker/items.py,
-- so new values (e.g. "Checked out") can be added without rebuilding the table.

CREATE TABLE IF NOT EXISTS equipment_item (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,
    asset_tag   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    condition   TEXT NOT NULL DEFAULT 'Good',
    status      TEXT NOT NULL DEFAULT 'Available',
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
