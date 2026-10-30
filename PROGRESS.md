# PROGRESS — LLM eval dashboard

## Status: frontend rebuilt, backend extended. Full suite: 134 passed.

## 2026-10-30 typography + demo data
- Proxima Nova is first in the font stack; `/api/fonts.css` emits `@font-face`
  rules for licensed `.woff2` files dropped into `static/fonts/` (empty when
  absent, so no 404s). Falls back to Montserrat/Inter/system UI.
- `seed_demo.py` inserts (and `--clear` removes) clearly-marked demo runs for
  three variants of the `polystrata` family, speed batches with concurrency and
  iterations, and two prompt runs; variants from unconfigured models join a
  family declared in `meta.base_model` (also written by ingest now).
- `tests/test_fonts.py`, a variants meta-family test, and a font CSS endpoint
  test, plus `tests/test_seed_demo.py` (tag scoping, timestamp formats, idempotency).

## 2026-10-29 sandbox preflight + UX gaps
- `sandbox.py`: Docker capability check (`docker version`) and the verified set
  of inspect_evals tasks that default to a Docker sandbox. `start_suite` refuses
  with an actionable 400 before claiming the job slot; `/api/preflight` feeds
  the UI, which warns, badges the tasks, and disables Start.
- Samples: `/api/run/{id}/samples?failures=1` filters failures server-side and
  pages over the filtered set; the drawer has Previous/Next and shows
  `1–200 of N`.
- A11y: clickable `<tr>` handlers replaced with real buttons (Runs "Open",
  sample "Details", prompt "Details"); SortableTable gained `rowAction`.
- Benchmark guide: collapsible category sections; undeclared category chips are
  derived from all entries so they no longer vanish while searching.
- Tests: sandbox unit tests + evalrun/API preflight, runlog filtering/paging.

## 2026-10-29 custom prompt harness
- `prompts.yaml` + `prompts.py`: nine starter tests across structured, tools,
  safety, long_context, and instruction, with checkers `json`, `tool_call`,
  `refusal`, `recall`, `contains`, `not_contains`, `regex`, `equals`,
  `max_words`. Malformed files/entries degrade to empty; `recall` generates a
  needle inside a `{context}` haystack.
- `promptharness.py`: sequential runner against the configured endpoint,
  per-test pass/detail/output/latency/tokens, repeats, cancel between tests,
  one run at a time; results in `prompt_runs` / `prompt_results`.
- `routes_prompts.py`: definitions, run/status/cancel/results. Eval, speed, and
  prompt starts now refuse to overlap (409) so the server still handles one
  stream of work at a time.
- Prompts view: model/repeats, live progress, pass-rate KPIs, expandable
  per-test results, and the definition list grouped by category.
- Tests: checker matrix, YAML validation, fake-server runner, storage, API
  validation/conflicts.

## 2026-10-29 concurrency and sustained-load speed
- `speedprobe.py` (split from `speed.py`): `probe_one` unchanged, plus
  `probe_batch` firing N concurrent streams and aggregating p50/p95 TTFT,
  mean per-request rates, and aggregate tokens/sec over wall time.
- `speed.py`: `run_probe(..., concurrency=[1,2,4,8], iterations=N)`; iterations
  share a `batch_id`. `speed` gained additive columns (`concurrency`,
  `batch_id`, `ttft_p50/p95`, `agg_gen_tps`, `requests`, `errors`, `wall_s`)
  via `db._MIGRATIONS`, and CSV export lists them.
- `/api/speed/run` validates concurrency (1–32) and iterations (1–20);
  `/api/speed/status` exposes the defaults.
- Overview: aggregate throughput and TTFT p95 by context (series per
  model × concurrency) plus a drift chart when a batch has multiple iterations.
  Run eval's probe panel gained concurrency chips (1/2/4/8) and an iterations
  field; default load stays one request.
- Tests: concurrent batch aggregation, failure counting, iterations/batch ids,
  schema migration, API validation.

