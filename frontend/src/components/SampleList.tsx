import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { fmtNum } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { Empty, ErrorNote, Spinner } from "./Ui";
import type { Run, SampleRow } from "../types";

const PAGE = 200;

function SampleDetail({ sample }: { sample: SampleRow }) {
  return (
    <div className="hx-ide">
      <div className="hx-ide-head">
        <span className="hx-ide-lights" aria-hidden="true" />
        <span className="hx-ide-title">sample/{sample.id}</span>
        {sample.epoch != null && <span className="hx-ide-tag">epoch&nbsp;{sample.epoch}</span>}
        {sample.score != null && <span className="hx-ide-tag">score&nbsp;{fmtNum(sample.score)}</span>}
      </div>
      <div className="hx-ide-body">
        {sample.input && (
          <section className="hx-pane hx-pane-input">
            <header className="hx-pane-label">Input</header>
            <pre className="hx-pane-pre">{sample.input}</pre>
          </section>
        )}
        {sample.target && (
          <section className="hx-pane hx-pane-target">
            <header className="hx-pane-label">Target</header>
            <pre className="hx-pane-pre">{sample.target}</pre>
          </section>
        )}
        {sample.output && (
          <section className="hx-pane hx-pane-output">
            <header className="hx-pane-label">Output</header>
            <pre className="hx-pane-pre">{sample.output}</pre>
          </section>
        )}
        {sample.error && (
          <section className="hx-pane hx-pane-error">
            <header className="hx-pane-label">Error</header>
            <pre className="hx-pane-pre">{sample.error}</pre>
          </section>
        )}
      </div>
    </div>
  );
}

function SampleRowView({
  sample,
  open,
  onToggle,
}: {
  sample: SampleRow;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr className="hx-row">
        <td className="mono small hx-sample-id">{sample.id}</td>
        <td className="num hx-sample-score">{fmtNum(sample.score)}</td>
        <td className="small hx-sample-detail">
          {sample.error ? (
            <span className="hx-sample-err">{sample.error}</span>
          ) : sample.output ? (
            <span className="hx-sample-preview">{sample.output.slice(0, 120)}</span>
          ) : (
            "—"
          )}
        </td>
        <td className="num">
          <button
            className="btn btn-sm"
            onClick={onToggle}
            aria-expanded={open}
            aria-label={`${open ? "Hide" : "Show"} sample ${sample.id} details`}
          >
            {open ? "Hide" : "Details"}
          </button>
        </td>
      </tr>
      {open && (
        <tr className="hx-expand">
          <td colSpan={4}>
            <SampleDetail sample={sample} />
          </td>
        </tr>
      )}
    </>
  );
}

/** Per-sample drilldown: server-side failure filter and pagination. */
export function SampleList({ run }: { run: Run }) {
  const [onlyFailures, setOnlyFailures] = useState(false);
  const [offset, setOffset] = useState(0);
  const [expanded, setExpanded] = useState<string | number | null>(null);

  useEffect(() => {
    setOffset(0);
  }, [run.eval_id]);

  const query = useAsync(
    () => api.runSamples(run.eval_id, PAGE, offset, onlyFailures),
    [run.eval_id, offset, onlyFailures],
  );

  const report = query.data;
  const rows = report?.samples ?? [];
  const rangeStart = (report?.offset ?? 0) + 1;
  const rangeEnd = (report?.offset ?? 0) + rows.length;
  const page = Math.floor(offset / PAGE) + 1;
  const pageCount = Math.max(1, Math.ceil((report?.filtered_total ?? 0) / PAGE));

  return (
    <div className="hx-samples">
      <div className="hx-samples-head">
        <h3>Samples</h3>
        {report && (
          <span className="small muted hx-samples-summary">
            {report.scored}/{report.total} scored
            {report.errors > 0 && `, ${report.errors} errored`}
            {report.failures > 0 && `, ${report.failures} failed`}
            {report.mean_score !== null && ` · mean ${fmtNum(report.mean_score)}`}
          </span>
        )}
      </div>

      <label className="hx-samples-filter">
        <input
          type="checkbox"
          checked={onlyFailures}
          onChange={(event) => {
            // Change filter and page together so only one request fires.
            setOnlyFailures(event.target.checked);
            setOffset(0);
          }}
        />
        Only failures (error or score 0), filtered on the server
      </label>

      {query.loading && <Spinner label="Reading log…" />}
      {query.error && <ErrorNote>Could not read samples: {query.error}</ErrorNote>}
      {report && !report.has_samples && (
        <Empty>This log was written without samples, so there is nothing to drill into.</Empty>
      )}
      {report?.has_samples && rows.length === 0 && (
        <Empty>{onlyFailures ? "No failures in this log." : "No samples."}</Empty>
      )}

      {rows.length > 0 && (
        <div className="hx-samples-grid">
          <table className="data">
            <thead>
              <tr>
                <th>#</th>
                <th className="num">Score</th>
                <th>Detail</th>
                <th className="num">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((sample) => {
                const key = `${sample.id}-${sample.epoch ?? 0}`;
                const open = expanded === key;
                return (
                  <SampleRowView
                    key={key}
                    sample={sample}
                    open={open}
                    onToggle={() => setExpanded(open ? null : key)}
                  />
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {report && report.filtered_total > 0 && (
        <div className="hx-pager">
          <span className="small muted hx-pager-range">
            {rangeStart}–{rangeEnd} of {report.filtered_total}
            {onlyFailures ? " failures" : " samples"}
          </span>
          <div className="hx-pager-group" role="group" aria-label="Sample pages">
            <button
              className="btn btn-sm hx-page-btn"
              onClick={() => setOffset(Math.max(0, offset - PAGE))}
              disabled={offset === 0 || query.loading}
            >
              Previous
            </button>
            <span className="hx-page-index">
              {page} / {pageCount}
            </span>
            <button
              className="btn btn-sm hx-page-btn"
              onClick={() => setOffset(offset + PAGE)}
              disabled={offset + PAGE >= report.filtered_total || query.loading}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
