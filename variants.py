"""Group model variants under a base model and regress them on a baseline.

A *variant* is one configured model entry (``models[].name``): q4/q5/q8 or
different context sizes are separate entries that share ``base_model``. For each
variant the best-supported pooled group per task is used (the same rule as the
Leaderboard), and the difference from the family's baseline is reported as a
pooled delta with its own standard error.

The delta SE is ``sqrt(se_variant^2 + se_baseline^2)`` because the two pooled
means are independent. A zero interval cannot resolve a non-zero delta, so the
result then says "unknown" rather than "outside noise".
"""

from __future__ import annotations

import json
import math

import aggregate
import hardware

Z = 1.96


def _regression(cell: dict | None, base: dict | None) -> dict | None:
    """Delta of one variant cell against the baseline cell for the same task."""
    if not cell or not base:
        return None
    score, base_score = cell.get("score"), base.get("score")
    if score is None or base_score is None:
        return None

    delta = score - base_score
    se_variant, se_base = cell.get("stderr"), base.get("stderr")
    se = math.hypot(se_variant, se_base) if se_variant is not None and se_base is not None else None
    if se is None:
        within = None
    elif se == 0:
        within = True if delta == 0 else None
    else:
        within = abs(delta) <= Z * se
    half = Z * se if se is not None else None

    return {
        "delta": delta,
        "se": se,
        "ci_low": (delta - half) if half is not None else None,
        "ci_high": (delta + half) if half is not None else None,
        "within_noise": within,
        "variant_score": score,
        "variant_se": se_variant,
        "baseline_score": base_score,
        "baseline_se": se_base,
    }


def _family_from_meta(group: dict) -> str | None:
    """A run can declare its family in meta.base_model (ad-hoc endpoints)."""
    raw = group.get("meta")
    if not raw:
        return None
    try:
        meta = json.loads(raw)
    except (TypeError, ValueError):
        return None
    base = meta.get("base_model") if isinstance(meta, dict) else None
    return base.strip() if isinstance(base, str) and base.strip() else None


def _resolve_baseline(variants: list[dict], override: str | None) -> str | None:
    names = [v["model"] for v in variants]
    if override in names:
        return override
    configured = next((v["model"] for v in variants if v.get("configured_baseline")), None)
    return configured or (names[0] if names else None)


def build(
    models: list[dict], groups: list[dict], baseline: str | None = None
) -> dict:
    """Payload for the Variants view from configured models and pooled groups."""
    families: dict[str, dict] = {}

    def family(base: str) -> dict:
        return families.setdefault(base, {"base_model": base, "variants": []})

    configured: set[str] = set()
    for model in models:
        name = model.get("name")
        if not name or name in configured:
            continue
        configured.add(name)
        family(model.get("base_model") or name)["variants"].append(
            {
                "model": name,
                "config": hardware.declared(model),
                "configured_baseline": bool(model.get("baseline")),
            }
        )

    best = aggregate.best_from_groups(groups)
    for (model, _task), group in best.items():
        if model in configured:
            continue
        # A run whose model is not configured still gets a family, either the
        # one declared in its meta.base_model or its own.
        configured.add(model)
        declared = (group.get("config") or {}).get("hardware") or {}
        family(_family_from_meta(group) or model)["variants"].append(
            {"model": model, "config": declared, "configured_baseline": False}
        )

    out = []
    for base, fam in families.items():
        variants = fam["variants"]
        names = [v["model"] for v in variants]
        chosen = _resolve_baseline(variants, baseline)
        tasks = sorted({task for (model, task) in best if model in names})
        cells = {
            v["model"]: {task: best.get((v["model"], task)) for task in tasks}
            for v in variants
        }
        regressions = {
            v["model"]: {
                task: _regression(
                    best.get((v["model"], task)), best.get((chosen, task)) if chosen else None
                )
                for task in tasks
            }
            for v in variants
        }
        out.append(
            {
                "base_model": base,
                "baseline": chosen,
                "variants": [
                    {**v, "is_baseline": v["model"] == chosen} for v in variants
                ],
                "tasks": tasks,
                "cells": cells,
                "regressions": regressions,
            }
        )
    return {"families": out}
