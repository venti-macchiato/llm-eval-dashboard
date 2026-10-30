import { useMemo, useState, type CSSProperties } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TooltipProps } from "recharts";
import { api } from "../lib/api";
import { fmtNum, shortDate, timeAgo, toDate } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useSeriesColors } from "../lib/theme";
import { driftSeries, speedSeries } from "../lib/speed";
import { ChipFilter } from "../components/ChipFilter";
import { Empty, ErrorNote, Kpi, Panel, Spinner } from "../components/Ui";
import type { Run } from "../types";

const axisTick = { fontSize: 11.5, fill: "var(--muted)" } as const;

/** Recharts treats dataKey as a lodash path, so series keys must not contain
 * dots. Map model names to `m0`, `m1`, … and pass the real name via `name`. */
function keyMap(models: string[]): Map<string, string> {
  return new Map(models.map((model, index) => [model, `m${index}`]));
}

function taskSeries(runs: Run[], task: string) {
  const rows = runs
    .filter((r) => r.task === task && r.score !== null)
    .sort((a, b) => (toDate(a.created)?.getTime() ?? 0) - (toDate(b.created)?.getTime() ?? 0));
  const models = [...new Set(rows.map((r) => r.model))];
  const keyOf = keyMap(models);
  const data = rows.map((r) => ({
    t: toDate(r.created)?.getTime() ?? 0,
    [keyOf.get(r.model)!]: r.score,
  }));
  return { models, data };
}

/* ---------------------------------------------------------------- neon layer
   Presentation only: every helper below derives colours, gradient ids and the
   drift overlay from the series it is handed. No metric is recomputed here. */

interface NeonSeries {
  key: string;
  name: string;
  color: string;
  /** gradient area under the stroke; off for overlay-only traces */
  fill?: boolean;
  /** legend swatch; off for overlay-only traces */
  legend?: boolean;
  /** keep out of the tooltip (overlay traces duplicate a real series) */
  overlay?: boolean;
  /** css glow class applied to the curve */
  glow?: string;
}

type AccentName = "cyan" | "violet" | "amber";

const ACCENTS: Record<
  AccentName,
  { base: string; blend: string; glow: string; spread: number }
> = {
  // tokens only: both themes resolve these through base.css
  cyan: { base: "var(--neon-cyan)", blend: "var(--accent)", glow: "neon-line-cyan", spread: 70 },
  violet: { base: "var(--neon-violet)", blend: "var(--accent)", glow: "neon-line-violet", spread: 70 },
  // amber stays in the warning family end to end: only a hint of rose at the tail
  amber: { base: "var(--neon-amber)", blend: "var(--neon-rose)", glow: "neon-line-amber", spread: 32 },
};

/**
 * Colour for series `index` of `count` inside one accent family: the first
 * trace is the pure accent, later ones drift toward a sibling hue so
 * overlapping loads stay separable while the panel reads as one channel.
 */
function accentStroke(accent: AccentName, index: number, count: number): string {
  const { base, blend, spread } = ACCENTS[accent];
  if (count <= 1) return base;
  const share = Math.round((index / (count - 1)) * spread);
  return share === 0 ? base : `color-mix(in srgb, ${base} ${100 - share}%, ${blend})`;
}

function accentSeries(accent: AccentName, labels: string[], keyPrefix = "m"): NeonSeries[] {
  return labels.map((label, index) => ({
    key: `${keyPrefix}${index}`,
    name: label,
    color: accentStroke(accent, index, labels.length),
    glow: ACCENTS[accent].glow,
  }));
}

/** Sustained-load series that finished ≥12% below their peak get a tail. */
const DRIFT_DROP = 0.88;

