"""Tests for ingest.py.

Writes synthetic inspect AI .eval logs into a temp directory (rather than the
removed sample_logs/) so the ingest path is exercised end to end without
depending on committed sample data.
"""

import sqlite3
from datetime import datetime, timedelta

import pytest

import db
import ingest


def _write_logs(root, specs):
    """Write synthetic .eval logs to root. specs: list of (eval_id, task, model, score)."""
    from inspect_ai.log import (
        EvalConfig,
        EvalDataset,
        EvalLog,
        EvalMetric,
        EvalResults,
        EvalScore,
        EvalSpec,
        EvalStats,
        write_eval_log,
    )

    root.mkdir(parents=True, exist_ok=True)
    for eval_id, task, model, score in specs:
        created = datetime.now() - timedelta(days=1)
        samples = 100
        se = round((score * (1 - score) / samples) ** 0.5, 4)
        metrics = {
            "accuracy": EvalMetric(name="accuracy", value=score),
            "stderr": EvalMetric(name="stderr", value=se),
        }
        result_score = EvalScore(name="score", scorer="accuracy", reducer="mean", metrics=metrics)
        results = EvalResults(total_samples=samples, completed_samples=samples, scores=[result_score])
        stats = EvalStats(started_at=created.isoformat(), completed_at=created.isoformat())
        spec = EvalSpec(
            eval_id=eval_id,
            run_id=f"{model}-{task}",
            created=created.isoformat(),
            task=task,
            task_id=task,
            task_version=1,
            task_display_name=task,
            model=model,
            dataset=EvalDataset(name=f"{task}-bench", samples=samples),
            config=EvalConfig(token_limit=128000),
        )
        log = EvalLog(
            version=1,
            status="success",
            eval=spec,
            results=results,
            stats=stats,
            metadata={"model": model},
        )
        log.location = str(root / f"{eval_id}.eval")
        write_eval_log(log, format="eval")


def _logs_dir(tmp_path):
    root = tmp_path / "logs"
    _write_logs(root, [
        ("run_a_math_polystrata", "math", "openai/tiel-coder-35b-a3b-ud-q3_k_xl", 0.72),
        ("run_b_math_polystrata", "math", "openai/tiel-coder-35b-a3b-ud-q3_k_xl", 0.75),
        ("run_c_math_polystrata", "math", "openai/tiel-coder-35b-a3b-ud-q3_k_xl", 0.80),
    ])
    return root


def test_ingest_maps_model_names(tmp_path):
    """Model names in logs map to config names, not raw inspect strings."""
    db_path = tmp_path / "bench.db"
    result = ingest.ingest(str(_logs_dir(tmp_path)), db_path)

    assert result["new"] == 3
    conn = db.connect(db_path)
    try:
        rows = conn.execute("SELECT model FROM runs").fetchall()
        models = {r["model"] for r in rows}
        # Config names, not raw inspect strings.
        assert "polystrata-q3" in models
        assert "openai/tiel-coder-35b-a3b-ud-q3_k_xl" not in models
    finally:
        db.close(conn)


def test_ingest_idempotent(tmp_path):
    db_path = tmp_path / "bench.db"
    result = ingest.ingest(str(_logs_dir(tmp_path)), db_path)
    assert result["new"] == 3
    again = ingest.ingest(str(_logs_dir(tmp_path)), db_path)
    assert again == {"new": 0, "skipped": 0}


def test_ingest_empty_dir(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    db_path = tmp_path / "empty.db"
    result = ingest.ingest(empty, db_path)
    assert result == {"new": 0, "skipped": 0}


def test_ingest_unknown_model_skipped(tmp_path):
    """A log whose model isn't in config is skipped, not inserted."""
    root = tmp_path / "logs"
    _write_logs(root, [
        ("run_a_math_polystrata", "math", "openai/tiel-coder-35b-a3b-ud-q3_k_xl", 0.72),
        ("run_unknown", "math", "openai/some-unknown-model", 0.5),
    ])
    db_path = tmp_path / "bench.db"
    result = ingest.ingest(str(root), db_path)
    assert result["new"] == 1
    assert result["skipped"] == 1
    conn = db.connect(db_path)
    try:
        models = {r["model"] for r in conn.execute("SELECT model FROM runs").fetchall()}
        assert "some-unknown-model" not in models
    finally:
        db.close(conn)


def test_ingest_raises_on_missing_dir(tmp_path):
    db_path = tmp_path / "bench.db"
    with pytest.raises(Exception):
        ingest.ingest(str(tmp_path / "does_not_exist"), db_path)


def test_ingest_rolls_back_on_failure(tmp_path):
    """A failure mid-ingest must not leave a half-written DB."""
    from inspect_ai.log import (
        EvalConfig,
        EvalDataset,
        EvalLog,
        EvalResults,
        EvalScore,
        EvalSpec,
        EvalStats,
    )

    root = tmp_path / "logs"
    _write_logs(root, [
        ("run_a_math_polystrata", "math", "openai/tiel-coder-35b-a3b-ud-q3_k_xl", 0.72),
    ])
    db_path = tmp_path / "bench.db"
    # Write a second log that is corrupt (invalid eval format) so evals_df raises.
    with open(root / "run_b.eval", "w") as fh:
        fh.write("this is not valid eval log data\n" * 100)

    with pytest.raises(Exception):
        ingest.ingest(str(root), db_path)
    # DB must be rolled back (no partial rows).
    conn = db.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        assert count == 0
    finally:
        db.close(conn)
