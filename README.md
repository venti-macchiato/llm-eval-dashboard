# LLM Eval Dashboard

A local dashboard for benchmarking LLMs served from an OpenAI-compatible
endpoint. It tracks two kinds of data:

1. **Accuracy** — from Inspect AI eval logs (`.eval`) produced by running
   `inspect_evals` tasks.
2. **Speed** — from a streaming probe that measures TTFT, prefill throughput,
   and generation throughput across context sizes.

Both land in a local SQLite database and are exposed through a JSON API and a
React single-page app.

## Stack

- Python 3.11+ (developed on 3.14), FastAPI, stdlib `sqlite3`
- React 18 + TypeScript + Vite, charts with Recharts
- `inspect_ai` + `inspect_evals` for benchmark execution and log ingestion
- pytest

## Layout

```
config.yaml            Local config (gitignored; holds secrets)
config.yaml.example    Template with stubbed values
config.py              Loads config.yaml into constants
db.py                  SQLite connect / schema
ingest.py              ingest(logs_dir, db_path) -> {new, skipped, updated}
runmeta.py             Row coercion + provenance meta build/merge
aggregate.py           Pool repeated runs into mean ± 95% CI
variants.py            Group variants by base model; delta vs a baseline
prompts.py             Custom prompt tests (YAML) + pass/fail checkers
promptharness.py       Prompt run state machine (start/cancel/status)
promptrunner.py        Prompt requests + test execution
promptstore.py         Prompt run/result persistence
prompts.yaml           User-editable prompt tests
sandbox.py             Docker preflight for code/agent benchmarks
speed.py               Speed probe orchestration + storage
speedprobe.py          Single request + concurrent batch measurement
evaljobs.py            In-memory state for the running eval job
evalrun.py             Launch inspect eval tasks in a background thread
evaltasks.py           Task-list normalization + EvalError
modeljobs.py           Shared job-claim lock (eval/prompt/speed)
evalproc.py            Subprocess driver for one inspect task
catalog.py             inspect_evals task catalog (no heavy imports)
runlog.py              Per-sample log analysis + token/duration stats
hardware.py            Declared hardware + local host probe (nvidia-smi)
benchmarks.py          Loads benchmarks.yaml (descriptions, categories)
benchmarks.yaml        Curated benchmark explanations and suite blurbs
api.py                 FastAPI app: routers + SPA serving
routes_data.py         Per-run read endpoints (runs, samples, speed, catalog)
routes_analysis.py     Aggregate reads (latest, trend, leaderboard, groups)
routes_export.py       CSV/JSON export endpoints
routes_eval.py         Operations (run eval, ingest, speed probe)
query.py               Shared SQL helpers + column orders
frontend/              React + Vite source
static/dist/           Built frontend (generated; gitignored)
static/favicon.svg     App icon
static/fonts/          Optional local Proxima Nova .woff2 files
fonts.py               @font-face rules for present font files
tests/                 pytest suite
```

## Setup

### Backend

```sh
python -m venv .venv
.venv\Scripts\activate            # Windows; . .venv/bin/activate on Unix
pip install -r requirements.txt
python setup.py                   # copies config.yaml.example -> config.yaml
```

Edit `config.yaml` with your models, endpoint, and suites (see below).

### Frontend

```sh
cd frontend
npm install
npm run build                     # writes static/dist
```

If the bundle is missing, `/` serves a page explaining how to build it.

## Configuration

```yaml
inspect_cmd: python -m inspect_ai
suites:
  smoke:
    - {task: inspect_evals/ifeval, limit: 10}
    - {task: inspect_evals/gsm8k, limit: 20}
logs_dir: sample_logs
db_path: bench.db
prompts_path: prompts.yaml   # optional; custom prompt tests
models:
  - name: my-model
    inspect_model: openai/served-model-name
    base_url: http://host:8080/v1
    model_id: served-model-name
    api_key_file: ~/config/.strata/key
```

- `name` is the dashboard label; `inspect_model` is what inspect_ai records.
- `base_model` groups variants into a family (defaults to `name`);
  `baseline: true` marks the family's reference variant for regressions.
