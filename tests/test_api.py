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
    monkeypatch.setattr(
        "config.MODELS",
        [
            {
                "name": "polystrata-q3",
                "inspect_model": "openai/tiel-coder-35b-a3b-ud-q3_k_xl",
                "base_url": "",
                "model_id": "tiel-coder-35b-a3b-ud-q3_k_xl",
                "api_key_file": "",
                "hardware": {"backend": "llama.cpp", "quant": "Q3_K_XL", "ctx_size": "32768"},
            }
        ],
    )
    monkeypatch.setattr("config.LOGS_DIR", str(tmp_path / "no_logs"))

    with TestClient(api.app) as c:
        yield c


def test_models_endpoint(client):
    resp = client.get("/api/models")
    assert resp.status_code == 200
    data = resp.json()
    # /api/models returns configured models with endpoint metadata (no key).
    assert [m["name"] for m in data] == ["polystrata-q3"]
    assert set(data[0]) == {"name", "base_url", "model_id", "has_key", "hardware"}
    # Declared hardware is normalised (ctx_size string -> int) and keyless.
    assert data[0]["hardware"] == {
        "backend": "llama.cpp",
        "quant": "Q3_K_XL",
        "ctx_size": 32768,
    }


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
    resp = client.get("/static/favicon.svg")
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


def test_runs_multi_value_filter(client):
    resp = client.get(
        "/api/runs",
        params=[("model", "gpt-4o"), ("model", "polystrata-q3")],
    )
    assert resp.status_code == 200
    assert {r["eval_id"] for r in resp.json()} == {"e1", "e2", "e3", "e4", "e5", "e6"}


def test_leaderboard_matrix(client):
    data = client.get("/api/leaderboard").json()
    assert data["models"] == ["gpt-4o", "polystrata-q3"]
    assert data["tasks"] == ["history", "math"]
    # Newest run per (model, task) wins.
    assert data["cells"]["polystrata-q3"]["math"]["eval_id"] == "e3"
    assert data["cells"]["gpt-4o"]["history"]["eval_id"] == "e6"


def test_leaderboard_task_filter(client):
    data = client.get("/api/leaderboard", params={"task": "history"}).json()
    assert data["tasks"] == ["history"]
    assert set(data["cells"]["polystrata-q3"]) == {"history"}


def test_run_detail_and_missing(client):
    body = client.get("/api/run/e3").json()
    assert body["task"] == "math"
    assert body["score"] == 0.7
    assert client.get("/api/run/does-not-exist").status_code == 404


