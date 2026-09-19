"""SQLite schema and connections for the data layer."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS emails (
    email_id TEXT PRIMARY KEY,
    from_addr TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'UNCLASSIFIED',
    category_conf REAL,
    category_reasons TEXT,
    decided_by TEXT,
    category_override TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    email_id TEXT NOT NULL REFERENCES emails(email_id) ON DELETE CASCADE,
    path TEXT NOT NULL UNIQUE,
    ext TEXT NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    role_hint TEXT,
    role_detected TEXT,
    convert_status TEXT,
    convert_method TEXT,
    text_path TEXT,
    meta_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_documents_email_id ON documents(email_id);
CREATE INDEX IF NOT EXISTS idx_emails_category ON emails(category);

CREATE TABLE IF NOT EXISTS extractions (
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    raw TEXT,
    normalized TEXT,
    line_no INTEGER,
    confidence REAL,
    status TEXT CHECK(status IN ('found', 'missing', 'blank')),
    PRIMARY KEY (doc_id, field)
);

CREATE TABLE IF NOT EXISTS comparisons (
    email_id TEXT PRIMARY KEY REFERENCES emails(email_id) ON DELETE CASCADE,
    status TEXT,
    review_reason TEXT,
    has_defect INTEGER,
    defect_fields TEXT,
    field_results TEXT,
    explanations TEXT,
    computed_at TEXT
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id TEXT NOT NULL REFERENCES emails(email_id) ON DELETE CASCADE,
    doc_role TEXT,
    field TEXT,
    value TEXT,
    reviewer TEXT,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stage_runs (
    email_id TEXT NOT NULL REFERENCES emails(email_id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    state TEXT NOT NULL,
    error TEXT,
    duration_ms INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (email_id, stage)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id TEXT REFERENCES emails(email_id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    detail TEXT,
    at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database(database_path: Path):
    """Yield a connection that always commits/rolls back and closes."""
    connection = connect(database_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with database(database_path) as connection:
        connection.executescript(SCHEMA)
