"""Tests for the demo seeder: tag scoping, formats, and idempotency."""

import db
import seed_demo


def _count(conn, sql):
    return conn.execute(sql).fetchone()[0]


def test_seed_and_clear_only_touch_demo_rows(tmp_path, monkeypatch):
    import config

    db_path = tmp_path / "bench.db"
    monkeypatch.setattr(config, "DB_PATH", str(db_path))
    conn = db.connect(db_path)
    db.init_schema(conn)
    conn.execute(
        """INSERT INTO runs (eval_id, task, model, created, score, stderr, samples)
           VALUES ('real-1', 'gsm8k', 'm', '2024-01-01 00:00:00+00:00', 0.5, 0.05, 10)"""
    )
    conn.execute(
        """INSERT INTO speed (model, ts, ctx_tokens, ttft_s)
           VALUES ('m', '2024-01-01T00:00:00', 2000, 0.2)"""
    )
    conn.commit()

    try:
        runs = seed_demo._seed_runs(conn)
        samples = seed_demo._seed_speed(conn)
        conn.commit()
        assert runs == 36
        assert samples == 36

        stamps = [
            row["created"]
            for row in conn.execute("SELECT created FROM runs WHERE eval_id LIKE 'demo-%'")
        ]
        assert all(stamp.endswith("+00:00") for stamp in stamps)
        ts = conn.execute("SELECT ts FROM speed WHERE batch_id LIKE 'demo-%'").fetchone()[0]
        assert "T" in ts and ts.count(":") == 2

        prompts = seed_demo._seed_prompts()
        assert prompts > 0
        assert _count(conn, "SELECT COUNT(*) FROM prompt_runs WHERE run_id LIKE 'demo-%'") == 2

        seed_demo._clear(conn)
        conn.commit()
        assert [row["eval_id"] for row in conn.execute("SELECT eval_id FROM runs")] == ["real-1"]
        assert _count(conn, "SELECT COUNT(*) FROM speed") == 1
        assert _count(conn, "SELECT COUNT(*) FROM prompt_runs") == 0

        # Re-seeding is idempotent.
        seed_demo._seed_runs(conn)
        seed_demo._seed_runs(conn)
        conn.commit()
        assert _count(conn, "SELECT COUNT(*) FROM runs WHERE eval_id LIKE 'demo-%'") == 36
    finally:
        db.close(conn)
