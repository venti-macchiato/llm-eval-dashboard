"""Custom prompt harness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import config
import evaljobs
import promptharness
import prompts
import speed

router = APIRouter(prefix="/api")


@router.get("/prompts")
def prompt_definitions():
    """Prompt tests from prompts.yaml (definitions only; nothing is sent)."""
    status = promptharness.status()
    return {
        "tests": prompts.load(),
        "running": bool(status.get("running")),
        "error": status.get("error"),
    }


@router.post("/prompts/run")
def prompt_run(body: dict):
    """Start a prompt run. Body: {model, repeats?}."""
    model = body.get("model")
    repeats = body.get("repeats", 1)
    if not model:
        raise HTTPException(status_code=400, detail="'model' is required")
    if not isinstance(repeats, int) or isinstance(repeats, bool):
        raise HTTPException(status_code=400, detail="'repeats' must be an integer")
    if not 1 <= repeats <= 10:
        raise HTTPException(
            status_code=400, detail="'repeats' must be between 1 and 10"
        )
    if evaljobs.is_running():
        raise HTTPException(status_code=409, detail="an eval job is running")
    if speed.is_running():
        raise HTTPException(status_code=409, detail="a speed probe is running")
    try:
        result = promptharness.start_run(model, repeats)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result.get("started"):
        raise HTTPException(
            status_code=409,
            detail=result.get("reason", "a prompt run is already active"),
        )
    return result


@router.get("/prompts/status")
def prompt_status():
    return promptharness.status()


@router.post("/prompts/cancel")
def prompt_cancel():
    return {"cancelled": promptharness.cancel()}


@router.get("/prompts/results")
def prompt_results(
    model: list[str] | None = Query(None),
    run_id: str | None = Query(None),
    limit: int = Query(5, ge=1, le=50),
):
    return {
        "runs": promptharness.recent_runs(
            config.DB_PATH, model=model, run_id=run_id, limit=limit
        )
    }
