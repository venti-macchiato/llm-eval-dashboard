import type { SpeedRow } from "../types";

export type SpeedMetric = "agg" | "ttft";

/** Concurrency is absent on rows written before the batch columns existed. */
export function levelOf(row: SpeedRow): number {
  return row.concurrency ?? 1;
}

export function seriesLabel(model: string, level: number): string {
  return level > 1 ? `${model} · c${level}` : model;
}

function metricValue(row: SpeedRow, metric: SpeedMetric): number | null {
  if (metric === "agg") return row.agg_gen_tps ?? row.gen_tps ?? null;
  return row.ttft_p95 ?? row.ttft_s ?? null;
}

/**
 * One point per context size, with the mean value per (model, concurrency)
 * series. Old single-request rows fall back to gen_tps / ttft_s.
 */
export function speedSeries(rows: SpeedRow[], metric: SpeedMetric) {
  const labels = [...new Set(rows.map((row) => seriesLabel(row.model, levelOf(row))))].sort();
  const indexOf = new Map(labels.map((label, index) => [label, index]));
  const buckets = new Map<number, Map<string, number[]>>();

  for (const row of rows) {
    const value = metricValue(row, metric);
    if (value === null || !Number.isFinite(value)) continue;
    const ctx = row.ctx_tokens ?? 0;
    const byLabel = buckets.get(ctx) ?? new Map<string, number[]>();
    const label = seriesLabel(row.model, levelOf(row));
    byLabel.set(label, [...(byLabel.get(label) ?? []), value]);
    buckets.set(ctx, byLabel);
  }

  // Keys are m0, m1, … because Recharts treats dataKey as a lodash path.
  const data = [...buckets.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([ctx, byLabel]) => {
      const point: Record<string, number> = { ctx };
      for (const [label, values] of byLabel) {
        point[`m${indexOf.get(label)}`] =
          values.reduce((sum, value) => sum + value, 0) / values.length;
      }
      return point;
    });

  return { labels, data };
}

export interface DriftSeries {
  labels: string[];
  data: Record<string, number>[];
}

/**
 * Batches probed more than once (iterations > 1), plotted in run order so a
 * throughput drop across a sustained run is visible.
 */
export function driftSeries(rows: SpeedRow[]): DriftSeries | null {
  const batches = new Map<string, SpeedRow[]>();
  for (const row of rows) {
    if (!row.batch_id) continue;
    batches.set(row.batch_id, [...(batches.get(row.batch_id) ?? []), row]);
  }
  const repeated = [...batches.values()]
    .filter((list) => list.length > 1)
    .map((list) => [...list].sort((a, b) => a.id - b.id));
  if (!repeated.length) return null;

  const labels = repeated.map((list) => {
    const first = list[0];
    const ctx = first.ctx_tokens ? `${Math.round(first.ctx_tokens / 1000)}k` : "?";
    return `${first.model} · ${ctx} · c${levelOf(first)}`;
  });
  const length = Math.max(...repeated.map((list) => list.length));

  const data: Record<string, number>[] = [];
  for (let index = 0; index < length; index += 1) {
    const point: Record<string, number> = { i: index + 1 };
    repeated.forEach((list, series) => {
      const row = list[index];
      const value = row ? row.agg_gen_tps ?? row.gen_tps : null;
      if (value !== null && value !== undefined) point[`b${series}`] = value;
    });
    data.push(point);
  }
  return { labels, data };
}
