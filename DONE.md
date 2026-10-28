# DONE — LLM eval dashboard

All five phases complete. Full suite: **24 passed**.

## Phase 1 — Data layer
- `config.yaml` (fixed contract), `config.py` (27), `db.py` (66), `ingest.py` (150).
- `tests/test_ingest.py` (self-contained) — 6 tests PASS. Synthetic `.eval`
  logs are written to a temp dir in tests; no committed sample data.

## Phase 2 — API
- `api.py` (186) — all endpoints; JSON, read-only except POST /api/ingest and
  POST /api/speed/run.
- Fixed the inverted `prev_score` query (rewrote /api/latest in Python).
- Lifespan context manager initializes the SQLite schema so queries work
  before the first ingest.
- `tests/test_api.py` (208) — 15 tests PASS.

## Phase 3 — Speed probe
- `speed.py` (240) — streaming probe (TTFT, prefill/gen TPS) over configurable
  context sizes; background `start_probe()`. Random prompt prefix defeats
  response caching; `out_tokens` is None when the server reports no usage;
  thread errors are captured (not swallowed) and exposed via
  `is_running()` / `last_error()`.
- `tests/test_speed.py` (153) — 3 tests against a fake local uvicorn streaming
  server; never contacts the real endpoint. PASS.

## Phase 4 — Frontend
- `static/index.html` (72), `static/app.js` (485), `static/style.css` (163).
- Vendored Chart.js 4.4.7 in `static/vendor/`.
- Summary cards (latest score + delta), 3 charts, sortable run table, empty
  states, theme-aware (`prefers-color-scheme`), DOM-escaped text.

## Phase 5 — Docs + verification
- `README.md` — setup, config, run, API, tests.
- Full suite: 24 passed.
- Every source file ≤ 250 lines.

## Verified
- `pytest -q` → 24 passed.
- HTTP smoke test: static files + every JSON endpoint (including the new
  `/api/speed/status`) return 200.
