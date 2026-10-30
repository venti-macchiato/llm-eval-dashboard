"""Speed probe orchestration.

For each model, context size, and concurrency level, run one or more concurrent
batches (see :mod:`speedprobe`) and store one row per batch. With
``iterations > 1`` the repeats share a ``batch_id`` so the UI can plot a
sustained run and look for thermal drift.
"""

from __future__ import annotations

import secrets
import threading
import time
from pathlib import Path

import evaljobs
import modeljobs
import promptharness
import speedprobe
from speedprobe import OUTPUT_TOKENS, probe_batch, probe_one  # noqa: F401 - re-exported

DEFAULT_CONTEXT_SIZES = [2000, 16000, 64000]
DEFAULT_CONCURRENCY = [1]
DEFAULT_ITERATIONS = 1

# Columns written for one batch, in insert order.
COLUMNS = (
    "model",
    "ts",
    "ctx_tokens",
    "concurrency",
    "batch_id",
    "ttft_s",
    "ttft_p50",
    "ttft_p95",
    "prefill_tps",
    "gen_tps",
    "agg_gen_tps",
    "out_tokens",
    "requests",
    "errors",
    "wall_s",
)

_lock = threading.Lock()
_running = False
_last_error: str | None = None


def _read_api_key(api_key_file: str) -> str:
    """Read an API key from a file, expanding ~ to the user's HOME."""
    path = Path(api_key_file).expanduser()
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read().strip()


def run_probe(
    models: list[dict],
    context_sizes: list[int] | None = None,
    concurrency: list[int] | None = None,
    iterations: int = DEFAULT_ITERATIONS,
) -> list[dict]:
    """Probe all models serially; batches run at the requested concurrency.

    Each result's ``model`` is the config name so it matches the runs table and
    the UI pickers.
    """
    sizes = context_sizes or DEFAULT_CONTEXT_SIZES
    levels = sorted({int(c) for c in (concurrency or DEFAULT_CONCURRENCY) if int(c) > 0})
    levels = levels or [1]
    iterations = max(1, int(iterations or 1))

    results: list[dict] = []
    for model in models:
        api_key = _read_api_key(model["api_key_file"])
        for ctx in sizes:
            for level in levels:
                batch_id = (
                    f"{time.strftime('%Y%m%dT%H%M%S')}-{model['name']}-"
                    f"{ctx}-c{level}-{secrets.token_hex(3)}"
                )
                for _ in range(iterations):
                    stats = probe_batch(
                        model["base_url"], model["model_id"], api_key, ctx, level
                    )
                    stats.update(
                        {
                            "model": model["name"],
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "ctx_tokens": ctx,
                            "batch_id": batch_id,
                        }
                    )
                    results.append(stats)
    return results


def is_running() -> bool:
    """Return True if a probe is currently running."""
    return _running


def last_error() -> str | None:
    """Return the error from the most recent probe, or None."""
    return _last_error


def start_probe(
    context_sizes: list[int] | None = None,
    model_names: list[str] | None = None,
    concurrency: list[int] | None = None,
    iterations: int = DEFAULT_ITERATIONS,
) -> bool:
    """Run the probe in a background thread.

    ``concurrency`` is a list of request counts to test (1/2/4/8 …);
    ``iterations`` repeats each batch back-to-back for drift. Returns True if a
    probe was started, False if one is already running. Errors are exposed via
    :func:`last_error`.
    """
    global _running, _last_error
    with modeljobs.LOCK:
        if evaljobs.is_running() or promptharness.is_running():
            _last_error = "an eval or prompt run is active"
            return False
        if not _lock.acquire(blocking=False):
            return False
        _running = True
        _last_error = None

    def _worker():
        global _running, _last_error
        try:
            import db
            from config import DB_PATH, MODELS

            models = list(MODELS)
            if model_names:
                wanted = set(model_names)
                models = [m for m in models if m.get("name") in wanted]
                if not models:
                    raise ValueError("no configured models matched the request")
            results = run_probe(models, context_sizes, concurrency, iterations)
            conn = db.connect(DB_PATH)
            try:
                placeholders = ", ".join("?" * len(COLUMNS))
                for result in results:
                    conn.execute(
                        f"INSERT INTO speed ({', '.join(COLUMNS)}) "
                        f"VALUES ({placeholders})",
                        tuple(result.get(column) for column in COLUMNS),
                    )
                conn.commit()
            finally:
                db.close(conn)
        except Exception as exc:  # noqa: BLE001 - surface, don't swallow
            _last_error = f"{type(exc).__name__}: {exc}"
        finally:
            _running = False
            _lock.release()

    threading.Thread(target=_worker, daemon=True).start()
    return True
