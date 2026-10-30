"""Pool repeated eval runs of the same configuration into one estimate.

A single run's headline stderr reflects dataset sampling only. When a task is
run several times, run-to-run variance (seeds, sampler, server state) matters
too, so pooling treats each run as one estimate and combines both components:

* ``k == 1`` - the run's own score and stderr, unchanged.
* ``k > 1``  - unweighted mean of the run scores, with
  ``se = sqrt((var(scores) + mean(se_i^2)) / k)``: the between-run variance plus
  the average within-run sampling variance, divided by the number of runs
  (standard error of the mean of k independent estimates).

Identical repeats therefore keep a non-zero interval from each run's own stderr
instead of claiming perfect certainty.

Runs are grouped by (model, task, configuration, sample count), where the
configuration is the declared hardware plus inspect's generate config. A quant,
context-size, or sampling change starts a new group instead of being averaged
into the old one; so does a different limit, because it covers a different
slice of the dataset.
"""

from __future__ import annotations

import json
import math
import statistics


def _meta(run: dict) -> dict:
    raw = run.get("meta")
    if not raw:
        return {}
    try:
        meta = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return meta if isinstance(meta, dict) else {}


def config_of(run: dict) -> dict:
    """The parts of a run's provenance that make its score comparable."""
    meta = _meta(run)
    out: dict = {}
    hardware = meta.get("hardware")
    declared = hardware.get("declared") if isinstance(hardware, dict) else None
    if isinstance(declared, dict) and declared:
        out["hardware"] = declared
    generate = meta.get("generate_config")
    if isinstance(generate, dict) and generate:
        out["generate_config"] = generate
    # `samples` already folds epochs in (inspect reports len(dataset) * epochs),
    # so record epochs explicitly to keep limit/epochs combinations apart.
    try:
        epochs = int(meta.get("epochs") or 1)
    except (TypeError, ValueError):
        epochs = 1
    if epochs > 1:
        out["epochs"] = epochs
    return out


def config_fingerprint(config: dict) -> str:
    return json.dumps(config, sort_keys=True, default=str) if config else ""


def _total(runs: list[dict], key: str):
    values = [r[key] for r in runs if r.get(key) is not None]
    return sum(values) if values else None


def _samples(runs: list[dict]):
    values = [r["samples"] for r in runs if r.get("samples") is not None]
    return max(values) if values else None


def pool(runs: list[dict]) -> dict:
    """Score, stderr, and 95% CI for one or more runs of the same config."""
    scored = [r for r in runs if r.get("score") is not None]
    scores = [float(r["score"]) for r in scored]
    k = len(scores)

    if k == 0:
        score = se = None
    elif k == 1:
        score = scores[0]
        se = next((r.get("stderr") for r in scored if r.get("stderr") is not None), None)
    else:
        score = sum(scores) / k
        errs = [float(r["stderr"]) ** 2 for r in scored if r.get("stderr") is not None]
        between = statistics.variance(scores)
        if errs:
            se = math.sqrt((between + statistics.fmean(errs)) / k)
        else:
            # No run reports sampling error: only run-to-run spread is
            # observable, and zero spread means unknown, not certain.
            se = math.sqrt(between / k) if between else None

    half = 1.96 * se if se is not None else None
    return {
        "score": score,
        "stderr": se,
        "ci_low": (score - half) if (score is not None and half is not None) else None,
        "ci_high": (score + half) if (score is not None and half is not None) else None,
        "k": k,
        "scores": scores,
        "samples": _samples(runs),
        "total_samples": _total(runs, "samples"),
        "input_tokens": _total(runs, "input_tokens"),
        "output_tokens": _total(runs, "output_tokens"),
        "duration_s": _total(runs, "duration_s"),
        "error_samples": sum(
            r["error_samples"] for r in runs if r.get("error_samples") is not None
        ),
        "eval_ids": [r["eval_id"] for r in runs if r.get("eval_id")],
        "first": min((r["created"] for r in runs if r.get("created")), default=None),
        "last": max((r["created"] for r in runs if r.get("created")), default=None),
    }


def groups(runs: list[dict]) -> list[dict]:
    """Group runs by model/task/configuration/sample count and pool each group.

    The sample count is part of the key: a 5-sample run and a 50-sample run
    cover different slices of the dataset, so averaging them would change what
    the score means. Repeats of the same limit are pooled.

    ``runs`` must be ordered newest-first (as the API returns them); the newest
    member is the representative ``eval_id``/``log_path`` for drilldown.
    """
    buckets: dict[tuple[str, str, str, int], list[dict]] = {}
    for run in runs:
        config = config_of(run)
        key = (
            run.get("model", ""),
            run.get("task", ""),
            config_fingerprint(config),
            int(run.get("samples") or 0),
        )
        buckets.setdefault(key, []).append(run)

    out = []
    for (model, task, fingerprint, _samples), members in buckets.items():
        members.sort(key=lambda r: r.get("created") or "", reverse=True)
        newest = members[0]
        pooled = pool(members)
        pooled.update(
            {
                "model": model,
                "task": task,
                "config": config_of(newest),
                "config_key": fingerprint,
                "eval_id": newest.get("eval_id"),
                "log_path": newest.get("log_path"),
                "created": newest.get("created"),
                "meta": newest.get("meta"),
            }
        )
        out.append(pooled)

    out.sort(key=lambda g: (g["last"] or "", g["model"], g["task"]), reverse=True)
    return out


def best_from_groups(grouped: list[dict]) -> dict[tuple[str, str], dict]:
    """The best-supported group per (model, task).

    Keeps the newest configuration, then the largest sample count within it:
    a 1-sample smoke run must not become headline evidence. ``grouped`` must be
    newest-first (as :func:`groups` returns).
    """
    pairs: dict[tuple[str, str], list[dict]] = {}
    for group in grouped:
        pairs.setdefault((group["model"], group["task"]), []).append(group)
    best: dict[tuple[str, str], dict] = {}
    for key, members in pairs.items():
        newest_config = members[0]["config_key"]
        same_config = [m for m in members if m["config_key"] == newest_config]
        best[key] = max(
            same_config,
            key=lambda m: (m["samples"] or 0, m["last"] or ""),
        )
    return best
