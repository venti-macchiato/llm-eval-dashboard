"""FastAPI app for the benchmark dashboard.

All endpoints are read-only except POST /api/ingest and POST /api/speed/run.
Static files are served from the static/ directory next to this module.
"""

from __future__ import annotations

from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import config
import db
import ingest
import speed

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Create the schema on startup so queries work before the first ingest."""
    conn = db.connect(config.DB_PATH)
    db.init_schema(conn)
    db.close(conn)
    yield


app = FastAPI(title="LLM Benchmark Dashboard", lifespan=_lifespan)


def _query_db() -> db.Connection:
    from config import DB_PATH

    return db.connect(DB_PATH)


@app.get("/api/models")
def list_models():
    from config import MODELS

    return [m["name"] for m in MODELS]


@app.get("/api/runs")
def list_runs(
    model: str | None = Query(None),
    task: str | None = Query(None),
    limit: int = Query(200, ge=1, le=10000),
):
    conn = _query_db()
    try:
        sql = "SELECT * FROM runs WHERE 1=1"
        params: list[object] = []
        if model:
            sql += " AND model = ?"
            params.append(model)
        if task:
            sql += " AND task = ?"
            params.append(task)
        sql += " ORDER BY created DESC, eval_id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close(conn)


@app.get("/api/latest")
def latest(models: str | None = Query(None)):
    """Most recent run per (model, task), with the score of the run before it."""
    conn = _query_db()
    try:
        sql = "SELECT model, task, created, score, stderr, eval_id FROM runs"
        params: list[object] = []
        if models:
            names = [m.strip() for m in models.split(",") if m.strip()]
            if names:
                placeholders = ",".join("?" * len(names))
                sql += " WHERE model IN (%s)" % placeholders
                params.extend(names)
        sql += " ORDER BY model ASC, task ASC, created DESC"
        rows = conn.execute(sql, params).fetchall()

        # Group by (model, task) in creation order (newest first).
        grouped: dict[tuple[str, str], list["sqlite3.Row"]] = {}
        for row in rows:
            grouped.setdefault((row["model"], row["task"]), []).append(row)

        result = []
        for (model, task), runs in grouped.items():
            latest_run = runs[0]
            prev_run = runs[1] if len(runs) > 1 else None
            result.append(
                {
                    "model": latest_run["model"],
                    "task": latest_run["task"],
                    "score": latest_run["score"],
                    "stderr": latest_run["stderr"],
                    "created": latest_run["created"],
                    "prev_score": prev_run["score"] if prev_run else None,
                }
            )
        return result
    finally:
        db.close(conn)


@app.get("/api/trend")
def trend(model: str, task: str):
    conn = _query_db()
    try:
        rows = conn.execute(
            "SELECT created, score, stderr FROM runs WHERE model = ? AND task = ? "
            "ORDER BY created ASC",
            (model, task),
        ).fetchall()
        return [
            {
                "created": r["created"],
                "score": r["score"],
                "stderr": r["stderr"],
            }
            for r in rows
        ]
    finally:
        db.close(conn)


@app.get("/api/speed")
def speed_data(
    model: str | None = Query(None),
    limit: int = Query(10000, ge=1, le=100000),
):
    conn = _query_db()
    try:
        sql = "SELECT * FROM speed"
        params: list[object] = []
        if model:
            sql += " WHERE model = ?"
            params.append(model)
        sql += " ORDER BY ts ASC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close(conn)


@app.get("/api/speed/status")
def speed_status():
    """Probe status: running flag and any captured error from the thread."""
    return {"running": speed.is_running(), "error": speed.last_error()}


@app.post("/api/ingest")
def api_ingest():
    from config import DB_PATH, LOGS_DIR

    result = ingest.ingest(LOGS_DIR, DB_PATH)
    return {"new": result["new"], "skipped": result["skipped"]}


@app.post("/api/speed/run")
def api_speed_run():
    started = speed.start_probe()
    return {"started": started}


@app.get("/")
def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


if STATIC_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR)),
        name="static",
    )