## 2026-10-29 variant matrix + baseline regression
- `variants.py`: `base_model` groups model entries into a family; `baseline: true`
  marks the reference (or `?baseline=` overrides it). Reuses
  `aggregate.best_from_groups` so a cell matches the Leaderboard's evidence.
- Δ vs baseline uses pooled means with `se = hypot(se_variant, se_baseline)`;
  `within_noise` is `null` when either interval is missing or a zero interval
  cannot resolve a non-zero delta.
- New Variants view (7th): family chips, baseline select, variant × task matrix
  with score, 95% CI, k, and Δ (colour + `ns`/`?` markers). `/api/variants`
  added to `routes_analysis.py`; `aggregate.best_from_groups` factored out of
  the Leaderboard.
- Tests: `tests/test_variants.py` (families, baseline override, delta maths,
  unknown models, missing tasks) plus an API test.

## 2026-10-29 repeats + real confidence intervals
- `aggregate.py`: runs grouped by (model, task, declared hardware + generate
  config, epochs, sample count) and pooled. k=1 keeps the run's own stderr; k>1
  uses the unweighted run mean with
  `se = sqrt((var(scores) + mean(se_i²))/k)`, so between-run variance (seeds,
  sampler, server state) and each run's sampling error both contribute. With no
  reported stderr only between-run spread is used; zero spread is unknown, not
  ±0.
- Sample count is in the grouping key: a 5-sample and a 20-sample run cover
  different dataset slices. Without this the live DB pooled 1-sample smoke runs
  into a headline 0.975 ± 0.013 for gsm8k; the 20-sample group gives 0.917.
- Leaderboard cells are pooled groups; the cell keeps the newest configuration,
  then prefers the largest sample count within it. Compare now selects pooled
  groups (k, mean, 95% CI) instead of single runs.
- Runner: `repeats` (separate evals, default 1) and `epochs` (inspect flag);
  progress spans repeats (`repeat 2/3`, samples_done continues across runs);
  results are labelled `#1/#2`; `/api/eval/run` validates both (1–20).
- `/api/groups` added; Leaderboard/Compare consume it. `tests/test_aggregate.py`
  plus repeat/epoch argv and API-pooling tests.

## 2026-10-29 hardware/backend provenance
- `hardware.py`: per-model `hardware:` block (backend, version, quant, GPU,
  VRAM, ctx size, offload, host, notes) normalised and snapshotted into
  `run.meta.hardware.declared`; optional `host_probe` (nvidia-smi CSV) recorded
  as `run.meta.hardware.probe`, tagged with the probed hostname.
- Probe is gated on the endpoint being local: the configured server here is a
  tailnet peer, so a local GPU is never claimed as the server's hardware.
  Runs once per model per ingest; failures degrade to no probe.
- Ingest backfills hardware into rows ingested earlier (reported as `updated`)
  and stays idempotent afterwards (`merge_meta` only adds the missing key).
- `/api/models` returns declared hardware; Runs gained a Config column and
  searchable variant labels; the run drawer has a Hardware section; Compare has
  a configuration table that warns when quant/context/GPU differ; Leaderboard
  tooltips name the variant; Run eval shows the selected model's config.
- `config.yaml.example` documents both blocks; the live `config.yaml` declares
  `quant: Q3_K_XL` (from the served model id) and leaves `host_probe` disabled.

## 2026-10-30 evaluation depth
- Benchmark guide view + `benchmarks.yaml`: 56 curated tasks across 12
  categories, with what each measures and how to read the score; 11 starter
  suites. The Run eval picker groups tasks by category and shows descriptions.
- Provenance: runs now store `meta` (base URL, model id, dataset, epochs,
  sampling config, package versions, git commit) and `error_samples`.
  Additive migrations upgrade an existing `bench.db` in place.
- Per-sample drilldown: `/api/run/{id}/samples` reads the `.eval` log; the Runs
  drawer shows score, errors, input/target/output, and a failures-only filter.
