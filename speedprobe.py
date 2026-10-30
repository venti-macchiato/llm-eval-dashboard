"""Single requests and concurrent batches for the speed probe.

One request records TTFT, prefill throughput, and generation throughput. A batch
fires ``concurrency`` requests at the endpoint simultaneously and aggregates
them: p50/p95 TTFT, mean per-request rates, and aggregate tokens/sec over wall
time (which is what a user actually experiences under load).
"""

from __future__ import annotations

import json
import math
import secrets
import statistics
import threading
import time

import httpx

OUTPUT_TOKENS = 200
CHARS_PER_TOKEN = 4


def _random_prefix() -> str:
    """Random prefix so repeat probes are not served from a response cache."""
    return secrets.token_urlsafe(24)


def _filler(prompt_tokens: int) -> str:
    """Build a prompt of roughly prompt_tokens tokens from filler text."""
    chars_needed = prompt_tokens * CHARS_PER_TOKEN
    base = "The quick brown fox jumps over the lazy dog. "
    repeat = max(1, chars_needed // len(base))
    return (base * repeat)[:chars_needed]


def percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile; None for an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(pct / 100 * len(ordered)) - 1))
    return ordered[index]


def probe_one(
    base_url: str,
    model_id: str,
    api_key: str,
    context_tokens: int,
    prefix: str | None = None,
) -> dict:
    """Run a single streaming probe for one context size."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    prompt = _random_prefix() if prefix is None else prefix
    prompt += _filler(context_tokens)
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": OUTPUT_TOKENS,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    start = time.perf_counter()
    first_token_time = None
    usage = None

    with httpx.stream("POST", url, json=payload, headers=headers, timeout=600.0) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            if line == "data: [DONE]":
                break
            if line.startswith("data: "):
                try:
                    data = json.loads(line[len("data: "):])
                except ValueError:
                    continue
                if usage is None and data.get("usage") is not None:
                    usage = data["usage"]
                for choice in data.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if delta.get("content") and first_token_time is None:
                        first_token_time = time.perf_counter()

    end = time.perf_counter()

    ttft = (first_token_time - start) if first_token_time is not None else None
    if usage is not None and usage.get("prompt_tokens") is not None:
        prompt_tokens = usage["prompt_tokens"]
    else:
        prompt_tokens = context_tokens
    # No usage means unknown, not fabricated.
    out_tokens = usage.get("completion_tokens") if usage is not None else None
    gen_seconds = (end - first_token_time) if first_token_time is not None else None

    return {
        "model": model_id,
        "ctx_tokens": context_tokens,
        "ttft_s": ttft,
        "prefill_tps": (prompt_tokens / ttft) if (ttft and ttft > 0) else None,
        "gen_tps": (out_tokens / gen_seconds) if (out_tokens is not None and gen_seconds and gen_seconds > 0) else None,
        "out_tokens": out_tokens,
        "prompt_tokens": prompt_tokens,
    }


def _aggregate(results: list[dict], wall_s: float, errors: int) -> dict:
    ttfts = [r["ttft_s"] for r in results if r.get("ttft_s") is not None]
    prefills = [r["prefill_tps"] for r in results if r.get("prefill_tps") is not None]
    gens = [r["gen_tps"] for r in results if r.get("gen_tps") is not None]
    outs = [r["out_tokens"] for r in results if r.get("out_tokens") is not None]
    total_out = sum(outs) if outs and len(outs) == len(results) and results else None
    mean_out = statistics.fmean(outs) if outs else None

    p50 = percentile(ttfts, 50)
    return {
        # ttft_s keeps the old single-request meaning; it is the p50 for batches.
        "ttft_s": p50,
        "ttft_p50": p50,
        "ttft_p95": percentile(ttfts, 95),
        "prefill_tps": statistics.fmean(prefills) if prefills else None,
        "gen_tps": statistics.fmean(gens) if gens else None,
        "agg_gen_tps": (total_out / wall_s) if (total_out is not None and wall_s > 0) else None,
        "out_tokens": int(round(mean_out)) if mean_out is not None else None,
        "requests": len(results),
        "errors": errors,
        "wall_s": wall_s,
    }


def probe_batch(
    base_url: str,
    model_id: str,
    api_key: str,
    context_tokens: int,
    concurrency: int = 1,
) -> dict:
    """Fire ``concurrency`` requests at once and aggregate their statistics."""
    concurrency = max(1, int(concurrency or 1))
    results: list[dict] = []
    errors: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            result = probe_one(base_url, model_id, api_key, context_tokens)
        except Exception as exc:  # noqa: BLE001 - one failure must not abort the batch
            with lock:
                errors.append(f"{type(exc).__name__}: {exc}")
            return
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(concurrency)]
    start = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.perf_counter() - start

    stats = _aggregate(results, wall, len(errors))
    stats["concurrency"] = concurrency
    return stats
