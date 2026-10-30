import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { shortDate } from "../lib/format";
import { useAsync, usePolling } from "../lib/hooks";
import { ErrorNote, Kpi, Panel, Spinner } from "../components/Ui";
import { ResultRow, TestDefinitions } from "../components/PromptParts";
import type { PromptStatus } from "../types";

export function Prompts() {
  const modelsQ = useAsync(api.models, []);
  const defsQ = useAsync(api.prompts, []);
  const resultsQ = useAsync(() => api.promptResults({ limit: 5 }), []);
  const [status, setStatus] = useState<PromptStatus | null>(null);
  const [model, setModel] = useState("");
  const [repeats, setRepeats] = useState(1);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  usePolling(api.promptStatus, true, 2000, (value) => setStatus(value));

  const models = modelsQ.data ?? [];
  useEffect(() => {
    if (models.length) setModel((prev) => prev || models[0].name);
  }, [models]);

  const running = !!status?.running;
  const runState = status?.state;
  const reloadResults = resultsQ.reload;
  useEffect(() => {
    if (runState === "done" || runState === "cancelled" || runState === "failed") {
      reloadResults();
    }
  }, [runState, status?.run_id, reloadResults]);

  const latest = resultsQ.data?.runs?.[0] ?? null;
  const tests = defsQ.data?.tests ?? [];

  const start = async () => {
    setError(null);
    setMessage(null);
    try {
      await api.promptRun({ model, repeats });
      setMessage("Prompt run started.");
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const cancel = async () => {
    try {
      const result = await api.promptCancel();
      setMessage(result.cancelled ? "Cancelling after the current test…" : "No prompt run to cancel.");
    } catch (err) {
      setError((err as Error).message);
    }
  };

  if (defsQ.error) return <ErrorNote>Failed to load prompt tests: {defsQ.error}</ErrorNote>;
  if (defsQ.loading && !defsQ.data) return <Spinner />;

  const passRate = latest && latest.tests ? latest.passed / latest.tests : null;

  return (
    <div className="stack">
      <Panel title="Run prompt tests" hint="one request per test, sequential">
        {tests.length === 0 ? (
          <div className="small muted">
            No tests defined. Add entries to <span className="mono">prompts.yaml</span> and
            reload.
          </div>
        ) : (
          <>
            <div className="row" style={{ gap: 12, alignItems: "flex-end" }}>
              <div className="field" style={{ minWidth: 220 }}>
                <span className="field-label">Model</span>
                <select
                  className="select"
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                  disabled={running}
                >
                  {models.map((entry) => (
                    <option key={entry.name} value={entry.name}>
                      {entry.name}
                      {entry.has_key ? "" : " (no key)"}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field" style={{ width: 110 }}>
                <span className="field-label">Repeats</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={10}
                  value={repeats}
                  onChange={(event) =>
                    setRepeats(Math.min(10, Math.max(1, Number(event.target.value) || 1)))
                  }
                  disabled={running}
                />
              </div>
              <button className="btn btn-primary" onClick={start} disabled={running || !model}>
                {running ? "Running…" : "Run prompts"}
              </button>
              <button className="btn btn-danger" onClick={cancel} disabled={!running}>
                Cancel
              </button>
            </div>

            <div className="small muted" style={{ marginTop: 10 }}>
              {running
                ? `Running ${status.done}/${status.total}${status.current ? ` · ${status.current}` : ""}`
                : runState === "done"
                  ? `Finished: ${status?.passed ?? 0} passed, ${status?.failed ?? 0} failed.`
                  : runState === "cancelled"
                    ? "Run cancelled."
                    : "Each test sends one chat completion and applies its checker."}
            </div>
            {message && <div className="small" style={{ color: "var(--success)" }}>{message}</div>}
            {error && <ErrorNote>{error}</ErrorNote>}
            {status?.error && <ErrorNote>{status.error}</ErrorNote>}
          </>
        )}
      </Panel>

      {resultsQ.error && <ErrorNote>Failed to load results: {resultsQ.error}</ErrorNote>}

      {latest ? (
        <>
          <div className="kpi-row">
            <Kpi
              label="Pass rate"
              value={passRate == null ? "—" : `${Math.round(passRate * 100)}%`}
              sub={`${latest.passed}/${latest.tests} checks`}
            />
            <Kpi label="Tests" value={latest.tests} sub={`${latest.repeats} repeat(s)`} />
            <Kpi label="Model" value={latest.model} />
            <Kpi label="Run" value={shortDate(latest.ts)} sub={latest.run_id} />
            <Kpi label="Errors" value={latest.errors} sub="HTTP / parsing failures" />
          </div>

          <Panel title="Latest results" hint={`${latest.model} · ${shortDate(latest.ts)}`} noBody>
            <div className="table-wrap" style={{ padding: "4px 8px 8px" }}>
              <table className="data">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Test</th>
                    <th>Result</th>
                    <th className="num">Latency</th>
                    <th>Detail</th>
                    <th className="num">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {latest.results.map((row) => (
                    <ResultRow key={`${row.test_id}-${row.repeat}`} row={row} />
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      ) : (
        <Panel>
          <div className="small muted">
            No prompt results yet. Run the tests above; results are stored like eval runs.
          </div>
        </Panel>
      )}

      {tests.length > 0 && <TestDefinitions tests={tests} />}
    </div>
  );
}
