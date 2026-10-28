"""Tests for the FastAPI app.

Seeds a temporary DB with a few rows (never touches sample_logs) and covers
every GET endpoint, including prev_score and empty-result cases.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

import api
import db


def _seed(conn: sqlite3.Connection) -> None:
    db.init_schema(conn)
    rows = [
        # eval_id, task, model, created, score, stderr, samples
        ("e1", "math", "polystrata-q3", "2024-01-01T10:00:00", 0.50, 0.05, 100),
        ("e2", "math", "polystrata-q3", "2024-01-02T10:00:00", 0.60, 0.04, 100),
        ("e3", "math", "polystrata-q3", "2024-01-03T10:00:00", 0.70, 0.03, 100),
        ("e4", "history", "polystrata-q3", "2024-01-01T10:00:00", 0.40, 0.06, 100),
        ("e5", "math", "gpt-4o", "2024-01-02T10:00:00", 0.65, 0.04, 100),
        ("e6", "history", "gpt-4o", "2024-01-03T10:00:00", 0.55, 0.05, 100),
    ]
    conn.executemany(
        """INSERT INTO runs
           (eval_id, task, model, created, score, stderr, samples,
            input_tokens, output_tokens, duration_s, log_path)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (r[0], r[1], r[2], r[3], r[4], r[5], r[6], None, None, None, r[0] + ".eval")
            for r in rows
        ],
    )
    conn.commit()


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    conn = db.connect(db_path)
    _seed(conn)
    db.close(conn)

    monkeypatch.setattr("config.DB_PATH", str(db_path))
    monkeypatch.setattr("config.LOGS_DIR", str(tmp_path / "no_logs"))

    with TestClient(api.app) as c:
        yield c


def test_models_endpoint(client):
    resp = client.get("/api/models")
    assert resp.status_code == 200
    data = resp.json()
    # /api/models returns the models from config.yaml (only polystrata-q3).
    assert data == ["polystrata-q3"]


def test_runs_endpoint_all(client):
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 6
    # Newest first.
    assert data[0]["eval_id"] == "e6"


def test_runs_endpoint_filter_model(client):
    resp = client.get("/api/runs", params={"model": "polystrata-q3"})
    data = resp.json()
    assert len(data) == 4
    assert all(r["model"] == "polystrata-q3" for r in data)


def test_runs_endpoint_filter_task(client):
    resp = client.get("/api/runs", params={"task": "math"})
    data = resp.json()
    assert len(data) == 4
    assert all(r["task"] == "math" for r in data)


def test_runs_endpoint_limit(client):
    resp = client.get("/api/runs", params={"limit": 2})
    data = resp.json()
    assert len(data) == 2


def test_latest_endpoint_with_prev(client):
    resp = client.get("/api/latest")
    data = resp.json()
    assert resp.status_code == 200
    assert len(data) == 4  # 2 tasks * 2 models

    by_key = {(r["model"], r["task"]): r for r in data}
    # polystrata-q3 math: latest 0.70, prev 0.60
    poly_math = by_key[("polystrata-q3", "math")]
    assert poly_math["score"] == 0.70
    assert poly_math["prev_score"] == 0.60
    assert poly_math["stderr"] == 0.03
    assert poly_math["created"] == "2024-01-03T10:00:00"
    # gpt-4o math: latest 0.65, no previous run -> prev_score null
    gpt_math = by_key[("gpt-4o", "math")]
    assert gpt_math["prev_score"] is None


def test_latest_endpoint_filter_models(client):
    resp = client.get("/api/latest", params={"models": "polystrata-q3"})
    data = resp.json()
    assert len(data) == 2
    assert all(r["model"] == "polystrata-q3" for r in data)


