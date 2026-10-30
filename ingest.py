"""Ingest inspect AI eval logs into the runs table.

Idempotent on eval_id. New columns (token counts, duration, provenance meta,
error sample count) are backfilled for rows ingested by older versions.
"""

from __future__ import annotations

from pathlib import Path

import hardware
from db import close, connect, init_schema
from runlog import log_stats
from runmeta import error_samples, merge_meta, meta_for, num


def _model_map() -> dict[str, str]:
    """Map dashboard model name -> inspect_ai model string."""
    from config import MODELS

    return {m["name"]: m.get("inspect_model", m["name"]) for m in MODELS}


# Columns backfilled for rows ingested by older versions, with their index in
# the tuple returned by _row_to_tuple.
_BACKFILL = (
    ("input_tokens", 7),
    ("output_tokens", 8),
    ("duration_s", 9),
    ("error_samples", 12),
)


def _row_to_tuple(
    row, model_name: str, model_cfg: dict | None, hw: dict | None = None
) -> tuple | None:
    """Map an evals_df row to a runs tuple. Returns None on bad data."""
    try:
        eval_id = row["eval_id"]
        if not eval_id:
            return None
        score = num(row.get("score_headline_value"))
        if score is None:
            return None
        stderr = num(row.get("score_headline_stderr"))
        samples = num(row.get("total_samples"))
        samples = int(samples) if samples is not None else None
        created = row.get("created")
        created = str(created) if created is not None else None
        log_path = row.get("log")
        input_tokens = row.get("input_tokens")
        output_tokens = row.get("output_tokens")
        duration_s = row.get("duration_s")
        if input_tokens is None or output_tokens is None or duration_s is None:
            log_in, log_out, log_dur = log_stats(log_path)
            input_tokens = input_tokens if input_tokens is not None else log_in
            output_tokens = output_tokens if output_tokens is not None else log_out
            duration_s = duration_s if duration_s is not None else log_dur
        return (
            str(eval_id),
            row.get("task_name"),
            model_name,
            created,
            score,
            stderr,
            samples,
            input_tokens,
            output_tokens,
            duration_s,
            log_path,
            meta_for(row, model_cfg, hw),
            error_samples(row),
        )
    except (KeyError, ValueError, TypeError):
        return None


def ingest(logs_dir: str | Path, db_path: str | Path) -> dict[str, int]:
    """Ingest logs from logs_dir into db_path.

    Returns ``{"new": n, "skipped": s, "updated": u}``. ``new`` counts inserted
    eval ids; ``updated`` counts existing rows enriched with token/duration/
    provenance data (including hardware declared or probed after the row was
    first ingested); ``skipped`` counts rows dropped because they had no
    headline score or an unknown model.

    Raises on real errors (missing dir, unreadable/corrupt logs, missing
    dependency) instead of silently returning 0.
    """
    from inspect_ai.analysis import evals_df

    from config import MODELS

    model_map = _model_map()
    config_by_name = {m["name"]: m for m in MODELS}
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
        updated = 0
        skipped = 0
        existing = {
            r["eval_id"]: r
            for r in conn.execute(
                "SELECT eval_id, input_tokens, output_tokens, duration_s, "
                "meta, error_samples FROM runs"
            )
        }
        hw_cache: dict[str, dict | None] = {}

        def _hw(name: str, cfg: dict | None) -> dict | None:
            """Probe each model at most once per ingest, and only when used."""
            if name not in hw_cache:
                hw_cache[name] = hardware.snapshot(cfg)
            return hw_cache[name]

        for _, row in df.iterrows():
            inspect_model = row.get("model")
            model_name = model_map.get(inspect_model) or reverse_map.get(inspect_model)
            if model_name is None:
                skipped += 1
                continue
            eval_id = row.get("eval_id")
            if eval_id is None:
                continue
            eid = str(eval_id)
            model_cfg = config_by_name.get(model_name)
            hw = _hw(model_name, model_cfg)
            prior = existing.get(eid)
            if prior is not None:
                values = _row_to_tuple(row, model_name, model_cfg, hw)
                if values is None:
                    continue
                updates: dict[str, object] = {}
                for column, index in _BACKFILL:
                    if prior[column] is None and values[index] is not None:
                        updates[column] = values[index]
                meta = merge_meta(prior["meta"], values[11])
                if meta != prior["meta"]:
                    updates["meta"] = meta
                if not updates:
                    continue
                assignments = ", ".join(f"{column} = ?" for column in updates)
                conn.execute(
                    f"UPDATE runs SET {assignments} WHERE eval_id = ?",
                    (*updates.values(), eid),
                )
                updated += 1
                continue
            values = _row_to_tuple(row, model_name, model_cfg, hw)
            if values is None:
                skipped += 1
                continue
            conn.execute(
                """INSERT INTO runs
                   (eval_id, task, model, created, score, stderr, samples,
                    input_tokens, output_tokens, duration_s, log_path, meta,
                    error_samples)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            inserted += 1
            existing[eid] = {
                "eval_id": eid,
                "input_tokens": values[7],
                "output_tokens": values[8],
                "duration_s": values[9],
                "meta": values[11],
                "error_samples": values[12],
            }
        conn.commit()
        return {"new": inserted, "skipped": skipped, "updated": updated}
    except Exception:
        conn.rollback()
        raise
    finally:
        close(conn)
