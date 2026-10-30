import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api";
import { fmtInt, fmtNum, shortDate } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { configSummary, hardwareOf } from "../lib/meta";
import { ConfigurationCompare } from "../components/ConfigurationCompare";
import { Empty, ErrorNote, Panel, Spinner } from "../components/Ui";
import type { Group } from "../types";

interface Metric {
  key: string;
  label: string;
  value: (group: Group) => number | null;
  format: (value: number | null) => string;
  highlight?: boolean;
}

const METRICS: Metric[] = [
  { key: "score", label: "Score (pooled)", value: (g) => g.score, format: (v) => fmtNum(v), highlight: true },
  {
    key: "ci",
    label: "95% CI ±",
    value: (g) => (g.stderr == null ? null : 1.96 * g.stderr),
    format: (v) => (v == null ? "—" : `±${fmtNum(v)}`),
    highlight: true,
  },
  { key: "k", label: "Repeats (k)", value: (g) => g.k, format: (v) => fmtInt(v) },
  { key: "samples", label: "Samples / run", value: (g) => g.samples, format: (v) => fmtInt(v) },
  { key: "input_tokens", label: "Input tokens", value: (g) => g.input_tokens, format: (v) => fmtInt(v) },
  { key: "output_tokens", label: "Output tokens", value: (g) => g.output_tokens, format: (v) => fmtInt(v) },
  {
    key: "duration_s",
    label: "Duration (all runs)",
    value: (g) => g.duration_s,
    format: (v) => (v == null ? "—" : `${fmtNum(v, 1)}s`),
  },
];