- `api_key_file` is read at run time and never returned by the API or logged.
- Task ids are `inspect_evals/<task>`; browse the full catalog in the **Run
  eval** tab. The catalog is built from the installed `inspect_evals` (249
  tasks in 0.26.0) and excludes registry exports that are not tasks.

### Hardware provenance

Neither the `.eval` log nor the OpenAI-compatible API reports the machine,
quantisation, or context window a model was served with, yet those decide
whether two scores are comparable. Declare them per model:

```yaml
models:
  - name: polystrata-q3
    # …
    hardware:
      backend: llama.cpp        # vLLM, Ollama, LM Studio, …
      backend_version: b6100
      quant: Q3_K_XL
      gpu: RTX 4090
      vram_gb: 24
      ctx_size: 32768
      offload: "35/48 layers"
```

Every field is optional; the snapshot is written into each run's `meta` and
backfilled into rows ingested earlier (ingest reports them as `updated`).
Ingest is still idempotent: once a run carries hardware, re-ingesting changes
nothing.

A local `nvidia-smi` probe can add evidence automatically, but only for an
endpoint on this machine:

```yaml
host_probe:
  enabled: true
  command: nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits
  timeout: 10
```

The probe output must be `name, memory MiB, driver` lines (nvidia-smi's CSV
format). It is skipped for remote endpoints and tagged with the probed
hostname, so a local GPU is not recorded as a remote server's hardware. A
localhost port-forward to a remote server is indistinguishable from a local
one; declare `hardware:` for those setups instead of enabling the probe.

## Typography

The UI uses **Proxima Nova** when it is available and falls back to Montserrat,
Inter, or the system UI font otherwise. Proxima Nova is a commercial typeface,
so it is not bundled: either install it on the machine running the browser, or
drop your licensed `.woff2` files into `static/fonts/` using the usual names:

```
static/fonts/ProximaNova-Regular.woff2
static/fonts/ProximaNova-Medium.woff2
static/fonts/ProximaNova-Semibold.woff2
static/fonts/ProximaNova-Bold.woff2
static/fonts/ProximaNova-Extrabold.woff2
```

`/api/fonts.css` emits `@font-face` rules for whatever is present (and nothing
when the directory is empty), so the dashboard never requests missing files.

## Demo data

To see every view populated without running the model:

```sh
python seed_demo.py           # demo runs, speed samples, prompt results
python seed_demo.py --clear   # remove only those rows
```

Demo rows are marked with `demo-` ids, `meta.demo = true`, and speed batch ids
prefixed `demo-`; they are inserted slightly in the future so they count as the
current configuration. Real runs are never modified.

## Running

Production (single process serves API + built SPA):

