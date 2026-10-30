"""Tests for variant families and baseline regressions (variants.py)."""

import json
import math

import pytest

import variants


def group(model, task, score, stderr, k=1, samples=20, config=None, meta=None):
    cfg = config or {}
    return {
        "model": model,
        "task": task,
        "score": score,
        "stderr": stderr,
        "k": k,
        "samples": samples,
        "config": cfg,
        "config_key": json.dumps(cfg, sort_keys=True),
        "ci_low": None,
        "ci_high": None,
        "eval_id": f"{model}-{task}",
        "last": "2024-01-01T00:00:00",
        "meta": json.dumps(meta) if meta else None,
    }


def model(name, base=None, baseline=False, **hardware):
    entry = {"name": name}
    if base:
        entry["base_model"] = base
    if baseline:
        entry["baseline"] = True
    if hardware:
        entry["hardware"] = hardware
    return entry


MODELS = [
    model("m-q3", base="m", quant="Q3"),
    model("m-q5", base="m", baseline=True, quant="Q5"),
    model("other"),
]
GROUPS = [
    group("m-q3", "t", 0.6, 0.02),
    group("m-q5", "t", 0.7, 0.02),
    group("other", "t", 0.5, 0.02),
]


def test_families_follow_base_model_and_config_order():
    out = variants.build(MODELS, GROUPS)
    assert [f["base_model"] for f in out["families"]] == ["m", "other"]
    fam = out["families"][0]
    assert [v["model"] for v in fam["variants"]] == ["m-q3", "m-q5"]
    assert fam["baseline"] == "m-q5"
    assert fam["variants"][1]["is_baseline"] is True
    assert fam["variants"][0]["config"] == {"quant": "Q3"}
    assert out["families"][1]["baseline"] == "other"


def test_baseline_override_changes_the_reference():
    out = variants.build(MODELS, GROUPS, baseline="m-q3")
    fam = out["families"][0]
    assert fam["baseline"] == "m-q3"
    reg = fam["regressions"]["m-q5"]["t"]
    assert reg["delta"] == pytest.approx(0.1)
    assert reg["se"] == pytest.approx(math.hypot(0.02, 0.02))
    assert reg["within_noise"] is False


def test_regression_within_noise():
    groups = [group("a", "t", 0.6, 0.05), group("b", "t", 0.65, 0.05)]
    models = [model("a", base="f", baseline=True), model("b", base="f")]
    fam = variants.build(models, groups)["families"][0]
    reg = fam["regressions"]["b"]["t"]
    assert reg["delta"] == pytest.approx(0.05)
    assert reg["within_noise"] is True


def test_missing_stderr_is_unresolved_not_significant():
    groups = [group("a", "t", 0.6, 0.02), group("b", "t", 0.9, None)]
    models = [model("a", base="f", baseline=True), model("b", base="f")]
    reg = variants.build(models, groups)["families"][0]["regressions"]["b"]["t"]
    assert reg["se"] is None
    assert reg["ci_low"] is None
    assert reg["within_noise"] is None


def test_zero_interval_cannot_resolve_a_difference():
    groups = [group("a", "t", 0.8, 0.0), group("b", "t", 0.9, 0.0)]
    models = [model("a", base="f", baseline=True), model("b", base="f")]
    reg = variants.build(models, groups)["families"][0]["regressions"]["b"]["t"]
    assert reg["se"] == 0.0
    assert reg["within_noise"] is None


def test_identical_zero_interval_is_within_noise():
    groups = [group("a", "t", 0.8, 0.0), group("b", "t", 0.8, 0.0)]
    models = [model("a", base="f", baseline=True), model("b", base="f")]
    reg = variants.build(models, groups)["families"][0]["regressions"]["b"]["t"]
    assert reg["delta"] == 0.0
    assert reg["within_noise"] is True


def test_unconfigured_model_gets_its_own_family():
    groups = [group("ghost", "t", 0.4, 0.02, config={"hardware": {"quant": "Q2"}})]
    out = variants.build([model("m")], groups)
    ghost = next(f for f in out["families"] if f["base_model"] == "ghost")
    assert ghost["variants"] == [
        {"model": "ghost", "config": {"quant": "Q2"}, "configured_baseline": False, "is_baseline": True}
    ]


def test_missing_task_cell_and_regression_are_none():
    groups = [group("a", "t", 0.6, 0.02)]
    models = [model("a", base="f", baseline=True), model("b", base="f")]
    fam = variants.build(models, groups)["families"][0]
    assert fam["tasks"] == ["t"]
    assert fam["cells"]["b"]["t"] is None
    assert fam["regressions"]["b"]["t"] is None


def test_tasks_are_the_union_across_variants():
    groups = [
        group("a", "x", 0.6, 0.02),
        group("b", "y", 0.7, 0.02),
        group("b", "x", 0.65, 0.02),
    ]
    models = [model("a", base="f", baseline=True), model("b", base="f")]
    fam = variants.build(models, groups)["families"][0]
    assert fam["tasks"] == ["x", "y"]
    assert fam["cells"]["a"]["y"] is None


def test_unconfigured_model_joins_family_from_meta():
    groups = [
        group("demo-q5", "t", 0.9, 0.02, meta={"base_model": "f"}),
    ]
    models = [model("base", base="f", baseline=True)]
    fam = variants.build(models, groups)["families"][0]
    assert fam["base_model"] == "f"
    assert [v["model"] for v in fam["variants"]] == ["base", "demo-q5"]
