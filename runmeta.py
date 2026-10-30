"""Row coercion and provenance metadata for ingested eval logs.

Pandas hands back ``<NA>``/NaN sentinels and JSON-encoded columns, so ingest
cannot use the frame values directly. This module converts one ``evals_df`` row
into the values stored on a run, builds the ``meta`` JSON (endpoint, dataset,
sampling config, package versions, hardware), and merges later additions into
meta written by older versions.
"""

from __future__ import annotations

import json


def clean(value):
    """Drop pandas NA/NaN sentinels so JSON stays clean."""
    if value is None:
        return None
    try:
        if value != value:  # NaN
            return None
    except (TypeError, ValueError):
        pass
    if str(value) in ("<NA>", "NaT", "nan", "None"):
        return None
    return value


def jsonish(value):
    """Parse JSON-encoded columns (packages, generate config) when possible."""
    value = clean(value)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def num(value):
    """Coerce to int/float, or None when the value is not numeric."""
    value = clean(value)
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def meta_for(row, model_cfg: dict | None, hw: dict | None = None) -> str | None:
    """Provenance for a run: endpoint, dataset, sampling, packages, hardware."""
    model_cfg = model_cfg or {}
    meta = {
        "base_url": clean(model_cfg.get("base_url")),
        "model_id": clean(model_cfg.get("model_id")),
        "inspect_model": clean(row.get("model")),
        "base_model": clean(model_cfg.get("base_model")),
        "dataset": clean(row.get("dataset_name")),
        "epochs": num(row.get("epochs")),
        "generate_config": jsonish(row.get("model_generate_config")),
        "packages": jsonish(row.get("packages")),
        "git_commit": clean(row.get("git_commit")),
        "total_samples": num(row.get("total_samples")),
        "completed_samples": num(row.get("completed_samples")),
        "hardware": hw,
    }
    meta = {key: value for key, value in meta.items() if value is not None}
    return json.dumps(meta, default=str) if meta else None


def merge_meta(prior: str | None, incoming: str | None) -> str | None:
    """Enrich a stored row's meta with hardware evidence it predates.

    Only the ``hardware`` key is merged (the other fields were already
    backfilled); everything else is left byte-identical so a second ingest of
    unchanged logs stays a no-op.
    """
    if not incoming:
        return prior
    if not prior:
        return incoming
    try:
        old = json.loads(prior)
        new = json.loads(incoming)
    except ValueError:
        return prior
    if not isinstance(old, dict) or not isinstance(new, dict):
        return prior
    if "hardware" in old or "hardware" not in new:
        return prior
    merged = dict(old)
    merged["hardware"] = new["hardware"]
    return json.dumps(merged, default=str)


def error_samples(row) -> int:
    """Samples that never completed, from the log's total/completed counts."""
    total = num(row.get("total_samples"))
    completed = num(row.get("completed_samples"))
    if total is None or completed is None:
        return 0
    return max(0, int(total) - int(completed))