```sh
.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000.

Frontend development (hot reload, API proxied to port 8000):

```sh
cd frontend && npm run dev        # http://127.0.0.1:5173
```

## Views

- **Overview** — filters, KPI cards, per-task accuracy facets, aggregate
  throughput and TTFT p95 by context, and a sustained-run drift chart when the
  probe recorded multiple iterations.
- **Variants** — one row per configured variant (q4/q5/q8, ctx sizes) grouped by
  `base_model`; each cell shows the pooled score and its Δ against the chosen
  baseline, flagged when the difference is inside 95% sampling noise.
- **Leaderboard** — model × task matrix; each cell is the pooled mean ± 95% CI
  of repeated runs of the same configuration, and the tooltip names the variant
  (quant, context) plus the run count and date range.
- **Runs** — sortable history with a config column and an Open action per row;
  drilldown (provenance, hardware, server-side failure filter with pagination,
  token usage), ingest, CSV/JSON export.
- **Compare** — head-to-head metrics between two pooled run groups, with a
  sampling-noise check and a configuration table that warns when
  quant/context/GPU differ.
- **Run eval** — pick a suite or compose tasks from the catalog (grouped and
  described), set repeats/epochs, override the endpoint, watch live sample
  progress (including repeat N of M) and the log tail; run speed probes with
  custom context sizes.
- **Prompts** — run your own prompts from `prompts.yaml` (JSON/schema adherence,
  tool calling, refusal, long-context recall, instruction constraints) against
  a configured model; results are stored with latency, tokens, output, and a
  pass/fail detail per test.
- **Benchmarks** — collapsible category sections; what each task measures, how
  to read its score, and which suites include it. Edit `benchmarks.yaml` to
  adjust the explanations.

## API

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/models` | Models with endpoint metadata (no key) and declared `hardware`. |
| GET | `/api/runs?model=&task=&limit=` | Runs; `model`/`task` repeatable. |
| GET | `/api/run/{eval_id}` | One run, including `meta` provenance. |
| GET | `/api/run/{eval_id}/samples?limit=&offset=&failures=` | Per-sample scores/errors; `failures=1` filters server-side. |
| GET | `/api/latest?models=a,b` | Latest score per (model, task) + previous. |
| GET | `/api/trend?model=&task=` | Score history. |
| GET | `/api/speed?model=&limit=` | Speed samples. |
| GET | `/api/leaderboard?model=&task=` | Model × task matrix of pooled groups. |
| GET | `/api/groups?model=&task=` | Runs pooled into configuration groups (Compare). |
| GET | `/api/variants?model=&task=&baseline=` | Variants grouped by base model + deltas vs baseline. |
| GET | `/api/prompts` | Prompt test definitions from prompts.yaml. |
| POST | `/api/prompts/run` | `{model, repeats?}`; 409 while eval/speed/prompt runs are active. |
| GET | `/api/prompts/status` | Prompt run progress. |
| GET | `/api/preflight?refresh=` | Host capabilities (Docker) + which tasks require them; `refresh=1` re-probes. |
| POST | `/api/prompts/cancel` | Cancel between tests. |
| GET | `/api/prompts/results?model=&run_id=&limit=` | Recent prompt runs with per-test rows. |
| GET | `/api/catalog` | inspect_evals task names (tasks only, not scorers). |
| GET | `/api/fonts.css` | `@font-face` rules for files in `static/fonts/`. |
| GET | `/api/benchmarks` | Curated descriptions, categories, suite blurbs. |
| GET | `/api/export/runs.csv\|json` | Export runs (same filters). |
| GET | `/api/export/speed.csv\|json` | Export speed samples. |
| GET | `/api/suites` | Configured suites. |
| POST | `/api/eval/run` | `{model, suite}` or `{model, tasks:[{task,limit,epochs?}]}`, optional `repeats`/`epochs` (1–20). |
| GET | `/api/eval/status` | Job state incl. live sample progress. |
| POST | `/api/eval/cancel` | Cancel the running job. |
| POST | `/api/ingest` | Ingest logs; returns `{new, skipped, updated}`. |
| POST | `/api/speed/run` | Start probe; optional `{context_sizes, models, concurrency:[1,2,4,8], iterations}`. |
| GET | `/api/speed/status` | Probe status + default concurrency/iterations. |

## Tests

```sh
python -m pytest -q
```

Tests never contact a real model server or run the real `inspect` CLI:
`tests/test_evalrun.py` drives the runner against a fake CLI script (including
repeats/epochs argv), `tests/test_speed.py` uses a local fake streaming server,
ingestion uses synthetic logs written to a temp dir, and
`tests/test_hardware.py` supplies a fake probe command (never a real
`nvidia-smi`), `tests/test_prompts.py` uses a fake chat-completions server, and
`tests/test_fonts.py` only inspects generated CSS.

## Notes

- **Repeats**: `repeats: N` runs every task N times as separate evals (separate
  logs); `epochs: N` passes inspect's native `--epochs` within one log. Both are
  set per run in the UI (1–20); a task entry may override `epochs`.
- **Pooling** (`aggregate.py`): runs are grouped by model, task, declared
  hardware + inspect generate config, and sample count. With `k == 1` the run's
  own score/stderr is used; with `k > 1` the group mean is the unweighted mean
  of run scores and
  `se = sqrt((var(scores) + mean(se_i²)) / k)` — between-run variance plus each
  run's average sampling error over k runs. Identical repeats therefore keep a
  non-zero interval rather than claiming perfect certainty.
