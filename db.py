"""Database connection and schema for the benchmark dashboard."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    eval_id TEXT PRIMARY KEY,
    task TEXT,
    model TEXT,
    created TEXT,
    score REAL,
    stderr REAL,
    samples INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    duration_s REAL,
    log_path TEXT
);

CREATE TABLE IF NOT EXISTS speed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT,
    ts TEXT,
    ctx_tokens INTEGER,
    ttft_s REAL,
    prefill_tps REAL,
    gen_tps REAL,
    out_tokens INTEGER
);

CREATE INDEX IF NOT EXISTS idx_runs_model ON runs(model);
CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task);
CREATE INDEX IF NOT EXISTS idx_speed_model ON speed(model);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection to the SQLite database.

    The connection uses row factory access and is created per-call so that
    callers can pass a fresh path (e.g. a temp DB in tests).
    """
    path = Path(db_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the schema if the tables do not yet exist."""
    conn.executescript(SCHEMA)
    conn.commit()


def close(conn: sqlite3.Connection) -> None:
    """Close the connection, swallowing errors."""
    try:
        conn.close()
    except sqlite3.Error:
        pass
