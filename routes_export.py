"""CSV/JSON export endpoints for runs and speed samples."""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

import db
from query import RUN_COLUMNS, SPEED_COLUMNS, connect, filters

router = APIRouter(prefix="/api")


@router.get("/export/runs.{fmt}")
def export_runs(
    fmt: str,
    model: list[str] | None = Query(None),
    task: list[str] | None = Query(None),
):
    return _export("runs", RUN_COLUMNS, fmt, model, task, "SELECT * FROM runs")


@router.get("/export/speed.{fmt}")
def export_speed(fmt: str, model: list[str] | None = Query(None)):
    return _export("speed", SPEED_COLUMNS, fmt, model, None, "SELECT * FROM speed")


def _export(table, columns, fmt, models, tasks, base_sql):
    fmt = fmt.lower()
    if fmt not in ("csv", "json"):
        raise HTTPException(status_code=400, detail="format must be csv or json")
    clauses, params = filters(models, tasks)
    sql = base_sql
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += f" ORDER BY {'created DESC' if table == 'runs' else 'ts ASC'}"
    conn = connect()
    try:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        db.close(conn)

    if fmt == "json":
        return Response(
            json.dumps(rows, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{table}.json"'},
        )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{table}.csv"'},
    )
