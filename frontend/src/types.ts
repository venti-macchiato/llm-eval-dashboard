export interface HardwareDeclared {
  backend?: string;
  backend_version?: string;
  quant?: string;
  gpu?: string | string[];
  vram_gb?: number;
  ctx_size?: number;
  offload?: string;
  host?: string;
  notes?: string;
  [key: string]: unknown;
}

export interface GpuInfo {
  name: string;
  memory_gb?: number;
  driver?: string;
}

export interface HardwareProbe {
  source?: string;
  host?: string;
  captured_at?: string;
  command?: string;
  gpus?: GpuInfo[];
}

export interface HardwareInfo {
  declared?: HardwareDeclared;
  probe?: HardwareProbe;
}

export interface ModelInfo {
  name: string;
  base_url: string;
  model_id: string;
  has_key: boolean;
  hardware?: HardwareDeclared;
}

export interface Run {
  eval_id: string;
  task: string;
  model: string;
  created: string;
  score: number | null;
  stderr: number | null;
  samples: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  duration_s: number | null;
  log_path: string | null;
  meta?: string | null;
  error_samples?: number | null;
}

export interface BenchmarkCategory {
  id: string;
  label: string;
  description: string;
}

export interface BenchmarkEntry {
  title: string;
  category: string;
  measures: string;
  read: string;
}

export interface BenchmarksPayload {
  categories: BenchmarkCategory[];
  benchmarks: Record<string, BenchmarkEntry>;
  suites: Record<string, { label: string; description: string }>;
}

export interface SampleRow {
  id: string | number;
  epoch: number | null;
  score: number | null;
  error: string | null;
  input: string | null;
  target: string | null;
  output: string | null;
}

export interface RunSamples {
  eval_id: string;
  total: number;
  scored: number;
  errors: number;
  failures: number;
  mean_score: number | null;
  has_samples: boolean;
  offset: number;
  limit: number;
  failures_only: boolean;
  filtered_total: number;
  samples: SampleRow[];
}

export interface SpeedRow {
  id: number;
  model: string;
  ts: string;
  ctx_tokens: number | null;
  ttft_s: number | null;
  prefill_tps: number | null;
  gen_tps: number | null;
  out_tokens: number | null;
  concurrency?: number | null;
  batch_id?: string | null;
  ttft_p50?: number | null;
  ttft_p95?: number | null;
  agg_gen_tps?: number | null;
  requests?: number | null;
  errors?: number | null;
  wall_s?: number | null;
}

export interface VariantInfo {
  model: string;
  config: HardwareDeclared;
  configured_baseline: boolean;
  is_baseline: boolean;
}

export interface Regression {
  delta: number;
  se: number | null;
  ci_low: number | null;
  ci_high: number | null;
  within_noise: boolean | null;
  variant_score: number;
  variant_se: number | null;
  baseline_score: number;
  baseline_se: number | null;
}

export interface VariantFamily {
  base_model: string;
  baseline: string | null;
  variants: VariantInfo[];
  tasks: string[];
  cells: Record<string, Record<string, Group | null>>;
  regressions: Record<string, Record<string, Regression | null>>;
}

export interface VariantsPayload {
  families: VariantFamily[];
}

export interface PreflightCapability {
  available: boolean;
  detail: string | null;
}

export interface Preflight {
  capabilities: Record<string, PreflightCapability>;
  requirements: Record<string, string[]>;
}

export interface PromptCheck {
  type: string;
  [key: string]: unknown;
}

export interface PromptTest {
  id: string;
  title: string;
  category: string;
  description: string;
  prompt: string;
  check: PromptCheck;
  max_tokens: number;
  temperature: number;
  context_tokens: number;
  system?: string;
  tools?: unknown[];
}

export interface PromptResult {
  id: number;
  run_id: string;
  model: string;
  ts: string;
  test_id: string;
  title: string;
  category: string;
  repeat: number;
  passed: number;
  output: string | null;
  detail: string | null;
  latency_s: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  error: string | null;
}

export interface PromptRun {
  run_id: string;
  model: string;
  ts: string;
  completed: string;
  tests: number;
  passed: number;
  errors: number;
  repeats: number;
  results: PromptResult[];
}

export interface PromptStatus {
  running: boolean;
  state: string;
  model: string | null;
  run_id: string | null;
  done: number;
  total: number;
  current: string | null;
  error: string | null;
  passed: number;
  failed: number;
}

export interface PromptsPayload {
  tests: PromptTest[];
  running: boolean;
  error: string | null;
}

export interface LatestRow {
  model: string;
  task: string;
  score: number | null;
  prev_score: number | null;
  created: string;
  stderr: number | null;
  samples: number | null;
}

export interface Group extends Run {
  k: number;
  scores: number[];
  ci_low: number | null;
  ci_high: number | null;
  total_samples: number | null;
  eval_ids: string[];
  first: string | null;
  last: string | null;
  config: Record<string, unknown>;
}

export interface Leaderboard {
  models: string[];
  tasks: string[];
  cells: Record<string, Record<string, Group | null>>;
}

export interface CatalogEntry {
  task: string;
  id: string;
}

export interface EvalJob {
  state: "running" | "done" | "failed";
  model: string;
  suite: string;
  task_index: number;
  task_total: number;
  samples_done: number;
  samples_total: number;
  error: string | null;
  log_tail: string[];
  results: {
    task: string;
    ok: boolean;
    repeat?: number | null;
    repeats?: number | null;
  }[];
  repeat_index?: number;
  repeat_total?: number;
  started_at?: string;
  finished_at?: string;
  current_task?: string | null;
}

export interface TaskSpec {
  task: string;
  limit: number;
}
