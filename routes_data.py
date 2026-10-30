"""Read-only data endpoints: models, runs, latest, trend, speed, leaderboard,
run detail, and the task catalog.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

import benchmarks
import catalog
import config
import db
import hardware
import runlog
from query import connect, filters

router = APIRouter(prefix="/api")


@router.get("/models")
def list_models():
    """Configured models with endpoint metadata. Never returns the API key."""
    out = []
    for m in config.MODELS:
        key_file = m.get("api_key_file", "")
        has_key = bool(key_file) and Path(os.path.expanduser(key_file)).exists()
        out.append(
            {
                "name": m.get("name", ""),
                "base_url": m.get("base_url", ""),
                "model_id": m.get("model_id", ""),
                "has_key": has_key,
                "hardware": hardware.declared(m),
            }
        )
    return out


@router.get("/runs")
def list_runs(
    model: list[str] | None = Query(None),
    task: list[str] | None = Query(None),
    limit: int = Query(200, ge=1, le=100000),
):
    clauses, params = filters(model, task)
    sql = "SELECT * FROM runs"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created DESC, eval_id DESC LIMIT ?"
    params.append(limit)
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        db.close(conn)


@router.get("/run/{eval_id}/samples")
def run_samples(
    eval_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    failures: bool = Query(False),
):
    """Per-sample breakdown read from the run's ``.eval`` log on demand.

    ``failures=1`` filters server-side to samples with an error or score 0,
    with ``offset``/``limit`` paging over the filtered set.
    """
    conn = connect()
    try:
        row = conn.execute(
            "SELECT log_path FROM runs WHERE eval_id = ?", (eval_id,)
        ).fetchone()
    finally:
        db.close(conn)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    log_path = row["log_path"]
    if not log_path:
        raise HTTPException(status_code=422, detail="run has no log path")
    try:
        report = runlog.sample_report(str(log_path), limit, offset, failures)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="log file not found") from exc
    except Exception as exc:  # noqa: BLE001 - surface read failures to the UI
        raise HTTPException(
            status_code=422, detail=f"could not read log: {exc}"
        ) from exc
    report["eval_id"] = eval_id
    return report


@router.get("/run/{eval_id}")
def run_detail(eval_id: str):
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM runs WHERE eval_id = ?", (eval_id,)
        ).fetchone()
    finally:
        db.close(conn)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    return dict(row)


@router.get("/speed")
def speed_data(
    model: list[str] | None = Query(None),
    limit: int = Query(10000, ge=1, le=100000),
):
    sql = "SELECT * FROM speed"
    params: list[object] = []
    if model:
        sql += " WHERE model IN (%s)" % ",".join("?" * len(model))
        params.extend(model)
    sql += " ORDER BY ts ASC, id ASC LIMIT ?"
    params.append(limit)
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        db.close(conn)


@router.get("/catalog")
def task_catalog():
    names = catalog.load_catalog()
    return [{"task": n, "id": f"inspect_evals/{n}"} for n in names]


@router.get("/benchmarks")
def benchmarks_catalog():
    """Curated descriptions, categories, and suite blurbs for the UI."""
    return benchmarks.payload()
