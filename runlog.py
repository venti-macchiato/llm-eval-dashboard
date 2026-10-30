"""Per-sample analysis of an inspect ``.eval`` log.

The dashboard stores one headline score per run; this module opens the log on
demand so the UI can show *which* samples failed and why.
"""

from __future__ import annotations


def log_stats(log_path) -> tuple[int | None, int | None, float | None]:
    """Token totals and duration from an .eval log. Best-effort."""
    if not log_path:
        return None, None, None
    try:
        from datetime import datetime

        from inspect_ai.log import read_eval_log

        stats = read_eval_log(str(log_path)).stats
        usage = getattr(stats, "model_usage", None) or {}
        input_tokens = sum(getattr(u, "input_tokens", 0) or 0 for u in usage.values())
        output_tokens = sum(getattr(u, "output_tokens", 0) or 0 for u in usage.values())
        duration = None
        start = getattr(stats, "started_at", None)
        end = getattr(stats, "completed_at", None)
        if start and end:
            delta = datetime.fromisoformat(str(end)) - datetime.fromisoformat(str(start))
            duration = delta.total_seconds()
        return input_tokens or None, output_tokens or None, duration
    except Exception:  # noqa: BLE001 - enrichment is best-effort
        return None, None, None


def _text(value, limit: int = 500) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _score(sample) -> float | None:
    from inspect_ai.scorer import CORRECT, INCORRECT, NOANSWER, PARTIAL

    scores = getattr(sample, "scores", None) or {}
    for score in scores.values():
        value = getattr(score, "value", None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    # Multiple-choice / classification scorers report a status code, not a
    # number: CORRECT='C', INCORRECT='I', NOANSWER='N', PARTIAL='P'.
    status_map = {CORRECT: 1.0, INCORRECT: 0.0, NOANSWER: 0.0, PARTIAL: 0.5}
    for score in scores.values():
        value = getattr(score, "value", None)
        if isinstance(value, str) and value in status_map:
            return status_map[value]
        # Dict-valued scorers (e.g. IFEval) report per-sample booleans; the
        # headline metric is prompt-level strict adherence.
        if isinstance(value, dict):
            for key in ("prompt_level_strict", "inst_level_strict"):
                flag = value.get(key)
                if isinstance(flag, (bool, int)):
                    return 1.0 if flag else 0.0
    return None


def _error(sample) -> str | None:
    error = getattr(sample, "error", None)
    if error is None:
        return None
    return _text(getattr(error, "message", None) or str(error), 300)


def _output(sample) -> str | None:
    output = getattr(sample, "output", None)
    completion = getattr(output, "completion", None)
    return _text(completion, 500) if isinstance(completion, str) else None


def sample_report(
    log_path: str,
    limit: int = 100,
    offset: int = 0,
    failures_only: bool = False,
) -> dict:
    """Return aggregate stats plus a page of samples for one eval log.

    Raises if the log cannot be read; callers translate that into an HTTP
    error. When the log was written with ``--no-log-samples`` the sample list
    is empty and ``has_samples`` is False.
    """
    from inspect_ai.log import read_eval_log

    log = read_eval_log(str(log_path))
    samples = list(getattr(log, "samples", None) or [])

    errors = 0
    scored = 0
    score_sum = 0.0
    failures = 0
    matched = 0
    rows: list[dict] = []
    for index, sample in enumerate(samples):
        error = _error(sample)
        score = None if error else _score(sample)
        if error:
            errors += 1
        if score is not None:
            scored += 1
            score_sum += score
        failed = bool(error) or score == 0
        if failed:
            failures += 1
        if failures_only and not failed:
            continue
        if offset <= matched < offset + limit:
            rows.append(
                {
                    "id": getattr(sample, "id", index),
                    "epoch": getattr(sample, "epoch", None),
                    "score": score,
                    "error": error,
                    "input": _text(getattr(sample, "input", None)),
                    "target": _text(getattr(sample, "target", None)),
                    "output": _output(sample),
                }
            )
        matched += 1

    return {
        "total": len(samples),
        "scored": scored,
        "errors": errors,
        "failures": failures,
        "mean_score": (score_sum / scored) if scored else None,
        "has_samples": bool(samples),
        "offset": offset,
        "limit": limit,
        "failures_only": failures_only,
        "filtered_total": matched,
        "samples": rows,
    }