- Sample count is part of the grouping key: a 5-sample and a 50-sample run cover
  different dataset slices, so they are never averaged. A Leaderboard cell shows
  the newest configuration, then the group with the largest sample count within
  that configuration — inside a configuration, a 1-sample smoke run never
  becomes headline evidence. Missing stderr stays unknown (no `±` / `—`), never `±0`.
- **Variants**: one model entry per variant, sharing `base_model`. `/api/variants`
  uses the same best-group-per-task rule as the Leaderboard; Δ is
  `variant − baseline` with `se = hypot(se_variant, se_baseline)`, and is marked
  `ns` when inside 95% noise, `?` when either interval is missing. The baseline
  comes from `baseline: true` (first variant as fallback) or the `baseline=`
  query parameter, which the UI select uses.
- `epochs` is recorded in the config fingerprint as well: `limit 20 x epochs 1`
  and `limit 10 x epochs 2` both report 20 samples but cover different slices.
- Ingest is idempotent on `eval_id`. It records provenance (`base_url`,
  `model_id`, dataset, epochs, sampling config, package versions, git commit)
  and `error_samples`, and backfills token counts, duration, and provenance for
  rows ingested by older versions.
- Hardware evidence lives in `run.meta.hardware`: `declared` (from
  `config.yaml`) and optionally `probe` (local `nvidia-smi`, tagged with the
  probed host). Backfilling it into an existing `bench.db` is a one-time
  `updated` per run; a repeat ingest is a no-op. The value is a snapshot: later
  edits to `config.yaml` do not rewrite runs that already recorded hardware
  (delete `meta` for a row if a declaration was wrong).
- The probe runs at most once per model per ingest, only when `host_probe` is
  enabled *and* the endpoint host is this machine.
- Schema changes are additive (`db._MIGRATIONS` → `ALTER TABLE ADD COLUMN`), so
  an existing `bench.db` upgrades in place on startup.
- Per-sample scores map inspect's choice statuses (`C`/`I`/`N`/`P`), dict-valued
  results (IFEval's `prompt_level_strict`), and numeric values to 0–1 so the
  drawer's mean matches the headline score.
- Sample progress is parsed from inspect's stdout, which redraws a progress
  line with `\r`; the runner splits on CR and LF.
- Speed probes prepend a random token so repeat probes are not served from a
  response cache.
- **Sandbox preflight**: the 87 code/agent tasks that default to a Docker
  sandbox in the installed `inspect_evals` (humaneval, mbpp, gaia, swe_bench,
  osworld, usaco, …) are checked before a run starts. Missing Docker returns a 400 with the daemon
  error and disables Start in the UI (`/api/preflight` feeds the badges). The
  check is cached for the status endpoint but always refreshed at run start.
- **Prompt tests** (`prompts.yaml`): each entry has a prompt and a
  `check.type` of `contains`, `not_contains`, `regex`, `equals`, `json`,
  `tool_call`, `refusal`, `recall`, or `max_words`. `recall` generates a needle
  and inserts it into a `{context}` haystack of `context_tokens`. Malformed
  files or entries are skipped, never fatal. Runs are sequential and refuse to
  start while an eval or speed probe is active (and vice versa).
- **Speed batches**: each probe row is one batch — `concurrency` parallel
  requests, `requests`/`errors`, `wall_s`, mean per-request `gen_tps`, and
  `agg_gen_tps` (total output tokens ÷ wall time, what you feel under load).
  `ttft_s` keeps the single-request meaning and equals `ttft_p50`; `ttft_p95`
  is the nearest-rank 95th percentile of the batch. Old rows have NULL batch
  columns and are treated as concurrency 1 by the charts.
- **Sustained runs**: `iterations` repeats each batch back-to-back under one
  `batch_id`; the Overview plots aggregate tokens/sec per iteration so a
  thermal or queueing drop is visible.
