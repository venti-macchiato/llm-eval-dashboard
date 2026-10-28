"""Tests for ingest.py.

Uses the real sample_logs directory (generated .eval files) so the ingest
path is exercised end to end.
"""

import sqlite3

import pytest

import db
import ingest


@pytest.fixture(scope="module")
def sample_db(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("bench") / "test.db"
    inserted = ingest.ingest("sample_logs", db_path)
    conn = db.connect(db_path)
    try:
        assert inserted == 7, f"expected 7 new runs, got {inserted}"
        # Idempotency: a second run adds nothing.
        again = ingest.ingest("sample_logs", db_path)
        assert again == 0
        rows = conn.execute("SELECT COUNT(*) FROM runs").fetchone()
        assert rows[0] == 7
        yield conn
    finally:
        db.close(conn)


def test_rows_have_expected_fields(sample_db):
    rows = sample_db.execute(
        "SELECT eval_id, task, model, score, stderr, samples, log_path "
        "FROM runs ORDER BY eval_id"
    ).fetchall()
    assert len(rows) == 7
    first = rows[0]
    assert first["eval_id"]
    assert first["task"]
    assert first["model"]
    assert first["score"] is not None
    assert first["stderr"] is not None
    assert first["samples"] is not None
    assert first["log_path"]


def test_scores_are_floats_in_unit_interval(sample_db):
    scores = sample_db.execute("SELECT score FROM runs").fetchall()
    for row in scores:
        score = row["score"]
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


def test_no_duplicate_eval_ids(sample_db):
    rows = sample_db.execute("SELECT eval_id, COUNT(*) c FROM runs GROUP BY eval_id").fetchall()
    for row in rows:
        assert row["c"] == 1


def test_null_token_columns_when_unavailable(sample_db):
    # The sample logs carry no token/duration columns, so these must be NULL.
    row = sample_db.execute(
        "SELECT input_tokens, output_tokens, duration_s FROM runs LIMIT 1"
    ).fetchone()
    assert row["input_tokens"] is None
    assert row["output_tokens"] is None
    assert row["duration_s"] is None


def test_ingest_into_fresh_db(tmp_path):
    db_path = tmp_path / "fresh.db"
    inserted = ingest.ingest("sample_logs", db_path)
    assert inserted == 7
    conn = db.connect(db_path)
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "runs" in tables
    finally:
        db.close(conn)


def test_ingest_empty_dir(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    db_path = tmp_path / "empty.db"
    inserted = ingest.ingest(empty, db_path)
    assert inserted == 0
