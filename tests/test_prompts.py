"""Tests for the custom prompt harness (prompts.py / promptharness.py).

A tiny fake OpenAI-compatible server streams canned chat completions keyed off
markers in the prompt. No test contacts a real model endpoint.
"""

import json
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

import promptharness
import prompts


def make_fake_app() -> FastAPI:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat_completions(request: dict):
        content = (request.get("messages") or [{}])[-1].get("content", "")
        if "[[json]]" in content:
            message = {
                "role": "assistant",
                "content": '```json\n{"name": "Ada", "age": 36, "city": "London"}\n```',
            }
        elif "[[tool]]" in content:
            message = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city": "Paris"}',
                        },
                    }
                ],
            }
        elif "Reference code:" in content:
            code = content.split("Reference code: ", 1)[1].split()[0]
            message = {"role": "assistant", "content": code}
        elif "[[refuse]]" in content:
            message = {"role": "assistant", "content": "I cannot help with that."}
        else:
            message = {"role": "assistant", "content": "PONG"}
        return {
            "id": "fake",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 5},
        }

    return app


@pytest.fixture
def fake_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    server = uvicorn.Server(
        uvicorn.Config(make_fake_app(), host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = None
    for _ in range(100):
        try:
            httpx.post(f"http://127.0.0.1:{port}/v1/chat/completions", json={})
            base_url = f"http://127.0.0.1:{port}/v1"
            break
        except Exception:
            time.sleep(0.05)
    assert base_url is not None, "fake server did not start"
    yield base_url
    server.should_exit = True
    thread.join(timeout=5)


def _test(test_id, prompt, check, **extra):
    return {
        "id": test_id,
        "title": test_id,
        "category": "custom",
        "prompt": prompt,
        "check": check,
        "max_tokens": 50,
        "temperature": 0,
        "context_tokens": 200,
        **extra,
    }


# --- checkers ---------------------------------------------------------------


def test_check_json_accepts_fenced_output_and_required_types():
    spec = {
        "type": "json",
        "required": ["name", "age"],
        "properties": {"name": "string", "age": "number"},
    }
    passed, detail = prompts.check(spec, '```json\n{"name": "Ada", "age": 36}\n```', None)
    assert passed, detail
    passed, detail = prompts.check(spec, '{"name": "Ada"}', None)
    assert not passed and "age" in detail
    passed, detail = prompts.check(spec, '{"name": "Ada", "age": "old"}', None)
    assert not passed and "age" in detail


def test_check_json_extracts_from_prose_but_rejects_non_objects():
    # Lenient about surrounding prose; strict about the root being an object.
    assert prompts.check({"type": "json", "required": []}, "sure: {}", None)[0] is True
    assert prompts.check({"type": "json", "required": []}, "[1, 2]", None)[0] is False
    assert prompts.check({"type": "json", "required": []}, "no braces", None)[0] is False


def test_check_tool_call():
    calls = [{"function": {"name": "get_weather", "arguments": '{"city": "Paris"}'}}]
    spec = {"type": "tool_call", "name": "get_weather", "required_args": ["city"]}
    assert prompts.check(spec, "", calls)[0] is True
    assert prompts.check(spec, "", [])[0] is False
    missing = [{"function": {"name": "get_weather", "arguments": "{}"}}]
    assert prompts.check(spec, "", missing)[0] is False


def test_check_refusal_and_recall():
    assert prompts.check({"type": "refusal"}, "I cannot help with that.", None)[0] is True
    assert prompts.check({"type": "refusal"}, "Sure, here is how.", None)[0] is False
    assert prompts.check({"type": "recall"}, "code is CODE-ABCD", None, "CODE-ABCD")[0] is True
    assert prompts.check({"type": "recall"}, "no idea", None, "CODE-ABCD")[0] is False
    assert prompts.check({"type": "recall"}, "anything", None, None)[0] is False


def test_check_text_rules():
    assert prompts.check({"type": "contains", "value": "pong"}, "PONG!")[0] is True
    assert prompts.check({"type": "not_contains", "value": ","}, "red; blue")[0] is True
    assert prompts.check({"type": "not_contains", "value": ","}, "red, blue")[0] is False
    assert prompts.check({"type": "equals", "value": " PONG "}, "pong")[0] is True
    assert prompts.check({"type": "max_words", "value": 3}, "one two three")[0] is True
    assert prompts.check({"type": "max_words", "value": 3}, "one two three four")[0] is False
    assert prompts.check({"type": "regex", "pattern": r"^\d{4}-\d{2}-\d{2}$"}, "2026-01-31")[0] is True
    assert prompts.check({"type": "regex", "pattern": r"^\d{4}$"}, "x")[0] is False


def test_check_refusal_any_of_string_is_one_phrase():
    spec = {"type": "refusal", "any_of": "cannot"}
    assert prompts.check(spec, "I cannot help with that.")[0] is True
    # The old bug iterated characters, so "c" matched any reply.
    assert prompts.check(spec, "Sure, here are the steps.")[0] is False


def test_check_unknown_type_fails_loudly():
    passed, detail = prompts.check({"type": "telepathy"}, "anything")
    assert passed is False
    assert "unknown check type" in detail


# --- loading ----------------------------------------------------------------


def test_load_validates_and_degrades(tmp_path):
    good = tmp_path / "prompts.yaml"
    good.write_text(
        """\
prompts:
  - {id: a, prompt: hi, check: {type: contains, value: h}}
  - {id: a, prompt: duplicate, check: {type: contains, value: h}}
  - {id: b, prompt: "", check: {type: contains, value: h}}
  - {id: c, prompt: hi, check: nonsense}
  - id: d
    title: "T"
    category: "cat"
    prompt: "reply"
    check: {type: equals, value: reply}
    system: "be terse"
"""
    )
    loaded = prompts.load(str(good))
    assert [item["id"] for item in loaded] == ["a", "d"]
    assert loaded[1]["title"] == "T"
    assert loaded[1]["system"] == "be terse"

    bad = tmp_path / "bad.yaml"
    bad.write_text("prompts: [unclosed\n")
    assert prompts.load(str(bad)) == []
    assert prompts.load(str(tmp_path / "missing.yaml")) == []


# --- runner + storage -------------------------------------------------------


def test_run_tests_against_fake_server(fake_server):
    tests = [
        _test("json", "[[json]] give me json", {"type": "json", "required": ["name", "age"]}),
        _test("tool", "[[tool]] weather", {"type": "tool_call", "name": "get_weather", "required_args": ["city"]}),
        _test("refuse", "[[refuse]] bad thing", {"type": "refusal"}),
        _test("pong", "say pong", {"type": "equals", "value": "PONG"}),
        _test("recall", "{context}", {"type": "recall"}),
    ]
    model = {"name": "m", "model_id": "test-model", "base_url": fake_server, "api_key_file": ""}
    progress = []
    results = promptharness.run_tests(
        model, tests, on_progress=lambda done, total, current: progress.append((done, total, current))
    )

    assert [row["test_id"] for row in results] == ["json", "tool", "refuse", "pong", "recall"]
    assert all(row["passed"] for row in results), [row["detail"] for row in results]
    assert all(row["input_tokens"] == 11 for row in results)
    assert progress[-1][:2] == (5, 5)
    assert all(row["latency_s"] >= 0 for row in results)


def test_run_tests_records_request_failure():
    tests = [_test("pong", "say pong", {"type": "equals", "value": "PONG"})]
    model = {"name": "m", "model_id": "x", "base_url": "http://127.0.0.1:1/v1", "api_key_file": ""}
    results = promptharness.run_tests(model, tests)
    assert results[0]["passed"] is False
    assert results[0]["error"]
    assert results[0]["detail"] == "request failed"


def test_save_and_recent_runs(tmp_path):
    db_path = tmp_path / "bench.db"
    results = [
        {"model": "m", "test_id": "a", "title": "A", "category": "cat", "repeat": 1,
         "passed": True, "output": "ok", "detail": "fine", "latency_s": 0.1,
         "input_tokens": 1, "output_tokens": 1, "error": None},
        {"model": "m", "test_id": "b", "title": "B", "category": "cat", "repeat": 1,
         "passed": False, "output": "no", "detail": "bad", "latency_s": 0.2,
         "input_tokens": 1, "output_tokens": 1, "error": None},
    ]
    promptharness.save_run(db_path, "run-1", "m", "2026-01-01T00:00:00", 1, results)

    runs = promptharness.recent_runs(db_path)
    assert len(runs) == 1
    run = runs[0]
    assert run["run_id"] == "run-1"
    assert run["tests"] == 2 and run["passed"] == 1 and run["errors"] == 0
    assert [row["test_id"] for row in run["results"]] == ["a", "b"]
    assert promptharness.recent_runs(db_path, model=["other"]) == []
    assert len(promptharness.recent_runs(db_path, run_id="run-1")) == 1


def test_load_degrades_on_non_numeric_fields(tmp_path):
    path = tmp_path / "prompts.yaml"
    path.write_text(
        """\
prompts:
  - id: bad_numbers
    prompt: hi
    check: {type: contains, value: h}
    max_tokens: lots
    temperature: warm
    context_tokens: many
"""
    )
    loaded = prompts.load(str(path))
    assert len(loaded) == 1
    assert loaded[0]["max_tokens"] == 512
    assert loaded[0]["temperature"] == 0.0
    assert loaded[0]["context_tokens"] == 2000


def test_prompt_run_refuses_while_eval_runs(monkeypatch):
    import evaljobs

    monkeypatch.setattr(evaljobs, "is_running", lambda: True)
    result = promptharness.start_run("polystrata-q3")
    assert result["started"] is False
    assert "eval" in result["reason"]