def test_latest_endpoint_empty(client):
    # Filter for a model with no runs -> empty result.
    resp = client.get("/api/latest", params={"models": "nonexistent-model"})
    assert resp.status_code == 200
    assert resp.json() == []


    resp = client.get("/api/latest", params={"models": "nonexistent-model"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_trend_endpoint(client):
    resp = client.get("/api/trend", params={"model": "polystrata-q3", "task": "math"})
    data = resp.json()
    assert resp.status_code == 200
    assert len(data) == 3
    # Oldest first.
    assert data[0]["created"] == "2024-01-01T10:00:00"
    assert data[0]["score"] == 0.50
    assert data[-1]["score"] == 0.70
    assert data[0]["stderr"] == 0.05


def test_trend_endpoint_empty(client):
    resp = client.get("/api/trend", params={"model": "nonexistent", "task": "math"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_speed_endpoint(client, tmp_path, monkeypatch):
    # Seed some speed rows into the monkeypatched DB.
    import config
    db_path = config.DB_PATH
    conn = db.connect(db_path)


    db.init_schema(conn)
    conn.execute(
        """INSERT INTO speed (model, ts, ctx_tokens, ttft_s, prefill_tps, gen_tps, out_tokens)
           VALUES ('polystrata-q3', '2024-01-01T10:00:00', 2000, 0.5, 4000, 50, 100)"""
    )
    conn.execute(
        """INSERT INTO speed (model, ts, ctx_tokens, ttft_s, prefill_tps, gen_tps, out_tokens)
           VALUES ('polystrata-q3', '2024-01-02T10:00:00', 16000, 1.0, 16000, 100, 200)"""
    )
    conn.execute(
        """INSERT INTO speed (model, ts, ctx_tokens, ttft_s, prefill_tps, gen_tps, out_tokens)
           VALUES ('gpt-4o', '2024-01-01T10:00:00', 2000, 0.3, 6000, 80, 100)"""
    )
    conn.commit()
    db.close(conn)

    resp = client.get("/api/speed")
    data = resp.json()
    assert resp.status_code == 200
    assert len(data) == 3
    # Oldest first (by ts).
    assert data[0]["ts"] == "2024-01-01T10:00:00"

    resp = client.get("/api/speed", params={"model": "gpt-4o"})
    data = resp.json()
    assert len(data) == 1
    assert data[0]["model"] == "gpt-4o"


def test_speed_endpoint_empty(client):
    resp = client.get("/api/speed", params={"model": "nonexistent"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_root_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "<!DOCTYPE html>" in resp.text.lower() or "<html" in resp.text.lower()


def test_static_files_served(client):
    resp = client.get("/static/style.css")
    assert resp.status_code == 200
    assert resp.text


def test_ingest_endpoint(client, monkeypatch, tmp_path):
    # Write synthetic logs to a temp dir and point LOGS_DIR there.
    from inspect_ai.log import (
        EvalConfig, EvalDataset, EvalLog, EvalMetric, EvalResults,
        EvalScore, EvalSpec, EvalStats, write_eval_log,
    )
    from datetime import datetime
    root = tmp_path / "logs"
    root.mkdir()
    created = datetime.now()
    spec = EvalSpec(
        eval_id="run_a_math_polystrata", run_id="x", created=created.isoformat(),
        task="math", task_id="math", task_version=1, task_display_name="math",
        model="openai/tiel-coder-35b-a3b-ud-q3_k_xl",
        dataset=EvalDataset(name="math-bench", samples=100),
        config=EvalConfig(token_limit=128000),
    )
    score = EvalScore(name="score", scorer="accuracy", reducer="mean",
                      metrics={"accuracy": EvalMetric(name="accuracy", value=0.72)})
    log = EvalLog(version=1, status="success", eval=spec,
                  results=EvalResults(total_samples=100, completed_samples=100,
                                      scores=[score]),
                  stats=EvalStats(started_at=created.isoformat(),
                                  completed_at=created.isoformat()))
    log.location = str(root / "run_a_math_polystrata.eval")
    write_eval_log(log, format="eval")
    monkeypatch.setattr("config.LOGS_DIR", str(root))
    resp = client.post("/api/ingest")
    assert resp.status_code == 200
    body = resp.json()
    assert "new" in body
    assert isinstance(body["new"], int)

