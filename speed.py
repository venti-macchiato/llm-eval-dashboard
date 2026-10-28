"""Speed probe for OpenAI-compatible endpoints.

For each context size (default [2000, 16000, 64000]) send ONE streaming
/chat/completions request asking for ~200 output tokens. Record:

  * TTFT      - time from request start to first content chunk
  * prefill_tps - prompt_tokens / TTFT (usage if server returns it, else estimate)
  * gen_tps   - output_tokens / (end - first_token_time)

Requests run serially (the server handles one at a time). Probe runs in a
background thread via start_probe(); only one probe runs at a time.
"""

from __future__ import annotations

import time
import threading
from pathlib import Path

import httpx

DEFAULT_CONTEXT_SIZES = [2000, 16000, 64000]
OUTPUT_TOKENS = 200
CHARS_PER_TOKEN = 4

_lock = threading.Lock()
_running = False


def _filler(prompt_tokens: int) -> str:
    """Build a prompt of roughly prompt_tokens tokens from filler text."""
    chars_needed = prompt_tokens * CHARS_PER_TOKEN
    # ~4 chars per token on average for English-ish filler.
    base = "The quick brown fox jumps over the lazy dog. "
    repeat = max(1, chars_needed // len(base))
    text = (base * repeat)[:chars_needed]
    return text


def _read_api_key(api_key_file: str) -> str:
    """Read an API key from a file, expanding ~ to the user's HOME."""
    path = Path(api_key_file).expanduser()
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read().strip()


def probe_one(
    base_url: str,
    model_id: str,
    api_key: str,
    context_tokens: int,
) -> dict:
    """Run a single streaming probe for one context size.

    Returns a dict with keys: model, ts, ctx_tokens, ttft_s, prefill_tps,
    gen_tps, out_tokens.
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    prompt = _filler(context_tokens)
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
    out_tokens = 0

    with httpx.stream("POST", url, json=payload, headers=headers, timeout=600.0) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            if line == "data: [DONE]":
                break
            if line.startswith("data: "):
                chunk = line[len("data: "):]
                try:
                    import json

                    data = json.loads(chunk)
                except ValueError:
                    continue
                # Usage can arrive in a chunk with no content choices.
                if usage is None and data.get("usage") is not None:
                    usage = data["usage"]
                choices = data.get("choices") or []
                for choice in choices:
                    delta = choice.get("delta") or {}
                    if delta.get("content") and first_token_time is None:
                        first_token_time = time.perf_counter()

    end = time.perf_counter()

    ttft = (first_token_time - start) if first_token_time is not None else None
    if usage is not None and usage.get("prompt_tokens") is not None:
        prompt_tokens = usage["prompt_tokens"]
    else:
        prompt_tokens = context_tokens

    prefill_tps = (prompt_tokens / ttft) if (ttft and ttft > 0) else None
    gen_seconds = (end - first_token_time) if first_token_time is not None else None

    if usage is not None and usage.get("completion_tokens") is not None:
        out_tokens = usage["completion_tokens"]
    else:
        out_tokens = round(context_tokens / CHARS_PER_TOKEN)

    gen_tps = (out_tokens / gen_seconds) if (gen_seconds and gen_seconds > 0) else None

    return {
        "model": model_id,
        "ctx_tokens": context_tokens,
        "ttft_s": ttft,
        "prefill_tps": prefill_tps,
        "gen_tps": gen_tps,
        "out_tokens": out_tokens,
    }


def run_probe(models: list[dict], context_sizes: list[int] | None = None) -> list[dict]:
    """Probe all models serially. Returns list of probe results."""
    sizes = context_sizes or DEFAULT_CONTEXT_SIZES
    results = []
    for model in models:
        api_key = _read_api_key(model["api_key_file"])
        for ctx in sizes:
            result = probe_one(
                model["base_url"], model["model_id"], api_key, ctx
            )
            result["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            results.append(result)
    return results



def start_probe() -> bool:
    """Run the probe for all configured models in a background thread.

    Returns True if a probe was started, False if one is already running.
    """
    global _running
    if not _lock.acquire(blocking=False):
        return False
    _running = True

    def _worker():
        try:
            from config import DB_PATH, MODELS
            import db

            results = run_probe(MODELS)
            conn = db.connect(DB_PATH)
            try:
                for r in results:
                    conn.execute(
                        """INSERT INTO speed
                           (model, ts, ctx_tokens, ttft_s, prefill_tps, gen_tps, out_tokens)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            r["model"],
                            r["ts"],
                            r["ctx_tokens"],
                            r["ttft_s"],
                            r["prefill_tps"],
                            r["gen_tps"],
                            r["out_tokens"],
                        ),
                    )
                conn.commit()
            finally:
                db.close(conn)
        finally:
            global _running
            _running = False
            _lock.release()

    threading.Thread(target=_worker, daemon=True).start()
    return True
