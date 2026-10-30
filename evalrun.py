"""Launch inspect eval tasks from the dashboard in a background thread.

One suite runs at a time (the model server serializes requests). Progress is
published through :mod:`evaljobs` under its lock so the API sees live sample
counts.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading

import config
import evaljobs
import modeljobs
from evaltasks import EvalError, normalise_tasks
import promptharness
import sandbox
import speed
from evalproc import run_task


def _cmd_argv(cmd: str) -> list[str]:
    return cmd.split()


def _resolve_inspect_cmd() -> str:
    cmd = (config.INSPECT_CMD or "").strip()
    if cmd:
        return cmd
    found = shutil.which("inspect")
    if not found:
        raise EvalError("inspect CLI not found; set inspect_cmd in config.yaml")
    return found


def _confirm_cli(cmd: str) -> None:
    try:
        proc = subprocess.run(
            _cmd_argv(cmd) + ["--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EvalError(f"inspect --version failed: {exc}") from exc
    if proc.returncode != 0:
        raise EvalError("inspect --version failed")


def _model_for(model_name: str, override: dict | None = None) -> dict:
    """Resolve a config model, applying UI overrides (endpoint / model id)."""
    base = next((m for m in config.MODELS if m.get("name") == model_name), None)
    adhoc = bool(override and override.get("model_id"))
    if base is None and not adhoc:
        raise EvalError(f"unknown model: {model_name}")
    model = dict(base) if base else {"name": model_name}
    if override:
        for key in ("base_url", "model_id", "api_key_file", "inspect_model"):
            if override.get(key):
                model[key] = override[key]
        if override.get("model_id") and not override.get("inspect_model"):
            model["inspect_model"] = f"openai/{override['model_id']}"
    model.setdefault("inspect_model", model.get("model_id") or model_name)
    return model


def _build_env(model: dict) -> dict:
    """Child env with OPENAI_BASE_URL + OPENAI_API_KEY (key never logged)."""
    env = dict(os.environ)
    env["OPENAI_BASE_URL"] = model.get("base_url", "")
    api_key_file = model.get("api_key_file", "")
    if api_key_file:
        path = os.path.expanduser(api_key_file)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                env["OPENAI_API_KEY"] = fh.read().strip()
        except OSError:
            env["OPENAI_API_KEY"] = ""
    return env


def _run_suite(
    model_name: str,
    suite_name: str,
    tasks: list[dict] | None,
    override: dict | None,
    repeats: int = 1,
) -> None:
    """Worker run in a background thread. Never raises into the caller."""
    try:
        cmd = _resolve_inspect_cmd()
        _confirm_cli(cmd)
        model = _model_for(model_name, override)
        task_list = normalise_tasks(suite_name, tasks)
        os.makedirs(config.LOGS_DIR, exist_ok=True)
        env = _build_env(model)
        interrupted = False
        repeats = max(1, min(int(repeats or 1), 20))
        for idx, task in enumerate(task_list, start=1):
            task_name = task["task"]
            limit = int(task.get("limit", 20))
            epochs = int(task.get("epochs", 1) or 1)
            full = (
                task_name
                if task_name.startswith("inspect_evals/")
                else f"inspect_evals/{task_name}"
            )
            # inspect reports samples as len(dataset) * epochs.
            per_repeat = limit * epochs
            for rep in range(1, repeats + 1):
                current = evaljobs.get_job() or {}
                if current.get("state") == "failed" or current.get("cancel_requested"):
                    interrupted = True
                    break
                evaljobs.set_state(
                    task_index=idx,
                    current_task=full,
                    samples_done=(rep - 1) * per_repeat,
                    samples_total=per_repeat * repeats,
                    repeat_index=rep,
                    repeat_total=repeats,
                )
                argv = _cmd_argv(cmd) + [
                    "eval",
                    full,
                    f"--model={model.get('inspect_model', model_name)}",
                    f"--limit={limit}",
                    "--max-connections=1",
                    f"--log-dir={config.LOGS_DIR}",
                    "--display=plain",
                ]
                if epochs > 1:
                    argv.append(f"--epochs={epochs}")
                ok, info = run_task(
                    argv,
                    env,
                    progress_base=(rep - 1) * per_repeat,
                    progress_total=per_repeat * repeats,
                )
                evaljobs.append_result(
                    full, ok, info if ok else None, repeat=rep, repeats=repeats
                )
                if not ok and not (evaljobs.get_job() or {}).get("error"):
                    evaljobs.set_state(error=info)
            if interrupted:
                break
        evaljobs.set_state(phase="finalizing")
        try:
            from ingest import ingest as _ingest

            ingest_result = _ingest(config.LOGS_DIR, config.DB_PATH)
        except Exception as exc:  # noqa: BLE001 - surface, don't swallow
            ingest_result = {"error": str(exc)}
        evaljobs.set_state(ingest=ingest_result)

        job = evaljobs.get_job() or {}
        if interrupted or job.get("cancel_requested"):
            evaljobs.finish("failed", "cancelled by user")
        elif any(not r["ok"] for r in job.get("results", [])):
            evaljobs.finish("failed")
        else:
            evaljobs.finish("done")
    except Exception as exc:  # noqa: BLE001 - surface into job state
        evaljobs.finish("failed", str(exc))


def start_suite(
    model_name: str,
    suite_name: str,
    tasks: list[dict] | None = None,
    override: dict | None = None,
    repeats: int = 1,
    epochs: int | None = None,
) -> dict:
    """Validate, refuse if busy, else start a background thread.

    ``repeats`` runs every task that many times as separate evals (separate
    logs), so the dashboard can pool the draws into a mean ± CI. ``epochs`` is
    the inspect-native repeat within one log, used as the per-task default.

    Returns {"started": True} or {"started": False, "reason": ...}. Raises
    EvalError for unknown model/suite.
    """
    _model_for(model_name, override)
    task_list = normalise_tasks(suite_name, tasks, epochs)
    try:
        sandbox.ensure([task["task"] for task in task_list])
    except sandbox.SandboxError as exc:
        raise EvalError(str(exc)) from exc
    repeats = max(1, min(int(repeats or 1), 20))
    # Guard and claim atomically: the sandbox preflight above can take seconds,
    # and another job may claim the slot in between.
    with modeljobs.LOCK:
        if promptharness.is_running():
            raise EvalError("a prompt run is running")
        if speed.is_running():
            raise EvalError("a speed probe is running")
        if evaljobs.try_start(model_name, suite_name, len(task_list)) is None:
            return {"started": False, "reason": "another job is running"}
    thread = threading.Thread(
        target=_run_suite,
        args=(model_name, suite_name, task_list, override, repeats),
        daemon=True,
    )
    thread.start()
    return {"started": True}


def cancel() -> bool:
    """Terminate the child process if running; mark job failed."""
    return evaljobs.cancel()