function driftTails(data: Record<string, number>[], labels: string[]) {
  const rows = data.map((point) => ({ ...point }));
  const tails: NeonSeries[] = [];
  labels.forEach((label, index) => {
    const key = `b${index}`;
    let peak = -Infinity;
    let peakAt = -1;
    let lastAt = -1;
    rows.forEach((point, at) => {
      const value = point[key];
      if (typeof value !== "number") return;
      lastAt = at;
      if (value > peak) {
        peak = value;
        peakAt = at;
      }
    });
    if (peakAt < 0 || lastAt <= peakAt) return;
    const last = rows[lastAt][key];
    if (typeof last !== "number" || last > peak * DRIFT_DROP) return;
    const tailKey = `t${index}`;
    for (let at = peakAt; at <= lastAt; at += 1) {
      const value = rows[at][key];
      if (typeof value === "number") rows[at][tailKey] = value;
    }
    tails.push({
      key: tailKey,
      name: label,
      color: "var(--neon-amber)",
      fill: false,
      legend: false,
      overlay: true,
      glow: "neon-line-amber-hot",
    });
  });
  return { rows, tails };
}

function NeonTooltip({
  active,
  payload,
  label,
  labelFormat,
  digits = 1,
  hideKeys,
}: TooltipProps<number, string> & {
  labelFormat: (value: number) => string;
  digits?: number;
  hideKeys?: string[];
}) {
  const rows = (payload ?? []).filter(
    (entry) => entry.dataKey !== undefined && !hideKeys?.includes(String(entry.dataKey)),
  );
  if (!active || rows.length === 0) return null;
  return (
    <div
      className="neon-tooltip"
      style={{
        background: "var(--panel-solid)",
        borderColor: "var(--border-strong)",
        borderRadius: "var(--r-sm)",
      }}
    >
      <div className="neon-tooltip-label">{labelFormat(Number(label))}</div>
      {rows.map((entry, index) => (
        <div className="neon-tooltip-row" key={`${String(entry.dataKey)}-${index}`}>
          <span className="neon-tooltip-dot" style={{ background: entry.color }} />
          <span className="neon-tooltip-name">{entry.name}</span>
          <span className="neon-tooltip-value">{fmtNum(entry.value as number, digits)}</span>
        </div>
      ))}
    </div>
  );
}

interface NeonChartProps {
  data: Record<string, number | null>[];
  series: NeonSeries[];
  xKey: string;
  /** unique per chart: used to namespace gradient ids in <defs> */
  gradientId: string;
  xTickFormatter: (value: number) => string;
  yTickFormatter?: (value: number) => string;
  xDomain?: [number | string, number | string];
  xAllowDecimals?: boolean;
  yDomain?: [number | string, number | string];
  yWidth?: number;
  dotRadius?: number;
  curve?: "monotone" | "linear";
  tooltipLabel: (value: number) => string;
  digits: number;
  accent?: string;
}