- Uncertainty: Leaderboard shows ±stderr; Compare warns when a difference is
  inside the 95% sampling-noise band.
- Readability: larger charts (360/460 px), larger axes/legends, wider content,
  fixed KPI grid, denser-but-readable tables, benchmark/task cards.

## 2026-10-29 rebuild
- Frontend replaced with React 18 + TypeScript + Vite (`frontend/`), built to
  `static/dist` and served by FastAPI. Recharts for charts; clean-minimal theme
  with a light/dark toggle.
- Five views: Overview, Leaderboard, Runs, Compare, Run eval.
- Backend split into `api.py` (app + SPA), `routes_data.py`, `routes_eval.py`.
- New endpoints: multi-value model/task filters, `/api/leaderboard`,
  `/api/run/{eval_id}`, `/api/catalog`, `/api/export/{runs,speed}.{csv,json}`.
- Eval runs accept a task-list override and an endpoint override; live sample
  progress is parsed from inspect stdout split on CR and LF.
- Ingest backfills input/output tokens and duration from `.eval` log stats.
- Speed probe accepts context-size and model overrides.
- Removed the vanilla JS frontend and the vendored Chart.js.

## Reviewer feedback addressed (2026-10-28)
- `inspect_model` maps config names to the string inspect records; ingest
  stores the config name.
- Ingest returns `{new, skipped, updated}`; real errors raise instead of
  returning 0; the DB rolls back on failure.
- Speed probe: random prefix defeats caching; `out_tokens` is null when the
  server reports no usage; thread errors surface via `/api/speed/status`.
- Lifespan context manager initializes the schema.

## Files
- Backend: `api.py`, `routes_data.py`, `routes_export.py`, `routes_eval.py`,
  `query.py`, `catalog.py`, `benchmarks.py`, `benchmarks.yaml`, `runlog.py`,
  `config.py`, `db.py`, `ingest.py`, `runmeta.py`, `hardware.py`, `aggregate.py`,
  `evaljobs.py`, `evalrun.py`, `evaltasks.py`, `evalproc.py`, `modeljobs.py`,
  `speed.py`.
- Frontend: `frontend/src/{App.tsx,main.tsx,types.ts,views/,components/,lib/}`.
- Tests: `tests/test_ingest.py`, `tests/test_speed.py`, `tests/test_api.py`,
  `tests/test_evalrun.py`, `tests/test_runlog.py`, `tests/test_hardware.py`,
  `tests/test_aggregate.py`, `tests/test_variants.py`, `tests/test_prompts.py`,
  `tests/test_sandbox.py`, `tests/test_fonts.py`.

## Verified
- `pytest -q` → 134 passed.
- Browser smoke: all six views render with zero console errors.
- Custom eval (limit 3) reported 0/3 → 2/3 → 3/3 samples and ingested 1 run.
- Ingest backfilled tokens/duration/provenance for existing runs (13 updated).
- Per-sample drawer on an arc_challenge run: 20/20 scored, mean 0.900, matching
  the stored headline score.
- Hardware backfill on the live `bench.db`: 17 existing runs updated once, then
  a repeat ingest returned `updated: 0`; Runs shows `Q3_K_XL`, the drawer's
  Hardware section and the Compare configuration table render.
- Pooling on the live `bench.db`: gsm8k 0.917 (n=20, k=3, ±0.040),
  arc_challenge 0.900 (n=20, k=2, ±0.049), ifeval 0.833 (n=10, k=3, ±0.033);
  `/api/groups` returns 9 groups. Compare refuses to claim a noise verdict when
  either side reports a zero interval (e.g. a perfect 5-sample run). Missing
  stderr pools to `None` (unknown), never a fabricated ±0. Browser: Leaderboard cells show `± · k`, Compare defaults
  to the best-evidenced groups and posts `repeats`/`epochs`
  (`{"model":…,"repeats":3,"epochs":2,"suite":"smoke"}`), job progress shows
  "repeat 2/3" and result chips `#1/#2`.
