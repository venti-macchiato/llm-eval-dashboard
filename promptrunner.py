"""Prompt request building and test execution against one model endpoint."""

from __future__ import annotations

import secrets
import time
from pathlib import Path

import httpx

import prompts


def _api_key(api_key_file: str | None) -> str:
    if not api_key_file:
        return ""
    try:
        return Path(api_key_file).expanduser().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _haystack(tokens: int, needle: str) -> str:
    """Filler text with the needle roughly in the middle."""
    line = "The archive index lists routine entries of little interest. "
    half = "".join([line] * max(1, (tokens * 2) // max(1, len(line) // 4) // 2))
    return f"{half}\nReference code: {needle}\n{half}"


def _messages(test: dict) -> tuple[list[dict], str | None]:
    prompt = test["prompt"]
    needle = None
    if test["check"].get("type") == "recall":
        needle = f"CODE-{secrets.token_hex(4).upper()}"
        prompt = prompt.replace("{context}", _haystack(test.get("context_tokens", 2000), needle))
        prompt = prompt.replace("{needle}", needle)
    messages = []
    if test.get("system"):
        messages.append({"role": "system", "content": test["system"]})
    messages.append({"role": "user", "content": prompt})
    return messages, needle


def _payload(test: dict, model_id: str, messages: list[dict]) -> dict:
    payload = {
        "model": model_id,
        "messages": messages,
        "max_tokens": test.get("max_tokens", 512),
        "temperature": test.get("temperature", 0),
        "stream": False,
    }
    if test.get("tools"):
        payload["tools"] = test["tools"]
    return payload


def _post(base_url: str, api_key: str, payload: dict) -> dict:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = httpx.post(url, json=payload, headers=headers, timeout=300.0)
    response.raise_for_status()
    return response.json()


def run_tests(
    model_cfg: dict,
    tests: list[dict],
    repeats: int = 1,
    on_progress=None,
    cancelled=None,
) -> list[dict]:
    """Run every test ``repeats`` times. Never raises per-test."""
    base_url = model_cfg.get("base_url") or ""
    model_name = model_cfg.get("name") or ""
    model_id = model_cfg.get("model_id") or model_name
    api_key = _api_key(model_cfg.get("api_key_file"))
    total = len(tests) * repeats
    done = 0
    results: list[dict] = []

    for repeat in range(1, repeats + 1):
        for test in tests:
            if cancelled and cancelled():
                return results
            started = time.perf_counter()
            row = {
                "model": model_name,
                "test_id": test["id"],
                "title": test["title"],
                "category": test["category"],
                "repeat": repeat,
                "passed": False,
                "output": None,
                "detail": None,
                "input_tokens": None,
                "output_tokens": None,
                "error": None,
            }
            try:
                messages, needle = _messages(test)
                data = _post(base_url, api_key, _payload(test, model_id, messages))
                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                output = message.get("content") or ""
                passed, detail = prompts.check(
                    test["check"], output, message.get("tool_calls"), needle
                )
                usage = data.get("usage") or {}
                row.update(
                    output=output,
                    passed=bool(passed),
                    detail=detail,
                    input_tokens=usage.get("prompt_tokens"),
                    output_tokens=usage.get("completion_tokens"),
                )
            except Exception as exc:  # noqa: BLE001 - one test must not abort the run
                row["detail"] = "request failed"
                row["error"] = f"{type(exc).__name__}: {exc}"
            row["latency_s"] = round(time.perf_counter() - started, 3)
            results.append(row)
            done += 1
            if on_progress:
                on_progress(done, total, test["id"])
    return results
