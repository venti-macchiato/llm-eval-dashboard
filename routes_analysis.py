"""Aggregate read endpoints: latest scores, trends, pooled groups, leaderboard.

Kept separate from :mod:`routes_data` so per-run reads stay small. Everything
here is derived from the same ``runs`` table; pooling lives in
:mod:`aggregate`.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

import aggregate
import config
import db
import variants
from query import connect, filters

router = APIRouter(prefix="/api")


@router.get("/latest")
def latest(models: str | None = Query(None)):
    """Most recent run per (model, task), with the score of the run before it."""
    conn = connect()
    try:
        sql = "SELECT model, task, created, score, stderr, eval_id FROM runs"
        params: list[object] = []
        if models:
            names = [m.strip() for m in models.split(",") if m.strip()]
            if names:
                sql += " WHERE model IN (%s)" % ",".join("?" * len(names))
                params.extend(names)
        sql += " ORDER BY model ASC, task ASC, created DESC"
        rows = conn.execute(sql, params).fetchall()
    finally:
        db.close(conn)

    grouped: dict[tuple[str, str], list] = {}
    for row in rows:
        grouped.setdefault((row["model"], row["task"]), []).append(row)

    result = []
    for (model_name, task), runs in grouped.items():
        cur = runs[0]
        prev = runs[1] if len(runs) > 1 else None
        result.append(
            {
                "model": cur["model"],
                "task": cur["task"],
                "score": cur["score"],
                "stderr": cur["stderr"],
                "created": cur["created"],
                "prev_score": prev["score"] if prev else None,
            }
        )
    return result


@router.get("/trend")
def trend(model: str, task: str):
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT created, score, stderr FROM runs WHERE model = ? AND task = ? "
            "ORDER BY created ASC",
            (model, task),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close(conn)


@router.get("/leaderboard")
def leaderboard(
    model: list[str] | None = Query(None),
    task: list[str] | None = Query(None),
):
    """Pooled score per (model, task), as a matrix for the UI.

    Each cell is the best-supported group for that pair: repeats of one
    configuration and sample count are pooled into a mean ± CI (see
    aggregate.py), so the cell shows evidence rather than an arbitrary run.
    """
    clauses, params = filters(model, task)
    sql = "SELECT * FROM runs"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created DESC, eval_id DESC"
    conn = connect()
    try:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        db.close(conn)

    cells: dict[str, dict[str, dict | None]] = {}
    grouped = aggregate.groups(rows)

    # One cell per (model, task): newest configuration, then the group with the
    # most dataset coverage (largest limit).
    for (model, task), group in aggregate.best_from_groups(grouped).items():
        cells.setdefault(model, {})[task] = group

    model_names = sorted(cells)
    task_names = sorted({group["task"] for group in grouped})
    for name in model_names:
        for task_name in task_names:
            cells[name].setdefault(task_name, None)
    return {"models": model_names, "tasks": task_names, "cells": cells}


@router.get("/variants")
def variant_matrix(
    model: list[str] | None = Query(None),
    task: list[str] | None = Query(None),
    baseline: str | None = Query(None),
):
    """Variants grouped by base model, with deltas against a baseline.

    ``baseline`` overrides the configured ``baseline: true`` entry for the
    family that contains it, so the UI can switch reference variants without
    editing config.yaml.
    """
    clauses, params = filters(model, task)
    sql = "SELECT * FROM runs"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created DESC, eval_id DESC"
    conn = connect()
    try:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        db.close(conn)
    return variants.build(config.MODELS, aggregate.groups(rows), baseline)


@router.get("/groups")
def run_groups(
    model: list[str] | None = Query(None),
    task: list[str] | None = Query(None),
    limit: int = Query(5000, ge=1, le=100000),
):
    """Runs pooled into configuration groups, for Compare."""
    clauses, params = filters(model, task)
    sql = "SELECT * FROM runs"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created DESC, eval_id DESC LIMIT ?"
    params.append(limit)
    conn = connect()
    try:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        db.close(conn)
    return aggregate.groups(rows)
