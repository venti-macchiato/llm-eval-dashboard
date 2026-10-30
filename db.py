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
    log_path TEXT,
    meta TEXT,
    error_samples INTEGER
);

CREATE TABLE IF NOT EXISTS speed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT,
    ts TEXT,
    ctx_tokens INTEGER,
    ttft_s REAL,
    prefill_tps REAL,
    gen_tps REAL,
    out_tokens INTEGER,
    concurrency INTEGER,
    batch_id TEXT,
    ttft_p50 REAL,
    ttft_p95 REAL,
    agg_gen_tps REAL,
    requests INTEGER,
    errors INTEGER,
    wall_s REAL
);

CREATE TABLE IF NOT EXISTS prompt_runs (
    run_id TEXT PRIMARY KEY,
    model TEXT,
    ts TEXT,
    completed TEXT,
    tests INTEGER,
    passed INTEGER,
    errors INTEGER,
    repeats INTEGER,
    meta TEXT
);

CREATE TABLE IF NOT EXISTS prompt_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    model TEXT,
    ts TEXT,
    test_id TEXT,
    title TEXT,
    category TEXT,
    repeat INTEGER,
    passed INTEGER,
    output TEXT,
    detail TEXT,
    latency_s REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_model ON runs(model);
CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task);
CREATE INDEX IF NOT EXISTS idx_speed_model ON speed(model);
CREATE INDEX IF NOT EXISTS idx_prompt_results_run ON prompt_results(run_id);
CREATE INDEX IF NOT EXISTS idx_prompt_results_model ON prompt_results(model);
"""

# Columns added after the first release. Applied to existing databases so
# upgrading does not require deleting the local DB.
_MIGRATIONS = {
    "runs": [("meta", "TEXT"), ("error_samples", "INTEGER")],
    "speed": [
        ("concurrency", "INTEGER"),
        ("batch_id", "TEXT"),
        ("ttft_p50", "REAL"),
        ("ttft_p95", "REAL"),
        ("agg_gen_tps", "REAL"),
        ("requests", "INTEGER"),
        ("errors", "INTEGER"),
        ("wall_s", "REAL"),
    ],
}


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


def _migrate(conn: sqlite3.Connection) -> None:
    for table, columns in _MIGRATIONS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the schema if needed and apply additive migrations."""
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()


def close(conn: sqlite3.Connection) -> None:
    """Close the connection, swallowing errors."""
    try:
        conn.close()
    except sqlite3.Error:
        pass
