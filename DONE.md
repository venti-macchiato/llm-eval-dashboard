# DONE — LLM eval dashboard

Rebuilt frontend and extended the backend. Full suite: **134 passed**.

## Typography and demo data
- Proxima Nova first in the stack with a self-hosting path: licensed `.woff2`
  files in `static/fonts/` are served as `@font-face` by `/api/fonts.css`;
  otherwise Montserrat/Inter/system UI. No bundled commercial font.
- `seed_demo.py` / `--clear` populates runs (3 variants × 4 tasks × 3 repeats),
  speed batches (concurrency + iterations), and prompt results, all tagged
  `demo-`. Unconfigured models can join a family via `meta.base_model`.

## Sandbox preflight and UX gaps
- `sandbox.py` + `/api/preflight`: Docker is checked before a run; missing
  Docker returns an actionable 400, and the UI warns, badges affected tasks,
  and disables Start.
- Sample drilldown filters failures server-side and pages the filtered set.
- Row interactions are real buttons (Runs/Samples/Prompts), not clickable rows.
- Benchmark guide sections collapse; undeclared category chips stay visible
  while searching.

## Custom prompt harness
- `prompts.yaml` with nine starter tests; `prompts.py` implements the checkers
  (JSON schema, tool calls, refusal, recall, regex, equals, word limit,
  contains) and degrades safely on malformed YAML.
- `promptharness.py` runs tests sequentially with repeats and cancel, stores
  runs/results (latency, tokens, output, detail) in two new tables, and exposes
  status for progress.
- `/api/prompts`, `/api/prompts/run|status|cancel|results`; eval/speed/prompt
  starts are mutually exclusive (409).
- New **Prompts** view with pass-rate KPIs, expandable results, and the test
  catalogue. Tests use a fake chat-completions server.

## Concurrency and sustained-load speed
- `speedprobe.py` splits the HTTP measurement out of `speed.py`: `probe_batch`
  fires 1/2/4/8 concurrent streams and reports p50/p95 TTFT, mean per-request
  rates, errors, wall time, and aggregate tokens/sec.
- Additive `speed` columns (concurrency, batch id, percentiles, aggregate
  tokens/sec, requests, errors, wall time) with migration; CSV export updated.
- `iterations` repeats a batch back-to-back under one batch id for drift.
- Overview charts aggregate throughput and TTFT p95 per model × concurrency,
  plus a sustained-run drift chart; the probe panel selects concurrency and
  iterations (default one request).
- Tests: concurrent batching, failure counting, iterations, migration, API
  validation (`tests/test_speed.py`, `tests/test_api.py`).

## Variant matrix and baseline regression
- `base_model` groups model entries into a family; `baseline: true` (or the
  `baseline=` query parameter) chooses the reference variant.
- `variants.py` reuses the Leaderboard's best-group rule and reports
  Δ = variant − baseline with `se = hypot(se_variant, se_baseline)`, marking
  `ns` inside 95% noise and `?` when an interval is unavailable.
- New **Variants** view: family chips, baseline select, variant × task matrix
  with pooled score, 95% CI, k, and colour-coded Δ. `/api/variants` endpoint.
- `tests/test_variants.py` + API coverage.

## Repeats and real confidence intervals
- `aggregate.py` pools repeated runs per (model, task, declared hardware +
  generate config, epochs, sample count): k=1 keeps the run's stderr, k>1 uses
  the run mean with `se = sqrt((var(scores) + mean(se_i²))/k)`; when no run
  reports stderr only between-run spread is used, and zero spread yields an
  unknown interval rather than ±0.
- Runner accepts `repeats` (separate evals) and `epochs` (inspect `--epochs`),
  validates 1–20, scales progress by `limit × epochs`, shows repeat N of M, and
  labels result chips.
- Leaderboard cells are pooled; selection prefers the newest configuration,
  then dataset coverage within it. Compare selects pooled groups with k, mean,
  and 95% CI. `/api/groups` exposes groups to the UI.
