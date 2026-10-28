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
