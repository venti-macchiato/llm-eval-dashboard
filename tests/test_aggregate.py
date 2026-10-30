"""Tests for pooling repeated runs (aggregate.py)."""

import json
import math

import pytest

import aggregate


def make_run(
    eval_id,
    score,
    stderr,
    created="2024-01-01T00:00:00",
    hardware=None,
    generate_config=None,
    model="m",
    task="t",
    samples=100,
    epochs=None,
):
    meta = {}
    if hardware is not None:
        meta["hardware"] = {"declared": hardware}
    if generate_config is not None:
        meta["generate_config"] = generate_config
    if epochs is not None:
        meta["epochs"] = epochs
    return {
        "eval_id": eval_id,
        "model": model,
        "task": task,
        "created": created,
        "score": score,
        "stderr": stderr,
        "samples": samples,
        "input_tokens": 10,
        "output_tokens": 5,
        "duration_s": 1.0,
        "error_samples": 0,
        "meta": json.dumps(meta) if meta else None,
    }


def test_single_run_keeps_its_own_stderr():
    pooled = aggregate.pool([make_run("e1", 0.8, 0.03)])
    assert pooled["k"] == 1
    assert pooled["score"] == 0.8
    assert pooled["stderr"] == 0.03
    assert pooled["ci_low"] == pytest.approx(0.8 - 1.96 * 0.03)


def test_repeats_pool_mean_and_between_run_error():
    pooled = aggregate.pool(
        [
            make_run("e1", 0.6, 0.05),
            make_run("e2", 0.7, 0.05),
            make_run("e3", 0.8, 0.05),
        ]
    )
    # var(scores) plus the average within-run variance, over k runs.
    se = math.sqrt((0.01 + 0.05**2) / 3)
    assert pooled["k"] == 3
    assert pooled["score"] == pytest.approx(0.7)
    assert pooled["stderr"] == pytest.approx(se)
    assert pooled["stderr"] != pytest.approx(0.05)
    assert pooled["ci_low"] == pytest.approx(0.7 - 1.96 * se)


def test_identical_repeats_keep_within_run_error():
    """No between-run spread, but each run still carries sampling error."""
    pooled = aggregate.pool([make_run("e1", 0.9, 0.01), make_run("e2", 0.9, 0.01)])
    assert pooled["score"] == 0.9
    assert pooled["stderr"] == pytest.approx(math.sqrt(0.01**2 / 2))
    assert pooled["ci_low"] < 0.9 < pooled["ci_high"]


def test_missing_scores_are_ignored():
    pooled = aggregate.pool([make_run("e1", None, None), make_run("e2", 0.5, 0.02)])
    assert pooled["k"] == 1
    assert pooled["score"] == 0.5


def test_empty_pool():
    pooled = aggregate.pool([make_run("e1", None, None)])
    assert pooled["k"] == 0
    assert pooled["score"] is None
    assert pooled["stderr"] is None
    assert pooled["ci_low"] is None


def test_groups_split_by_declared_hardware():
    rows = [
        make_run("e3", 0.8, 0.02, created="2024-01-03T00:00:00", hardware={"quant": "Q5"}),
        make_run("e2", 0.7, 0.02, created="2024-01-02T00:00:00", hardware={"quant": "Q3"}),
        make_run("e1", 0.6, 0.02, created="2024-01-01T00:00:00", hardware={"quant": "Q3"}),
    ]
    grouped = aggregate.groups(rows)
    assert len(grouped) == 2
    q3 = next(g for g in grouped if g["config"]["hardware"]["quant"] == "Q3")
    assert q3["k"] == 2
    assert q3["score"] == pytest.approx(0.65)
    # Newest member represents the group for drilldown.
    assert q3["eval_id"] == "e2"
    assert q3["eval_ids"] == ["e2", "e1"]


def test_groups_split_by_generate_config():
    rows = [
        make_run("e2", 0.7, 0.02, created="2024-01-02T00:00:00", generate_config={"temperature": 0.0}),
        make_run("e1", 0.5, 0.02, created="2024-01-01T00:00:00", generate_config={"temperature": 0.7}),
    ]
    grouped = aggregate.groups(rows)
    assert len(grouped) == 2
    assert all(g["k"] == 1 for g in grouped)


def test_groups_pool_unlabelled_runs_together():
    rows = [
        make_run("e2", 0.7, 0.02, created="2024-01-02T00:00:00"),
        make_run("e1", 0.5, 0.02, created="2024-01-01T00:00:00"),
    ]
    grouped = aggregate.groups(rows)
    assert len(grouped) == 1
    assert grouped[0]["k"] == 2
    assert grouped[0]["score"] == pytest.approx(0.6)
    assert grouped[0]["config"] == {}


def test_groups_split_by_sample_count():
    """A 5-sample run and a 20-sample run cover different dataset slices."""
    rows = [
        make_run("e2", 1.0, 0.0, created="2024-01-02T00:00:00", samples=5),
        make_run("e1", 0.9, 0.03, created="2024-01-01T00:00:00", samples=20),
    ]
    grouped = aggregate.groups(rows)
    assert len(grouped) == 2
    assert sorted(g["samples"] for g in grouped) == [5, 20]


def test_missing_stderr_never_fabricates_zero_interval():
    """Two identical repeats with no stderr: unknown, not certain."""
    pooled = aggregate.pool([make_run("e1", 0.8, None), make_run("e2", 0.8, None)])
    assert pooled["score"] == 0.8
    assert pooled["stderr"] is None
    assert pooled["ci_low"] is None


def test_missing_stderr_keeps_between_run_spread():
    pooled = aggregate.pool([make_run("e1", 0.7, None), make_run("e2", 0.9, None)])
    assert pooled["stderr"] == pytest.approx(math.sqrt(0.02 / 2))


def test_epochs_separate_groups_with_the_same_sample_count():
    """limit 10 x epochs 2 and limit 20 x epochs 1 cover different slices."""
    rows = [
        make_run("e2", 0.8, 0.02, created="2024-01-02T00:00:00", samples=20, epochs=2),
        make_run("e1", 0.8, 0.02, created="2024-01-01T00:00:00", samples=20),
    ]
    grouped = aggregate.groups(rows)
    assert len(grouped) == 2
    assert any(g["config"].get("epochs") == 2 for g in grouped)
