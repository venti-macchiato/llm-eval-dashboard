import { useMemo } from "react";
import { api } from "../lib/api";
import { fmtInt, fmtNum, scoreTint, shortDate } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { configSummary, hardwareOf } from "../lib/meta";
import { Empty, ErrorNote, Panel, Spinner } from "../components/Ui";
import { IconDownload } from "../components/Icons";

export function Leaderboard() {
  const query = useAsync(() => api.leaderboard(), []);
  const data = query.data;

  const ranked = useMemo(() => {
    if (!data) return [];
    return data.models
      .map((model) => {
        const scores = data.tasks
          .map((task) => data.cells[model]?.[task]?.score ?? null)
          .filter((score): score is number => score !== null);
        const avg = scores.length
          ? scores.reduce((sum, score) => sum + score, 0) / scores.length
          : null;
        return { model, avg, count: scores.length };
      })
      .sort((a, b) => (b.avg ?? -1) - (a.avg ?? -1));
  }, [data]);

  if (query.error) return <ErrorNote>Failed to load leaderboard: {query.error}</ErrorNote>;
  if (query.loading && !data) return <Spinner />;
  if (!data || data.models.length === 0) {
    return (
      <Panel>
        <Empty>No scored runs yet. Run an eval or ingest logs to populate the leaderboard.</Empty>
      </Panel>
    );
  }

  return (
    <Panel
      title="Model × task leaderboard"
      hint={data.models.length ? "pooled mean ± 95% CI" : undefined}
      noBody
      actions={
        <a className="btn btn-sm" href="/api/export/runs.csv">
          <IconDownload /> CSV
        </a>
      }
    >
      <div className="matrix-wrap lb-wrap">
        <table className="matrix lb-matrix">
          <thead>
            <tr>
              <th className="row-head">Model</th>
              {data.tasks.map((task) => (
                <th key={task} className="lb-col-head">
                  {task}
                </th>
              ))}
              <th className="lb-avg-head">Avg</th>
            </tr>
          </thead>
          <tbody>
            {ranked.map(({ model, avg, count }) => (
              <tr key={model}>
                <th className="row-head" scope="row">
                  <span className="lb-row-id" title={model}>
                    {model}
                  </span>
                </th>
                {data.tasks.map((task) => {
                  const run = data.cells[model]?.[task] ?? null;
                  if (!run) {
                    return (
                      <td key={task}>
                        <span className="cell empty lb-cell">—</span>
                      </td>
                    );
                  }
                  const config = configSummary(hardwareOf(run));
                  const pooled = run.k > 1 ? ` · pooled from ${run.k} runs (${shortDate(run.first)} – ${shortDate(run.last)})` : "";
                  const title = `${run.score === null ? "no score" : fmtNum(run.score)} · ${run.samples ?? "?"} samples · ${shortDate(run.created)}${config ? ` · ${config}` : ""}${pooled}`;
                  const ci =
                    run.ci_low != null && run.ci_high != null
                      ? `${fmtNum(run.ci_low)}–${fmtNum(run.ci_high)}`
                      : null;
                  const se = run.stderr != null ? `se ${fmtNum(run.stderr, 3)}` : null;
                  const counts = [
                    run.samples != null ? `n=${fmtInt(run.samples)}` : null,
                    run.k > 1 ? `k=${run.k}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ");
                  const tint = scoreTint(run.score);
                  return (
                    <td key={task}>
                      <span
                        className="cell lb-cell"
                        style={tint ? { backgroundColor: tint } : undefined}
                        title={title}
                      >
                        <span className="lb-cell-score">{fmtNum(run.score)}</span>
                        {ci && <span className="cell-sub">CI {ci}</span>}
                        {se && <span className="cell-sub">{se}</span>}
                        {counts && <span className="cell-sub">{counts}</span>}
                      </span>
                    </td>
                  );
                })}
                <td className="lb-avg-cell">
                  <span className="lb-avg-value">{avg === null ? "—" : fmtNum(avg)}</span>
                  <span className="lb-avg-count">({fmtInt(count)})</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
