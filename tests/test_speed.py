"""Tests for speed.py using a fake local streaming HTTP server.

The fake server is a tiny FastAPI/ASGI app run by uvicorn in a background
thread on a real localhost socket. It streams a canned chat/completions
SSE response. Tests NEVER contact the real endpoint; they point probe_one()
at the fake server's base_url.
"""

import asyncio
import json
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

import speed


def _sse_chunk(payload: dict) -> str:
    return "data: " + json.dumps(payload) + "\n\n"


def make_fake_app(first_chunk_delay: float = 0.05) -> FastAPI:
    """Build an ASGI app that streams a canned completion.

    Waits first_chunk_delay, emits one content delta, then a usage chunk,
    then [DONE]. The delay lets us verify TTFT is measured.
    """
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat_completions(request: dict):
        async def generate():
            await asyncio.sleep(first_chunk_delay)
            prompt_text = request.get("messages", [{}])[0].get("content", "")
            prompt_tokens = max(1, len(prompt_text) // 4)
            yield _sse_chunk(
                {
                    "id": "fake-1",
                    "object": "chat.completion.chunk",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": "hello"},
                        }
                    ],
                }
            )
            # Usage chunk (stream_options include_usage).
            yield _sse_chunk(
                {
                    "id": "fake-1",
                    "object": "chat.completion.chunk",
                    "choices": [],
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": 1,
                        "total_tokens": prompt_tokens + 1,
                    },
                }
            )
            yield _sse_chunk({"id": "fake-1", "choices": []})
            yield "data: [DONE]\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    return app


@pytest.fixture
def fake_server():
    # Reserve a free port with a raw socket, then run uvicorn on it.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    app = make_fake_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

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


def test_probe_one_records_metrics(fake_server):
    result = speed.probe_one(
        base_url=fake_server,
        model_id="test-model",
        api_key="fake-key",
        context_tokens=2000,
    )
    assert result["model"] == "test-model"
    assert result["ctx_tokens"] == 2000
    assert result["ttft_s"] is not None
    assert result["ttft_s"] >= 0.0
    assert result["prefill_tps"] is not None
    assert result["gen_tps"] is not None
    assert result["out_tokens"] == 1


def test_run_probe_serial_and_configurable(fake_server):
    import tempfile
    import os
    key_file = tempfile.NamedTemporaryFile(delete=False)
    key_file.write(b"fake-key")
    key_file.close()
    models = [{"name": "m", "base_url": fake_server, "model_id": "test-model", "api_key_file": key_file.name}]
    try:
        results = speed.run_probe(models, context_sizes=[1000, 5000])
    finally:
        os.unlink(key_file.name)

    assert len(results) == 2
    ctxs = [r["ctx_tokens"] for r in results]
    assert ctxs == [1000, 5000]
    for r in results:
        assert r["ttft_s"] is not None
        assert r["prefill_tps"] is not None


def test_prompt_tokens_from_usage(fake_server):
    # The fake server reports prompt_tokens = len(content)//4.
    result = speed.probe_one(
        base_url=fake_server,
        model_id="test-model",
        api_key="fake-key",
        context_tokens=2000,
    )
    # content is filler of ~2000 tokens * 4 chars = 8000 chars -> 2000 tokens
    assert result["prefill_tps"] == pytest.approx(2000 / result["ttft_s"], rel=0.1)


def test_probe_batch_aggregates_concurrent_requests(fake_server):
    batch = speed.probe_batch(fake_server, "test-model", "fake-key", 1000, concurrency=3)
    assert batch["concurrency"] == 3
    assert batch["requests"] == 3
    assert batch["errors"] == 0
    assert batch["ttft_p50"] is not None
    assert batch["ttft_p95"] >= batch["ttft_p50"]
    assert batch["agg_gen_tps"] is not None
    assert batch["wall_s"] > 0
    # Mean per request; the fake reports one completion token.
    assert batch["out_tokens"] == 1


def test_probe_batch_counts_failed_requests():
    batch = speed.probe_batch(
        "http://127.0.0.1:1/v1", "test-model", "fake-key", 10, concurrency=2
    )
    assert batch["requests"] == 0
    assert batch["errors"] == 2
    assert batch["ttft_p50"] is None
    assert batch["agg_gen_tps"] is None


def test_run_probe_concurrency_and_iterations(fake_server):
    import os
    import tempfile

    key_file = tempfile.NamedTemporaryFile(delete=False)
    key_file.write(b"fake-key")
    key_file.close()
    models = [
        {
            "name": "m",
            "base_url": fake_server,
            "model_id": "test-model",
            "api_key_file": key_file.name,
        }
    ]
    try:
        results = speed.run_probe(
            models, context_sizes=[1000], concurrency=[1, 2], iterations=2
        )
    finally:
        os.unlink(key_file.name)

    assert len(results) == 4
    assert {r["concurrency"] for r in results} == {1, 2}
    # One batch_id per (ctx, concurrency), shared by its iterations.
    per_batch: dict[str, int] = {}
    for result in results:
        per_batch[result["batch_id"]] = per_batch.get(result["batch_id"], 0) + 1
    assert sorted(per_batch.values()) == [2, 2]
    assert all(r["ctx_tokens"] == 1000 for r in results)
    assert all(r["ts"] for r in results)


def test_init_schema_adds_speed_batch_columns(tmp_path):
    import sqlite3

    import db

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE speed (id INTEGER PRIMARY KEY AUTOINCREMENT, model TEXT, "
        "ts TEXT, ctx_tokens INTEGER, ttft_s REAL, prefill_tps REAL, "
        "gen_tps REAL, out_tokens INTEGER)"
    )
    conn.commit()
    conn.close()

    conn = db.connect(path)
    try:
        db.init_schema(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(speed)")}
    finally:
        db.close(conn)
    assert {
        "concurrency",
        "batch_id",
        "ttft_p50",
        "ttft_p95",
        "agg_gen_tps",
        "requests",
        "errors",
        "wall_s",
    } <= columns