function NeonChart({
  data,
  series,
  xKey,
  gradientId,
  xTickFormatter,
  yTickFormatter,
  xDomain,
  xAllowDecimals,
  yDomain,
  yWidth = 46,
  dotRadius = 3,
  curve = "monotone",
  tooltipLabel,
  digits,
  accent = "var(--accent)",
}: NeonChartProps) {
  // overlay traces restate a real series; keep them out of the tooltip
  const hideKeys = series.filter((item) => item.overlay).map((item) => item.key);
  return (
    <div className="chart-box" style={{ "--chart-accent": accent } as CSSProperties}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: -14 }}>
          <defs>
            {series.map((item, index) => (
              <linearGradient
                key={item.key}
                id={`${gradientId}-${index}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop offset="0%" stopColor={item.color} stopOpacity={1} />
                <stop offset="55%" stopColor={item.color} stopOpacity={0.35} />
                <stop offset="100%" stopColor={item.color} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>

          <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey={xKey}
            type="number"
            domain={xDomain}
            tick={axisTick}
            tickFormatter={xTickFormatter}
            axisLine={false}
            tickLine={false}
            tickMargin={8}
            minTickGap={24}
            allowDecimals={xAllowDecimals}
          />
          <YAxis
            domain={yDomain}
            tick={axisTick}
            tickFormatter={yTickFormatter}
            width={yWidth}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            content={
              <NeonTooltip labelFormat={tooltipLabel} digits={digits} hideKeys={hideKeys} />
            }
            cursor={{ stroke: "var(--border-strong)", strokeDasharray: "3 3" }}
            wrapperStyle={{ outline: "none" }}
          />
          <Legend
            iconType="plainline"
            iconSize={10}
            wrapperStyle={{ fontSize: 11, paddingTop: 2 }}
          />

          {series.map((item, index) => (
            <Area
              key={item.key}
              type={curve}
              dataKey={item.key}
              name={item.name}
              className={item.glow}
              stroke={item.color}
              strokeWidth={item.fill === false ? 2.5 : 2}
              fill={item.fill === false ? "none" : `url(#${gradientId}-${index})`}
              fillOpacity={1}
              dot={
                item.overlay ? false : { r: dotRadius, strokeWidth: 0, fill: item.color }
              }
              activeDot={
                item.overlay ? false : { r: dotRadius + 2, strokeWidth: 0, fill: item.color }
              }
              connectNulls
              legendType={item.legend === false ? "none" : "line"}
              isAnimationActive
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Overview() {
  const modelsQ = useAsync(api.models, []);
  const runsQ = useAsync(() => api.runs(), []);
  const speedQ = useAsync(() => api.speed(), []);
  const colors = useSeriesColors();

  const [selModels, setSelModels] = useState<Set<string>>(new Set());
  const [selTasks, setSelTasks] = useState<Set<string>>(new Set());

  const allRuns = runsQ.data ?? [];
  const allSpeed = speedQ.data ?? [];

  const modelOptions = useMemo(
    () => [...new Set(allRuns.map((r) => r.model).filter(Boolean))].sort(),
    [allRuns],
  );
  const taskOptions = useMemo(
    () => [...new Set(allRuns.map((r) => r.task).filter(Boolean))].sort(),
    [allRuns],
  );

  const runs = useMemo(
    () =>
      allRuns.filter(
        (r) =>
          (selModels.size === 0 || selModels.has(r.model)) &&
          (selTasks.size === 0 || selTasks.has(r.task)),
      ),
    [allRuns, selModels, selTasks],
  );

  const speed = useMemo(
    () => allSpeed.filter((s) => selModels.size === 0 || selModels.has(s.model)),
    [allSpeed, selModels],
  );

  const kpis = useMemo(() => {
    const scored = runs.filter((r) => r.score !== null);
    const best = scored.reduce<number | null>(
      (acc, r) => (acc === null || (r.score ?? 0) > acc ? r.score : acc),
      null,
    );
    const latest = runs.reduce<string | null>(
      (acc, r) => (acc === null || String(r.created) > acc ? String(r.created) : acc),
      null,
    );
    return {
      runs: runs.length,
      models: new Set(runs.map((r) => r.model)).size,
      tasks: new Set(runs.map((r) => r.task)).size,
      best,
      latest,
    };
  }, [runs]);

  const activeTasks = selTasks.size ? [...selTasks] : taskOptions;
  const shownTasks = activeTasks.slice(0, 6);
  const throughput = speedSeries(speed, "agg");
  const ttft = speedSeries(speed, "ttft");
  const drift = driftSeries(speed);
  const driftView = drift ? driftTails(drift.data, drift.labels) : null;

  if (runsQ.error) return <ErrorNote>Failed to load runs: {runsQ.error}</ErrorNote>;
  if (runsQ.loading && !runsQ.data) return <Spinner />;

  return (
    <div className="stack">
      <div className="panel" style={{ padding: 16 }}>
        <div className="row" style={{ gap: 28, alignItems: "flex-start" }}>
          <ChipFilter label="Models" options={modelOptions} selected={selModels} onChange={setSelModels} />
          <ChipFilter label="Tasks" options={taskOptions} selected={selTasks} onChange={setSelTasks} />
        </div>
      </div>

      <div className="kpi-row">
        <Kpi label="Runs" value={kpis.runs} sub={`${modelsQ.data?.length ?? 0} configured models`} />
        <Kpi label="Models" value={kpis.models} />
        <Kpi label="Tasks" value={kpis.tasks} />
        <Kpi label="Best score" value={fmtNum(kpis.best)} sub="across filtered runs" />
        <Kpi label="Last run" value={kpis.latest ? timeAgo(kpis.latest) : "—"} sub={kpis.latest ? shortDate(kpis.latest) : undefined} />
        <Kpi label="Speed samples" value={speed.length} />
      </div>

      <div>
        <h2 style={{ marginBottom: 12 }}>Accuracy trend</h2>
        {shownTasks.length === 0 ? (
          <Panel><Empty>No scored runs yet. Run an eval or ingest logs.</Empty></Panel>
        ) : (
          <div className="grid grid-auto">
            {shownTasks.map((task) => {
              const { models: taskModels, data } = taskSeries(runs, task);
              const series: NeonSeries[] = taskModels.map((model, i) => ({
                key: `m${i}`,
                name: model,
                color: colors[i % colors.length],
                glow: "neon-line-soft",
              }));
              return (
                <Panel key={task} title={task} hint={`${taskModels.length} model(s)`} noBody>
                  {data.length === 0 ? (
                    <div className="panel-body"><Empty>No scores.</Empty></div>
                  ) : (
                    <div className="chart-slot">
                      <NeonChart
                        data={data}
                        series={series}
                        xKey="t"
                        gradientId={`acc-${task.replace(/[^a-z0-9_-]/gi, "")}`}
                        xDomain={["dataMin", "dataMax"]}
                        yDomain={["auto", "auto"]}
                        yWidth={44}
                        xTickFormatter={(v: number) => shortDate(new Date(v).toISOString())}
                        yTickFormatter={(v: number) => v.toFixed(2)}
                        tooltipLabel={(v: number) => shortDate(new Date(v).toISOString())}
                        digits={3}
                        accent={series[0]?.color ?? "var(--accent)"}
                      />
                    </div>
                  )}
                </Panel>
              );
            })}
          </div>
        )}
      </div>

      <div>
        <h2 style={{ marginBottom: 12 }}>Speed</h2>
        {speed.length === 0 ? (
          <Panel><Empty>No speed samples yet. Run a speed probe from the Run eval tab.</Empty></Panel>
        ) : (
          <div className="grid grid-2">
            <Panel title="Aggregate throughput" hint="tokens/sec under load" noBody>
              <div className="chart-slot">
                <NeonChart
                  data={throughput.data}
                  series={accentSeries("cyan", throughput.labels).map((item, i) => ({
                    ...item,
                    fill: i === 0,
                  }))}
                  xKey="ctx"
                  gradientId="tp"
                  dotRadius={4}
                  xTickFormatter={(v: number) => `${Math.round(v / 1000)}k`}
                  tooltipLabel={(v: number) => `${Number(v).toLocaleString()} ctx`}
                  digits={1}
                  accent="var(--neon-cyan)"
                />
              </div>
            </Panel>
            <Panel title="Time to first token" hint="p95, seconds" noBody>
              <div className="chart-slot">
                <NeonChart
                  data={ttft.data}
                  series={accentSeries("violet", ttft.labels).map((item, i) => ({
                    ...item,
                    fill: i === 0,
                  }))}
                  xKey="ctx"
                  gradientId="ttft"
                  dotRadius={4}
                  xTickFormatter={(v: number) => `${Math.round(v / 1000)}k`}
                  tooltipLabel={(v: number) => `${Number(v).toLocaleString()} ctx`}
                  digits={3}
                  accent="var(--neon-violet)"
                />
              </div>
            </Panel>
            {drift && driftView && (
              <Panel title="Sustained run" hint="aggregate tokens/sec per iteration" noBody>
                <div className="chart-slot">
                  <NeonChart
                    data={driftView.rows}
                    series={[
                      ...accentSeries("amber", drift.labels, "b").map((item) => ({
                        ...item,
                        fill: false,
                        // only the degraded tail carries the hot aura
                        glow: undefined,
                      })),
                      ...driftView.tails,
                    ]}
                    xKey="i"
                    gradientId="drift"
                    curve="linear"
                    xAllowDecimals={false}
                    xTickFormatter={(v: number) => `#${v}`}
                    tooltipLabel={(v: number) => `iteration ${v}`}
                    digits={1}
                    accent="var(--neon-amber)"
                  />
                </div>
              </Panel>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
