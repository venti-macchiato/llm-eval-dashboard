import type {
  BenchmarksPayload,
  CatalogEntry,
  EvalJob,
  Group,
  LatestRow,
  Leaderboard,
  ModelInfo,
  Preflight,
  PromptRun,
  PromptsPayload,
  PromptStatus,
  Run,
  RunSamples,
  SpeedRow,
  TaskSpec,
  VariantsPayload,
} from "../types";

type Params = Record<string, string | number | string[] | undefined | null>;

function qs(params: Params = {}): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) {
        parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(item)}`);
      }
    } else {
      parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
    }
  }
  return parts.join("&");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (body?.detail) {
        msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* non-JSON error body */
    }
    throw new Error(msg);
  }
  return (await res.json()) as T;
}

export const api = {
  models: () => request<ModelInfo[]>("/api/models"),
  runs: (p?: Params) => request<Run[]>(`/api/runs?${qs({ limit: 10000, ...p })}`),
  run: (id: string) => request<Run>(`/api/run/${encodeURIComponent(id)}`),
  latest: (models?: string[]) =>
    request<LatestRow[]>(`/api/latest?${qs({ models: models?.join(",") })}`),
  trend: (model: string, task: string) =>
    request<{ created: string; score: number | null; stderr: number | null }[]>(
      `/api/trend?${qs({ model, task })}`,
    ),
  speed: (p?: Params) => request<SpeedRow[]>(`/api/speed?${qs({ limit: 10000, ...p })}`),
  leaderboard: (p?: Params) => request<Leaderboard>(`/api/leaderboard?${qs(p)}`),
  groups: (p?: Params) => request<Group[]>(`/api/groups?${qs({ limit: 5000, ...p })}`),
  variants: (p?: Params) => request<VariantsPayload>(`/api/variants?${qs(p)}`),
  preflight: (refresh = false) =>
    request<Preflight>(`/api/preflight${refresh ? "?refresh=1" : ""}`),
  prompts: () => request<PromptsPayload>("/api/prompts"),
  promptStatus: () => request<PromptStatus>("/api/prompts/status"),
  promptRun: (body: unknown) =>
    request<{ started: boolean; run_id?: string; reason?: string }>("/api/prompts/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  promptCancel: () =>
    request<{ cancelled: boolean }>("/api/prompts/cancel", { method: "POST" }),
  promptResults: (p?: Params) =>
    request<{ runs: PromptRun[] }>(`/api/prompts/results?${qs({ limit: 5, ...p })}`),
  catalog: () => request<CatalogEntry[]>("/api/catalog"),
  benchmarks: () => request<BenchmarksPayload>("/api/benchmarks"),
  runSamples: (id: string, limit = 200, offset = 0, failures = false) =>
    request<RunSamples>(
      `/api/run/${encodeURIComponent(id)}/samples?${qs({ limit, offset, failures: failures ? 1 : 0 })}`,
    ),
  suites: () => request<Record<string, TaskSpec[]>>("/api/suites"),
  evalStatus: () => request<EvalJob | Record<string, never>>("/api/eval/status"),
  runEval: (body: unknown) =>
    request<{ started: boolean; reason?: string }>("/api/eval/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  cancelEval: () =>
    request<{ cancelled: boolean }>("/api/eval/cancel", { method: "POST" }),
  ingest: () =>
    request<{ new: number; skipped: number; updated: number }>("/api/ingest", {
      method: "POST",
    }),
  speedRun: (body?: unknown) =>
    request<{ started: boolean }>("/api/speed/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    }),
  speedStatus: () =>
    request<{ running: boolean; error: string | null; context_sizes: number[]; models: string[] }>(
      "/api/speed/status",
    ),
};

export function exportUrl(
  table: "runs" | "speed",
  fmt: "csv" | "json",
  params: Params = {},
): string {
  return `/api/export/${table}.${fmt}?${qs(params)}`;
}