def test_export_runs_csv(client):
    resp = client.get("/api/export/runs.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().splitlines()
    assert lines[0].startswith("eval_id,task,model")
    assert len(lines) == 7  # header + 6 seeded rows


def test_export_runs_json_filtered(client):
    data = client.get("/api/export/runs.json", params={"model": "gpt-4o"}).json()
    assert {r["eval_id"] for r in data} == {"e5", "e6"}


def test_export_rejects_unknown_format(client):
    assert client.get("/api/export/runs.xml").status_code == 400


def test_catalog_endpoint(client):
    data = client.get("/api/catalog").json()
    assert isinstance(data, list)
    assert all("task" in row and "id" in row for row in data)



def test_leaderboard_pools_repeats(client):
    data = client.get("/api/leaderboard").json()
    cell = data["cells"]["polystrata-q3"]["math"]
    # Three runs of the same (model, task, config) pool into one estimate.
    assert cell["k"] == 3
    assert cell["score"] == pytest.approx(0.6)
    se = (0.01 + (0.05**2 + 0.04**2 + 0.03**2) / 3) / 3
    assert cell["stderr"] == pytest.approx(se**0.5)
    assert cell["ci_low"] == pytest.approx(0.6 - 1.96 * se**0.5)
    # Newest member stays the drilldown target.
    assert cell["eval_id"] == "e3"
    assert cell["eval_ids"] == ["e3", "e2", "e1"]


def test_leaderboard_single_run_keeps_stderr(client):
    cell = client.get("/api/leaderboard").json()["cells"]["gpt-4o"]["math"]
    assert cell["k"] == 1
    assert cell["score"] == 0.65
    assert cell["stderr"] == 0.04


def test_groups_endpoint(client):
    groups = client.get("/api/groups").json()
    assert len(groups) == 4  # 2 models x 2 tasks
    poly_math = next(
        g for g in groups if g["model"] == "polystrata-q3" and g["task"] == "math"
    )
    assert poly_math["k"] == 3
    assert poly_math["total_samples"] == 300


def test_eval_run_rejects_bad_repeat_and_epoch_counts(client):
    body = {
        "model": "polystrata-q3",
        "tasks": [{"task": "inspect_evals/gsm8k"}],
        "repeats": 0,
    }
    assert client.post("/api/eval/run", json=body).status_code == 400
    body["repeats"] = 1
    body["epochs"] = "3"
    assert client.post("/api/eval/run", json=body).status_code == 400
    body["epochs"] = 21
    assert client.post("/api/eval/run", json=body).status_code == 400


def test_leaderboard_prefers_dataset_coverage(client):
    """A newer 1-sample smoke run must not outrank a 20-sample group."""
    import config
    import db as dbmod

    conn = dbmod.connect(config.DB_PATH)
    try:
        conn.executemany(
            """INSERT INTO runs (eval_id, task, model, created, score, stderr, samples)
               VALUES (?, 'gsm8k', 'polystrata-q3', ?, ?, ?, ?)""",
            [
                ("n1", "2024-01-05T10:00:00", 1.0, 0.0, 1),
                ("n2", "2024-01-04T10:00:00", 0.90, 0.05, 20),
                ("n3", "2024-01-03T10:00:00", 0.95, 0.04, 20),
            ],
        )
        conn.commit()
    finally:
        dbmod.close(conn)

    cell = client.get("/api/leaderboard").json()["cells"]["polystrata-q3"]["gsm8k"]
    assert cell["samples"] == 20
    assert cell["k"] == 2
    assert cell["score"] == pytest.approx(0.925)


def test_variants_endpoint_groups_and_regresses(client, monkeypatch):
    monkeypatch.setattr(
        "config.MODELS",
        [
            {"name": "polystrata-q3", "base_model": "polystrata", "hardware": {"quant": "Q3_K_XL"}},
            {
                "name": "gpt-4o",
                "base_model": "polystrata",
                "baseline": True,
                "hardware": {"quant": "Q5_K_M"},
            },
        ],
    )
    data = client.get("/api/variants").json()
    fam = data["families"][0]
    assert fam["base_model"] == "polystrata"
    assert fam["baseline"] == "gpt-4o"
    assert [v["model"] for v in fam["variants"]] == ["polystrata-q3", "gpt-4o"]

    reg = fam["regressions"]["polystrata-q3"]["math"]
    assert reg["delta"] == pytest.approx(-0.05)
    assert reg["within_noise"] is True

    override = client.get("/api/variants", params={"baseline": "polystrata-q3"}).json()
    fam = override["families"][0]
    assert fam["baseline"] == "polystrata-q3"
    assert fam["regressions"]["gpt-4o"]["math"]["delta"] == pytest.approx(0.05)


def test_speed_run_rejects_bad_concurrency_and_iterations(client):
    url = "/api/speed/run"
    assert client.post(url, json={"concurrency": [], "iterations": 1}).status_code == 400
    assert client.post(url, json={"concurrency": [0], "iterations": 1}).status_code == 400
    assert client.post(url, json={"concurrency": [2], "iterations": 0}).status_code == 400
    assert client.post(url, json={"concurrency": [2], "iterations": "3"}).status_code == 400


def test_speed_status_reports_defaults(client):
    data = client.get("/api/speed/status").json()
    assert data["concurrency"] == [1]
    assert data["iterations"] == 1
    assert data["running"] is False


def test_prompts_definitions_endpoint(client):
    data = client.get("/api/prompts").json()
    assert data["tests"], "prompts.yaml should define starter tests"
    first = data["tests"][0]
    assert {"id", "title", "category", "prompt", "check"} <= set(first)
    assert data["running"] is False


def test_prompts_results_empty(client):
    assert client.get("/api/prompts/results").json() == {"runs": []}


def test_prompts_run_validation_and_conflicts(client, monkeypatch):
    url = "/api/prompts/run"
    assert client.post(url, json={}).status_code == 400
    assert client.post(url, json={"model": "nope"}).status_code == 400
    assert client.post(url, json={"model": "polystrata-q3", "repeats": 0}).status_code == 400
    monkeypatch.setattr("evaljobs.is_running", lambda: True)
    assert client.post(url, json={"model": "polystrata-q3"}).status_code == 409


def test_eval_and_speed_refuse_while_prompts_run(client, monkeypatch):
    monkeypatch.setattr("promptharness.is_running", lambda: True)
    eval_body = {"model": "polystrata-q3", "suite": "smoke"}
    assert client.post("/api/eval/run", json=eval_body).status_code == 409
    assert client.post("/api/speed/run", json={}).status_code == 409


def test_preflight_reports_docker_availability(client, monkeypatch):
    import sys

    import sandbox

    sandbox.clear_cache()
    monkeypatch.setattr(sandbox, "DOCKER_CMD", [sys.executable, "-c", "print('24.0.7')"])
    data = client.get("/api/preflight").json()
    assert data["capabilities"]["docker"] == {"available": True, "detail": "24.0.7"}
    assert data["requirements"]["humaneval"] == ["docker"]

    sandbox.clear_cache()
    monkeypatch.setattr(
        sandbox, "DOCKER_CMD", [sys.executable, "-c", "import sys; sys.exit(1)"]
    )
    data = client.get("/api/preflight").json()
    assert data["capabilities"]["docker"]["available"] is False
    sandbox.clear_cache()


def test_preflight_refresh_bypasses_the_cache(client, monkeypatch):
    import sys

    import sandbox

    sandbox.clear_cache()
    monkeypatch.setattr(
        sandbox, "DOCKER_CMD", [sys.executable, "-c", "import sys; sys.exit(1)"]
    )
    assert client.get("/api/preflight").json()["capabilities"]["docker"]["available"] is False
    monkeypatch.setattr(sandbox, "DOCKER_CMD", [sys.executable, "-c", "print('24.0.7')"])
    # Cached answer is still the old failure.
    assert client.get("/api/preflight").json()["capabilities"]["docker"]["available"] is False
    refreshed = client.get("/api/preflight", params={"refresh": 1}).json()
    assert refreshed["capabilities"]["docker"] == {"available": True, "detail": "24.0.7"}
    sandbox.clear_cache()


def test_catalog_excludes_scorers():
    import catalog

    catalog._cache = None
    try:
        names = catalog.load_catalog()
    finally:
        catalog._cache = None
    assert "gsm8k" in names
    assert "persistbench_judge" not in names


def test_catalog_empty_when_inspect_evals_missing(monkeypatch):
    import catalog

    catalog._cache = None
    monkeypatch.setattr(
        catalog.importlib.util,
        "find_spec",
        lambda name: (_ for _ in ()).throw(ModuleNotFoundError("inspect_evals")),
    )
    try:
        assert catalog.load_catalog() == []
    finally:
        catalog._cache = None


def test_font_css_endpoint(client):
    resp = client.get("/api/fonts.css")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/css")
