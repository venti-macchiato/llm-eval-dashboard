# LLM Eval Dashboard

A local web dashboard for tracking how local LLMs perform over time. It combines
two data sources:

1. **Accuracy** — from Inspect AI eval logs (`.eval` files) via `inspect_ai`.
2. **Speed** — from a streaming speed probe against an OpenAI-compatible endpoint.

Both are stored in a local SQLite database and exposed through a read-only JSON
API plus a single-page frontend (vanilla JS + Chart.js, no build step).

## Stack

- Python 3.11+ (developed on 3.14)
- FastAPI (API + static file serving)
- SQLite via stdlib `sqlite3`
- pytest (tests)
- Chart.js 4.4.7 (vendored in `static/vendor/`)
- `inspect_ai`, pandas, pyarrow (log ingestion)

## Layout

```
config.yaml          Fixed contract: logs_dir, db_path, inspect_view_url, models
config.py            Loads config.yaml into importable constants
db.py                connect(), init_schema(), close()
ingest.py            ingest(logs_dir, db_path) -> {"new": n, "skipped": s}
speed.py             Streaming speed probe + background start_probe()
api.py               FastAPI app; all endpoints
static/index.html    Single page
static/app.js        Frontend logic (fetch + render)
static/style.css     Theme-aware styling
static/vendor/       Vendored Chart.js
tests/               pytest suite
```

## Setup

```sh
python -m venv .venv
.venv\Scripts\activate            # Windows; . .venv/bin/activate on Unix
pip install inspect-ai fastapi uvicorn httpx pytest pyyaml pandas pyarrow
```

The API initializes the SQLite schema on startup, so no manual migration is
needed. Logs are ingested at runtime (see below).

## Configuration

Edit `config.yaml`:

```yaml
logs_dir: sample_logs
db_path: bench.db
inspect_view_url: ""
models:
- name: polystrata-q3
  inspect_model: openai/tiel-coder-35b-a3b-ud-q3_k_xl
  base_url: http://100.112.119.2:8080/v1
  model_id: tiel-coder-35b-a3b-ud-q3_k_xl
  api_key_file: ~/.strata/key
```

`inspect_model` maps each model to the string inspect_ai recorded in its logs
so the runs table stores the config `name` (used by the picker and filters),
not the raw inspect string. `api_key_file` must contain the raw key for the
model's endpoint; it is read at probe time and never printed or logged.


## Running

```sh
.venv\Scripts\python.exe -m uvicorn api:app --reload
```

Open http://127.0.0.1:8000. Click **Ingest logs** to load `sample_logs/` (or set
`logs_dir` to your own Inspect logs), then **Run speed probe** to measure the
configured models.

## API

All endpoints are JSON, read-only except where noted.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/models` | Configured model names. |
| GET | `/api/runs?model=&task=&limit=200` | Accuracy runs. |
| GET | `/api/latest?models=a,b` | Latest score per (model, task) with `prev_score`. |
| GET | `/api/trend?model=&task=` | Score history, oldest first. |
| GET | `/api/speed?model=&limit=10000` | Speed rows, oldest first. |
| POST | `/api/ingest` | Ingest logs. Returns `{"new": n, "skipped": s}`. |
| POST | `/api/speed/run` | Start the background speed probe. Returns `{"started": b}`. |
| GET | `/api/speed/status` | Probe status: `{"running": bool, "error": str|null}`. |


## Tests

```sh
.venv\Scripts\python.exe -m pytest -q
```

- `tests/test_ingest.py` — ingestion semantics against synthetic logs written
  to a temp dir (no committed sample data).
- `tests/test_api.py` — every endpoint via FastAPI `TestClient`.
- `tests/test_speed.py` — the probe against a fake local streaming server (never
  contacts the real endpoint).

## Notes

- The speed probe uses a random prompt prefix per run so repeat probes don't
  report inflated prefill throughput from cached responses.
- `out_tokens` is reported as null when the server returns no usage, rather
  than a fabricated estimate.
- Probe thread errors (missing key file, unreachable endpoint) are captured
  and surfaced via `/api/speed/status`.

