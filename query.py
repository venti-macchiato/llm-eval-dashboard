"""Shared SQL helpers and column orders for the JSON read endpoints."""

from __future__ import annotations

import sqlite3

import config
import db

RUN_COLUMNS = [
    "eval_id", "task", "model", "created", "score", "stderr", "samples",
    "input_tokens", "output_tokens", "duration_s", "log_path",
]
SPEED_COLUMNS = [
    "id", "model", "ts", "batch_id", "concurrency", "ctx_tokens", "ttft_s",
    "ttft_p50", "ttft_p95", "prefill_tps", "gen_tps", "agg_gen_tps",
    "out_tokens", "requests", "errors", "wall_s",
]


def connect() -> sqlite3.Connection:
    """Open a connection to the configured database (read at call time)."""
    return db.connect(config.DB_PATH)


def filters(
    models: list[str] | None, tasks: list[str] | None
) -> tuple[list[str], list[object]]:
    """Build SQL WHERE clauses and params for multi-value model/task filters."""
    clauses: list[str] = []
    params: list[object] = []
    if models:
        clauses.append("model IN (%s)" % ",".join("?" * len(models)))
        params.extend(models)
    if tasks:
        clauses.append("task IN (%s)" % ",".join("?" * len(tasks)))
        params.extend(tasks)
    return clauses, params
