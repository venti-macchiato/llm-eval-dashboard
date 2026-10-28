# PROGRESS — LLM eval dashboard

## Status: All phases complete. Full suite: 24 passed.

## Reviewer feedback addressed (2026-10-28)

Model names won't match on real logs:
- Added `inspect_model` to config.yaml (maps config name → inspect string).
- `ingest` maps the raw inspect model string in logs to the config `name`
  (reverse map), storing the config name in `runs.model`.
- `run_probe` stores `model["name"]` (config name) in `speed.model`, requests
  with `model["model_id"]`.
- `/api/models` still returns config names. Picker + `model=` filters now match.

Ingest hid failures:
- `ingest` now returns `{"new": n, "skipped": s}` instead of an int.
- Real errors (missing dir, corrupt log, missing dep) are raised, not
  swallowed → 0. DB is rolled back on failure (no half-written rows).
- Rows with no headline score or an unknown model are counted as skipped.

Speed probe:
- Random prompt prefix per run defeats response caching (inflated prefill).
- `out_tokens` is `None` when the server reports no usage (was a bogus
  `context_tokens / 4` estimate).
- Thread errors are captured, not swallowed; exposed via
  `speed.is_running()` / `speed.last_error()` and `GET /api/speed/status`.
- `/api/speed` now honors `limit` (default 10000, max 100000).

Smaller:
- Replaced deprecated `@app.on_event("startup")` with a lifespan context
  manager.
- `api_key_file` default changed `~/.config/strata/key` → `~/.strata/key`.
- DONE.md no longer claims the UI was live-verified in a browser.

Sample data:
- `sample_logs/` removed. `tests/test_ingest.py` writes synthetic `.eval`
  logs to a temp dir (self-contained). `make_logs.py` kept as a generator.

## Files (line counts)
- config.yaml (fixed contract; added `inspect_model`, key path).
- config.py (27), db.py (66), ingest.py (119).
- api.py (185) — lifespan, /api/speed/status, /api/speed limit.
- speed.py (220) — random prefix, out_tokens=None, error capture.
- tests/test_ingest.py (164), tests/test_speed.py (153), tests/test_api.py (208).

## Verified
- `pytest -q` → 24 passed.
- HTTP smoke: static files + every JSON endpoint (incl. /api/speed/status) return 200.
