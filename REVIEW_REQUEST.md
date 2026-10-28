# REVIEW REQUEST — LLM eval dashboard

Requesting a review of the completed dashboard. All phases done; full suite 24 passed.

## What to review

1. **Speed probe correctness** (`speed.py`) — TTFT / prefill_tps / gen_tps math.
   The probe is the least-tested path against real endpoints; the unit tests use
   a fake server, so real-stream behavior (chunk timing, usage parsing) is
   unverified. Worth eyeballing the streaming logic.

2. **`prev_score` semantics** (`api.py::latest`) — was inverted and rewritten in
   Python (load rows ordered by created DESC, take runs[1]). Confirm the grouping
   and delta logic match intent.

3. **Frontend rendering** (`static/app.js`) — summary-card deltas, chart dataset
   assignment, and table sorting. Live-verified to load but not exercised in
   browser; chart color cycling and empty-state toggling are worth a manual look.

4. **Startup schema init** (`api.py::_lifespan`) — added so queries work before the
   first ingest. Confirm this is the right place vs. an `@app.on_event` handler.

## Known gaps

- No browser-based tests; frontend verified only by live HTTP smoke test.
- Speed probe unit tests use a fake server; real streaming behavior unverified.
- `sample_logs/` is generated data — ensure reviewers know to replace it.

## Verification

```sh
.venv\Scripts\python.exe -m pytest -q    # 24 passed
.venv\Scripts\python.exe -m uvicorn api:app --reload   # smoke test endpoints
```
