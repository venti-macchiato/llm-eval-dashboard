"""Persistence for prompt runs and their per-test rows."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import db

RUN_COLUMNS = (
    "run_id",
    "model",
    "ts",
    "completed",
    "tests",
    "passed",
    "errors",
    "repeats",
    "meta",
)
RESULT_COLUMNS = (
    "run_id",
    "model",
    "ts",
    "test_id",
    "title",
    "category",
    "repeat",
    "passed",
    "output",
    "detail",
    "latency_s",
    "input_tokens",
    "output_tokens",
    "error",
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def save_run(
    db_path: str | Path,
    run_id: str,
    model: str,
    ts: str,
    repeats: int,
    results: list[dict],
) -> None:
    """Persist one prompt run and its per-test rows."""
    conn = db.connect(db_path)
    try:
        db.init_schema(conn)
        passed = sum(1 for row in results if row.get("passed"))
        errors = sum(1 for row in results if row.get("error"))
        conn.execute(
            f"INSERT OR REPLACE INTO prompt_runs ({', '.join(RUN_COLUMNS)}) "
            f"VALUES ({', '.join('?' * len(RUN_COLUMNS))})",
            (run_id, model, ts, _now(), len(results), passed, errors, repeats, None),
        )
        rows = []
        for result in results:
            enriched = {**result, "run_id": run_id, "ts": ts}
            rows.append(tuple(enriched.get(column) for column in RESULT_COLUMNS))
        conn.executemany(
            f"INSERT INTO prompt_results ({', '.join(RESULT_COLUMNS)}) "
            f"VALUES ({', '.join('?' * len(RESULT_COLUMNS))})",
            rows,
        )
        conn.commit()
    finally:
        db.close(conn)


def recent_runs(
    db_path: str | Path,
    model: list[str] | None = None,
    run_id: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Runs newest-first, each with its per-test rows."""
    conn = db.connect(db_path)
    try:
        db.init_schema(conn)
        sql = "SELECT * FROM prompt_runs"
        clauses, params = [], []
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if model:
            clauses.append("model IN (%s)" % ",".join("?" * len(model)))
            params.extend(model)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY ts DESC, rowid DESC LIMIT ?"
        params.append(limit)
        runs = [dict(row) for row in conn.execute(sql, params)]
        for run in runs:
            run["results"] = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM prompt_results WHERE run_id = ? ORDER BY id",
                    (run["run_id"],),
                )
            ]
        return runs
    finally:
        db.close(conn)
