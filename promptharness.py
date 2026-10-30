"""Run custom prompt tests against one configured model.

Requests are sequential: the model server serializes them, so one test run at a
time (the route layer also refuses to overlap an eval or speed probe). Results
are stored in ``prompt_runs`` / ``prompt_results`` via :mod:`promptstore`, and
the HTTP side lives in :mod:`promptrunner`.
"""

from __future__ import annotations

import secrets
import threading
from datetime import datetime

import config
import evaljobs
import modeljobs
import prompts
from promptrunner import run_tests
from promptstore import recent_runs, save_run  # re-exported for routes/tests

_run_lock = threading.Lock()
_state_lock = threading.Lock()
_cancel = False
_state: dict = {
    "running": False,
    "state": "idle",
    "model": None,
    "run_id": None,
    "done": 0,
    "total": 0,
    "current": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
    "passed": 0,
    "failed": 0,
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _model_cfg(name: str) -> dict:
    for model in config.MODELS:
        if model.get("name") == name:
            return model
    raise ValueError(f"unknown model: {name}")


def is_running() -> bool:
    with _state_lock:
        return bool(_state["running"])


def status() -> dict:
    with _state_lock:
        return dict(_state)


def cancel() -> bool:
    global _cancel
    if not is_running():
        return False
    _cancel = True
    return True


def start_run(model_name: str, repeats: int = 1) -> dict:
    """Validate, claim the runner, and start the background thread.

    Returns ``{"started": True, "run_id": ...}`` or ``{"started": False,
    "reason": ...}``. Raises ValueError for an unknown model or no tests.
    """
    global _cancel
    model = _model_cfg(model_name)
    tests = prompts.load()
    if not tests:
        raise ValueError("no prompt tests defined in prompts.yaml")
    repeats = max(1, min(int(repeats or 1), 10))
    # Local import: speed imports this module for its own claim check.
    import speed as speed_module

    with modeljobs.LOCK:
        if evaljobs.is_running():
            return {"started": False, "reason": "an eval job is running"}
        if speed_module.is_running():
            return {"started": False, "reason": "a speed probe is running"}
        if not _run_lock.acquire(blocking=False):
            return {"started": False, "reason": "a prompt run is already active"}

        _cancel = False
        run_id = f"p-{secrets.token_hex(6)}"
        started = _now()
        with _state_lock:
            _state.update(
                {
                    "running": True,
                    "state": "running",
                    "model": model_name,
                    "run_id": run_id,
                    "done": 0,
                    "total": len(tests) * repeats,
                    "current": None,
                    "error": None,
                    "started_at": started,
                    "finished_at": None,
                    "passed": 0,
                    "failed": 0,
                }
            )

    def progress(done: int, total: int, test_id: str) -> None:
        with _state_lock:
            _state.update({"done": done, "total": total, "current": test_id})

    def worker() -> None:
        global _cancel
        try:
            results = run_tests(
                model,
                tests,
                repeats,
                on_progress=progress,
                cancelled=lambda: _cancel,
            )
            if results:
                save_run(config.DB_PATH, run_id, model_name, started, repeats, results)
            passed = sum(1 for row in results if row.get("passed"))
            failed = sum(1 for row in results if not row.get("passed"))
            was_cancelled = _cancel
            with _state_lock:
                _state.update(
                    {
                        "running": False,
                        "state": "cancelled" if was_cancelled else "done",
                        "done": len(results),
                        "total": len(tests) * repeats,
                        "current": None,
                        "finished_at": _now(),
                        "passed": passed,
                        "failed": failed,
                    }
                )
        except Exception as exc:  # noqa: BLE001 - surface into status
            with _state_lock:
                _state.update(
                    {
                        "running": False,
                        "state": "failed",
                        "error": f"{type(exc).__name__}: {exc}",
                        "finished_at": _now(),
                    }
                )
        finally:
            _cancel = False
            _run_lock.release()

    threading.Thread(target=worker, daemon=True).start()
    return {"started": True, "run_id": run_id}