function label(group: Group): string {
  const config = configSummary(hardwareOf(group));
  return [
    shortDate(group.last),
    group.model,
    group.task,
    group.samples ? `n=${group.samples}` : null,
    group.k > 1 ? `${group.k}×` : null,
    config || null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function Compare() {
  const query = useAsync(() => api.groups(), []);
  const groups = useMemo(() => query.data ?? [], [query.data]);
  const [aId, setAId] = useState("");
  const [bId, setBId] = useState("");

  useEffect(() => {
    if (!groups.length || aId || bId) return;
    // Default to the most evidenced groups rather than the newest smoke run.
    const byEvidence = [...groups].sort(
      (x, y) => (y.total_samples ?? 0) - (x.total_samples ?? 0),
    );
    const a = byEvidence[0];
    const b =
      byEvidence.find((g) => g.task === a.task && g.model !== a.model) ??
      byEvidence.find((g) => g.task === a.task && g.eval_id !== a.eval_id) ??
      byEvidence[1];
    setAId(a.eval_id ?? "");
    setBId(b ? b.eval_id ?? "" : "");
  }, [groups, aId, bId]);

  const a = groups.find((g) => g.eval_id === aId);
  const b = groups.find((g) => g.eval_id === bId);

  if (query.error) return <ErrorNote>Failed to load runs: {query.error}</ErrorNote>;
  if (query.loading && !query.data) return <Spinner />;
  if (!groups.length) return <Panel><Empty>No runs to compare yet.</Empty></Panel>;

  const scoreA = a?.score ?? null;
  const scoreB = b?.score ?? null;
  const seA = a?.stderr ?? null;
  const seB = b?.stderr ?? null;
  const diff = scoreA !== null && scoreB !== null ? scoreB - scoreA : null;
  const seDiff = seA !== null && seB !== null ? Math.hypot(seA, seB) : null;
  const withinNoise = diff !== null && seDiff !== null ? Math.abs(diff) <= 1.96 * seDiff : null;
  // A reported stderr of exactly zero (e.g. a perfect score) cannot resolve a
  // difference; say so instead of claiming certainty from a zero-width interval.
  const noInterval = diff !== null && diff !== 0 && (seA === 0 || seB === 0);

  const hwA = hardwareOf(a);
  const hwB = hardwareOf(b);
  const pooled = (a?.k ?? 0) > 1 || (b?.k ?? 0) > 1;
  const summaryA = configSummary(hwA);
  const summaryB = configSummary(hwB);

  return (
    <div className="stack cx-compare">
      <section className="panel cx-picker">
        <header className="panel-head cx-picker-head">
          <div className="row cx-picker-headline">
            <span className="cx-picker-kicker">Workspace</span>
            <span className="panel-title">Head-to-head</span>
            <span className="panel-hint">repeated runs are pooled</span>
          </div>
          <span className="cx-picker-count">
            {groups.length} run{groups.length === 1 ? "" : "s"} available
          </span>
        </header>
        <div className="panel-body cx-picker-body">
          <div className="cx-picker-grid">
            <div className="cx-slot cx-slot-a">
              <div className="cx-slot-head">
                <span className="cx-slot-key" aria-hidden="true">A</span>
                <span className="field-label">Run A (model · task · config)</span>
              </div>
              <select
                className="select cx-select"
                value={aId}
                onChange={(e) => setAId(e.target.value)}
                title={a ? label(a) : "Run A"}
              >
                <option value="">Select a run…</option>
                {groups.map((g) => (
                  <option key={g.eval_id} value={g.eval_id}>{label(g)}</option>
                ))}
              </select>
              <div className="cx-slot-meta">
                {a ? (
                  <>
                    <span className="cx-meta-model">{a.model}</span>
                    <span className="cx-meta-sep" aria-hidden="true">/</span>
                    <span className="cx-meta-task">{a.task}</span>
                    {summaryA ? (
                      <span className="cx-meta-config">{summaryA}</span>
                    ) : (
                      <span className="cx-meta-missing">no hardware declared</span>
                    )}
                  </>
                ) : (
                  <span className="cx-meta-missing">No run selected</span>
                )}
              </div>
            </div>

            <div className="cx-vs" aria-hidden="true">vs</div>

            <div className="cx-slot cx-slot-b">
              <div className="cx-slot-head">
                <span className="cx-slot-key" aria-hidden="true">B</span>
                <span className="field-label">Run B (model · task · config)</span>
              </div>
              <select
                className="select cx-select"
                value={bId}
                onChange={(e) => setBId(e.target.value)}
                title={b ? label(b) : "Run B"}
              >
                <option value="">Select a run…</option>
                {groups.map((g) => (
                  <option key={g.eval_id} value={g.eval_id}>{label(g)}</option>
                ))}
              </select>
              <div className="cx-slot-meta">
                {b ? (
                  <>
                    <span className="cx-meta-model">{b.model}</span>
                    <span className="cx-meta-sep" aria-hidden="true">/</span>
                    <span className="cx-meta-task">{b.task}</span>
                    {summaryB ? (
                      <span className="cx-meta-config">{summaryB}</span>
                    ) : (
                      <span className="cx-meta-missing">no hardware declared</span>
                    )}
                  </>
                ) : (
                  <span className="cx-meta-missing">No run selected</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {a && b ? (
        <div className="grid grid-2">
          <Panel title="Metrics">
            <table className="data cx-metrics-table">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th className="num">A</th>
                  <th className="num">B</th>
                  <th className="num">Δ (B−A)</th>
                </tr>
              </thead>
              <tbody>
                {METRICS.map((metric) => {
                  const av = metric.value(a);
                  const bv = metric.value(b);
                  const delta = av !== null && bv !== null ? bv - av : null;
                  // a delta that renders as 0.000 must not read as a green gain
                  const negligible = delta !== null && Math.abs(delta) < 0.0005;
                  // only metrics whose direction means "better" carry a tone;
                  // a slower duration or a token count is not a gain
                  const sign =
                    delta === null
                      ? "na"
                      : !metric.highlight || negligible
                        ? "flat"
                        : delta > 0
                          ? "pos"
                          : "neg";
                  return (
                    <tr key={metric.key}>
                      <td>{metric.label}</td>
                      <td className="num">{metric.format(av)}</td>
                      <td className="num">{metric.format(bv)}</td>
                      <td className={`num cx-delta${metric.highlight ? " is-key" : ""}`}>
                        <span className={`cx-delta-chip is-${sign}`}>
                          {delta === null ? "—" : `${delta > 0 ? "+" : ""}${fmtNum(delta)}`}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="cx-metric-note">
              A: {a.model} / {a.task} · B: {b.model} / {b.task}
              {pooled && ` · ${a.k}× / ${b.k}× runs pooled`}
            </div>
            {noInterval ? (
              <div className="cx-noise cx-noise-note">
                <span className="cx-noise-mark" aria-hidden="true">i</span>
                <div className="cx-noise-copy">
                  <p className="cx-noise-text">
                    At least one estimate reports a zero interval (for example a perfect score),
                    so the difference cannot be tested against sampling noise.
                  </p>
                </div>
              </div>
            ) : (
              withinNoise !== null && (
                <div className={`cx-noise ${withinNoise ? "cx-noise-warn" : "cx-noise-ok"}`}>
                  <span className="cx-noise-mark" aria-hidden="true">{withinNoise ? "!" : "✓"}</span>
                  <div className="cx-noise-copy">
                    <p className="cx-noise-text">
                      {withinNoise
                        ? "Score difference is within sampling noise (95% CI)."
                        : "Score difference is outside sampling noise (95% CI)."}
                    </p>
                    {withinNoise && (
                      <p className="cx-noise-sub">
                        Do not report this as an improvement or a regression.
                      </p>
                    )}
                  </div>
                </div>
              )
            )}
          </Panel>

          <Panel title="Score comparison">
            <div className="chart-box tall">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={[
                    { name: "A", score: scoreA ?? 0 },
                    { name: "B", score: scoreB ?? 0 },
                  ]}
                  margin={{ top: 8, right: 12, bottom: 4, left: -12 }}
                >
                  <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 13, fill: "var(--muted)" }} />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 12.5, fill: "var(--muted)" }} width={44} />
                  <Tooltip formatter={(v: number) => fmtNum(v)} />
                  <Bar dataKey="score" radius={[6, 6, 0, 0]}>
                    <Cell fill="var(--c1)" />
                    <Cell fill="var(--c2)" />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Panel>
        </div>
      ) : (
        <Panel><Empty>Select two runs to compare.</Empty></Panel>
      )}

      {a && b && <ConfigurationCompare a={hwA} b={hwB} pooled={pooled} />}
    </div>
  );
}
