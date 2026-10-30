"""Operational endpoints: run evals, job status, suites, ingest, speed probe."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import config
import evaljobs
import evalrun
import ingest
import promptharness
import sandbox
import speed

router = APIRouter(prefix="/api")


@router.get("/suites")
def api_suites():
    """Configured suites: {suite_name: [{task, limit}, ...]}."""
    return {name: tasks for name, tasks in config.SUITES.items()}


@router.post("/eval/run")
def api_eval_run(body: dict):
    """Start an eval. Body: {model, suite?} or {model, tasks: [{task, limit}]}.

    Optional ``model_override`` ({base_url, model_id, api_key_file}) lets the UI
    run an ad-hoc endpoint without editing config.yaml.
    """
    model = body.get("model")
    suite = body.get("suite")
    tasks = body.get("tasks")
    override = body.get("model_override") or None
    repeats = body.get("repeats", 1)
    epochs = body.get("epochs")

    if not model:
        raise HTTPException(status_code=400, detail="'model' is required")
    if not suite and not tasks:
        raise HTTPException(
            status_code=400, detail="provide 'suite' or a 'tasks' list"
        )
    if promptharness.is_running():
        raise HTTPException(status_code=409, detail="a prompt run is running")
    if speed.is_running():
        raise HTTPException(status_code=409, detail="a speed probe is running")
    for name, value in (("repeats", repeats), ("epochs", epochs)):
        if value is None and name == "epochs":
            continue
        if not isinstance(value, int) or isinstance(value, bool):
            raise HTTPException(status_code=400, detail=f"'{name}' must be an integer")
        if not 1 <= value <= 20:
            raise HTTPException(
                status_code=400, detail=f"'{name}' must be between 1 and 20"
            )
    if tasks is not None:
        if not isinstance(tasks, list) or not tasks:
            raise HTTPException(status_code=400, detail="'tasks' must be a non-empty list")
        for item in tasks:
            if not isinstance(item, dict) or not item.get("task"):
                raise HTTPException(
                    status_code=400, detail="each task needs a 'task' name"
                )

    try:
        result = evalrun.start_suite(
            model, suite or "custom", tasks, override, repeats, epochs
        )
    except evalrun.EvalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result.get("started"):
        raise HTTPException(
            status_code=409, detail=result.get("reason", "another job is running")
        )
    return result


@router.get("/preflight")
def api_preflight(refresh: bool = False):
    """Host capabilities that tasks require (Docker), for the run form.

    ``refresh=1`` re-probes instead of serving the short-lived cache, so the
    UI's Recheck button reflects a just-started Docker daemon.
    """
    return {
        "capabilities": sandbox.capabilities(refresh=refresh),
        "requirements": {
            task: ["docker"] for task in sorted(sandbox.DOCKER_TASKS)
        },
    }


@router.get("/eval/status")
def api_eval_status():
    """Current eval job state (or {} if idle)."""
    return evaljobs.get_job() or {}


@router.post("/eval/cancel")
def api_eval_cancel():
    if evalrun.cancel():
        return {"cancelled": True}
    # Already flagged but the worker has not finished finalizing: report it as
    # accepted so the UI does not claim there is nothing to cancel.
    job = evaljobs.get_job() or {}
    if job.get("state") == "running" and job.get("cancel_requested"):
        return {"cancelled": True, "already": True}
    return {"cancelled": False, "reason": "not running"}


@router.post("/ingest")
def api_ingest():
    result = ingest.ingest(config.LOGS_DIR, config.DB_PATH)
    return {
        "new": result["new"],
        "skipped": result["skipped"],
        "updated": result.get("updated", 0),
    }


@router.post("/speed/run")
def api_speed_run(body: dict | None = None):
    """Start the speed probe.

    Optional ``{context_sizes, models, concurrency, iterations}`` overrides.
    ``concurrency`` is a list of parallel request counts (1/2/4/8 …);
    ``iterations`` repeats each batch back-to-back to expose drift.
    """
    body = body or {}
    sizes = body.get("context_sizes")
    models = body.get("models")
    concurrency = body.get("concurrency")
    iterations = body.get("iterations", 1)
    if sizes is not None:
        if not isinstance(sizes, list) or not sizes:
            raise HTTPException(
                status_code=400, detail="'context_sizes' must be a non-empty list"
            )
        try:
            sizes = [int(s) for s in sizes]
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400, detail="'context_sizes' must be integers"
            ) from exc
        if any(s <= 0 for s in sizes):
            raise HTTPException(
                status_code=400, detail="'context_sizes' must be positive"
            )
    if models is not None and not isinstance(models, list):
        raise HTTPException(status_code=400, detail="'models' must be a list")
    if concurrency is not None:
        if not isinstance(concurrency, list) or not concurrency:
            raise HTTPException(
                status_code=400, detail="'concurrency' must be a non-empty list"
            )
        try:
            concurrency = sorted({int(value) for value in concurrency})
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400, detail="'concurrency' must be integers"
            ) from exc
        if any(value < 1 or value > 32 for value in concurrency):
            raise HTTPException(
                status_code=400, detail="'concurrency' must be between 1 and 32"
            )
    if not isinstance(iterations, int) or isinstance(iterations, bool):
        raise HTTPException(status_code=400, detail="'iterations' must be an integer")
    if not 1 <= iterations <= 20:
        raise HTTPException(
            status_code=400, detail="'iterations' must be between 1 and 20"
        )
    if evaljobs.is_running():
        raise HTTPException(status_code=409, detail="an eval job is running")
    if promptharness.is_running():
        raise HTTPException(status_code=409, detail="a prompt run is running")
    started = speed.start_probe(
        context_sizes=sizes,
        model_names=models,
        concurrency=concurrency,
        iterations=iterations,
    )
    return {"started": started}


@router.get("/speed/status")
def speed_status():
    from config import MODELS

    return {
        "running": speed.is_running(),
        "error": speed.last_error(),
        "context_sizes": speed.DEFAULT_CONTEXT_SIZES,
        "concurrency": speed.DEFAULT_CONCURRENCY,
        "iterations": speed.DEFAULT_ITERATIONS,
        "models": [m["name"] for m in MODELS],
    }
