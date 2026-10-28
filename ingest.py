"""Ingest inspect AI eval logs into the runs table.

Idempotent on eval_id: running ingest twice adds zero new rows.

Model names: config.yaml gives each model a dashboard ``name`` and the
``inspect_model`` string that inspect_ai recorded in its logs. We store the
dashboard name in the runs table so the UI picker and filters match config,
not the raw inspect string.
"""

from __future__ import annotations

from pathlib import Path

from db import close, connect, init_schema


def _model_map() -> dict[str, str]:
    """Map dashboard model name -> inspect_ai model string."""
    from config import MODELS

    return {m["name"]: m.get("inspect_model", m["name"]) for m in MODELS}


def _row_to_tuple(row, model_name: str) -> tuple | None:
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
        created = str(created) if created is not None else None
        return (
            str(eval_id),
            row.get("task_name"),
            model_name,
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


def ingest(logs_dir: str | Path, db_path: str | Path) -> dict[str, int]:
    """Ingest logs from logs_dir into db_path.

    Returns ``{"new": inserted, "skipped": skipped}``. ``new`` is the count of
    NEW runs inserted (idempotent on eval_id); ``skipped`` counts rows dropped
    because they had no headline score or an unknown model.

    Raises on real errors (missing dir, unreadable/corrupt logs, missing
    dependency) instead of silently returning 0, so a bad path is never
    mistaken for "no new runs".
    """
    from inspect_ai.analysis import evals_df

    from config import MODELS

    model_map = _model_map()
    # Fallback: if a log's model isn't in config, map by inspect string.
    reverse_map: dict[str, str] = {}
    for m in MODELS:
        ins = m.get("inspect_model")
        if ins:
            reverse_map[ins] = m["name"]

    logs_dir = Path(logs_dir)
    conn = connect(db_path)
    try:
        init_schema(conn)
        df = evals_df(str(logs_dir))

        inserted = 0
        skipped = 0
        existing = {r["eval_id"] for r in conn.execute("SELECT eval_id FROM runs")}
        for _, row in df.iterrows():
            inspect_model = row.get("model")
            model_name = model_map.get(inspect_model) or reverse_map.get(inspect_model)
            if model_name is None:
                skipped += 1
                continue
            values = _row_to_tuple(row, model_name)
            if values is None:
                # Row has no headline score (or unparseable): skip.
                skipped += 1
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
        return {"new": inserted, "skipped": skipped}
    except Exception:
        # Roll back partial inserts so a failure doesn't leave a half-written DB.
        conn.rollback()
        raise
    finally:
        close(conn)
