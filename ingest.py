"""Ingest inspect AI eval logs into the runs table.

Idempotent on eval_id: running ingest twice adds zero new rows.
"""

from __future__ import annotations

from pathlib import Path

from db import close, connect, init_schema


def _row_to_tuple(row) -> tuple | None:
    """Map an evals_df row to a runs tuple. Returns None on bad data."""
    try:
        eval_id = row["eval_id"]
        if not eval_id:
            return None
        score = row.get("score_headline_value")
        if score is None:
            return None
        score = float(score)
        stderr = row.get("score_headline_stderr")
        stderr = float(stderr) if stderr is not None else None
        samples = row.get("total_samples")
        samples = int(samples) if samples is not None else None
        created = row.get("created")
        if created is None:
            created = None
        else:
            created = str(created)
        return (
            str(eval_id),
            row.get("task_name"),
            row.get("model"),
            created,
            score,
            stderr,
            samples,
            row.get("input_tokens"),
            row.get("output_tokens"),
            row.get("duration_s"),
            row.get("log"),
        )
    except (KeyError, ValueError, TypeError):
        return None


def ingest(logs_dir: str | Path, db_path: str | Path) -> int:
    """Ingest logs from logs_dir into db_path.

    Returns the number of NEW runs inserted. Idempotent on eval_id.
    """
    from inspect_ai.analysis import evals_df

    logs_dir = Path(logs_dir)
    conn = connect(db_path)
    try:
        init_schema(conn)
        try:
            df = evals_df(str(logs_dir))
        except Exception:
            # No logs / empty dir: nothing to ingest.
            return 0

        inserted = 0
        existing = {r["eval_id"] for r in conn.execute("SELECT eval_id FROM runs")}
        for _, row in df.iterrows():
            values = _row_to_tuple(row)
            if values is None:
                continue
            if values[0] in existing:
                continue
            conn.execute(
                """INSERT INTO runs
                   (eval_id, task, model, created, score, stderr, samples,
                    input_tokens, output_tokens, duration_s, log_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            inserted += 1
            existing.add(values[0])
        conn.commit()
        return inserted
    finally:
        close(conn)
