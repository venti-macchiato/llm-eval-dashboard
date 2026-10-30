# REVIEW REQUEST — LLM eval dashboard

Requesting a review of the current dashboard. Full suite: 80 passed.

## What to review

1. **Per-sample scoring** (`runlog.py`) — inspect scorers report numbers,
   `C/I/N/P` status codes, or dicts (IFEval). Confirm the mapping matches each
   run's headline score for multiple-choice, exact-answer, and IFEval tasks.
2. **Ingest provenance/backfill** (`ingest.py`, `db.py`) — 13-column insert,
   pandas `<NA>` handling, idempotent backfill, and additive migrations on an
   existing `bench.db`.
3. **Benchmark metadata** (`benchmarks.py`, `benchmarks.yaml`) — task ids
   resolve in `inspect_evals`; malformed or partial YAML must not crash the app
   or hide benchmarks.
4. **Eval job state machine** (`evaljobs.py`, `evalrun.py`, `evalproc.py`) —
   atomic start, cancel semantics, terminal-state ordering, live progress,
   repeat/epoch progress accounting.
5. **Pooling** (`aggregate.py`, `routes_analysis.py`) — grouping key (config,
   epochs, sample count), `se` combination, leaderboard cell selection, and the
   unknown-stderr path.
6. **Hardware provenance** (`hardware.py`, `ingest.py`) — declared vs probed
   evidence, local-endpoint gating, backfill idempotency.
7. **Frontend** (`frontend/src/`) — hooks/polling cleanup, drawer state, chart
   data keys, null guards, pooled-group selection, and layout at 1280/1600 px.

## Verification

```sh
python -m pytest -q                                  # 80 passed
cd frontend && npm run build                         # writes static/dist
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```
