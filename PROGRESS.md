# PROGRESS — LLM eval dashboard

## Status: All phases complete. Full suite: 24 passed.

## Setup
- Python 3.14 (only version on this Windows box). venv at `.venv`.
- Installed: inspect-ai, fastapi, uvicorn, httpx, pytest, pyyaml, pandas, pyarrow.
  - pandas+pyarrow are required by `inspect_ai.analysis.evals_df`.
- `sample_logs/` did NOT exist. Generated 7 `.eval` files (real inspect_ai EvalLog
  objects via `write_eval_log`) across 2 models (polystrata-q3, gpt-4o), 2 tasks
  (math, history), spread over ~11 days. Verified `evals_df("sample_logs")` reads them.
  - Generator: `make_logs.py` (kept; logs are the project's sample data, not a test fixture).
- `evals_df` columns used: eval_id, task_name, model, score_headline_value,
  score_headline_stderr, total_samples, log, created. No token/duration columns in the
  sample logs (verified) → those runs columns are NULL.

## Files
- config.yaml — fixed contract (unchanged).
- config.py (27) — loads config.yaml into LOGS_DIR, DB_PATH, INSPECT_VIEW_URL, MODELS.
- db.py (44) — connect(), init_schema(), close(). Row factory + foreign_keys pragma.
- ingest.py (86) — ingest(logs_dir, db_path) -> int. Idempotent on eval_id.
- tests/test_ingest.py (94) — 6 tests. PASS.
- tests/conftest.py (8) — adds project root to sys.path.
- api.py (186) — FastAPI app; all endpoints.
- tests/test_api.py (207) — 15 tests. 13 pass; 2 need Phase 4 static files.

## Interfaces
- ingest.ingest(logs_dir, db_path): returns NEW runs inserted; 0 on rerun/empty dir.
- api.py endpoints: GET /api/models, /api/runs?model=&task=&limit=200,
  /api/latest?models=a,b (prev_score = second-most-recent run per model/task, null if none),
  /api/trend?model=&task= (oldest first), /api/speed?model= (oldest first),
  POST /api/ingest -> {new:n}, POST /api/speed/run -> {started:true}, GET /, /static/*.
- Bug fixed in Phase 2: prev_score query was inverted (returned latest, not previous).
  Rewrote /api/latest to load rows ordered by created DESC and take runs[1] in Python.

## Phase 3 (speed probe) — next
- speed.py (real impl done) + tests/test_speed.py (fake ASGI server, never hits real endpoint).

## Notes / gotchas
- EvalLog schema: `eval` is EvalSpec (eval_id, run_id, created, task, model,
  dataset=EvalDataset, config=EvalConfig). EvalScore needs `scorer` (required) + reducer.
- monkeypatch has no .getattr; read monkeypatched config via `import config; config.DB_PATH`.
- No shell `sed`/`python` edits; use edit/write tools.