- `tests/test_aggregate.py`, repeat/epoch argv tests (fake CLI), and pooled
  leaderboard/API tests.

## Hardware / backend provenance
- `hardware.py` — declared `hardware:` block from `config.yaml` (backend,
  version, quant, GPU, VRAM, ctx size, offload, host) plus opt-in local
  `nvidia-smi` probe; both snapshotted into `run.meta.hardware`.
- The probe only runs for a local endpoint and is tagged with the probed host,
  so local GPU evidence is not attributed to a remote server (a localhost
  port-forward is indistinguishable, hence the declared block).
- Ingest backfills hardware into existing runs once, then stays idempotent.
- `/api/models` exposes declared hardware.
- UI: Runs Config column (+ search), run drawer Hardware section, Compare
  configuration table with a mismatch warning, Leaderboard variant tooltip,
  Run eval model summary.

## Data layer
- `config.yaml` contract, `config.py`, `db.py`, `ingest.py`.
- Ingest is idempotent on `eval_id`; returns `{new, skipped, updated}` and
  backfills token counts / duration from `.eval` log stats.
- Real ingest errors raise instead of returning 0; the DB rolls back.

## API
- `api.py` — app shell, lifespan schema init, SPA serving from `static/dist`.
- `routes_data.py` — models, runs (multi-value filters), run detail, latest,
  trend, speed, leaderboard matrix, catalog.
- `routes_export.py` — CSV/JSON export for runs and speed samples.
- `routes_eval.py` — run eval (suite or explicit task list, endpoint override),
  job status with live progress, cancel, ingest, speed probe (context sizes).
- `query.py` — shared SQL helpers; `evalproc.py` — subprocess driver.

## Eval runner
- `evalrun.py` runs tasks in a background thread, publishes progress through
  `evaljobs`, parses inspect's `\r` progress line, and ingests on completion.
- Exactly one job at a time.

## Frontend (React + TypeScript + Vite)
- `frontend/src/App.tsx` — sidebar shell, light/dark toggle.
- Views: Overview (KPIs, per-task accuracy facets, speed charts), Leaderboard
  (model × task matrix), Runs (sortable table, drilldown, export, ingest),
  Compare (head-to-head), Run eval (suite or catalog composer, live progress,
  log tail, speed probe).
- Built output served from `static/dist`; dev server proxies `/api`.

## Evaluation depth
- `benchmarks.yaml` + `/api/benchmarks`: 56 curated benchmarks in 12
  categories with "what it measures" and "how to read the score"; 11 suites.
- Benchmark guide view; Run eval picker grouped by category with descriptions.
- Run provenance (`meta`) and `error_samples`, with additive DB migrations and
  backfill for existing rows.
- `/api/run/{eval_id}/samples` + Runs drawer: per-sample scores, error text,
  input/target/output, failures-only filter.
- Leaderboard shows ±stderr; Compare flags differences within sampling noise.

## Verified
- `pytest -q` → 134 passed (incl. `tests/test_evalrun.py` against a fake CLI,
  `tests/test_hardware.py` against a fake probe, `tests/test_aggregate.py`).
- Browser smoke: all six views render with zero console errors.
- Custom eval (limit 3) reported 0/3 → 2/3 → 3/3 and ingested 1 run.
- `curl` checks: catalog (249 tasks), leaderboard, CSV/JSON export.
- Hardware: live backfill reported 17 updated, second ingest 0 updated; Runs
  Config column, drawer Hardware section, Compare configuration table (same and
  differing configs), and Leaderboard tooltip all verified in the browser.
- Pooling: live leaderboard shows gsm8k 0.917 (n=20, k=3, ±0.040),
  arc_challenge 0.900 (k=2, ±0.049), ifeval 0.833 (n=10, k=3, ±0.033); Compare
  shows k and 95% CI; the run form posts repeats/epochs and progress renders
  "repeat 2/3".
