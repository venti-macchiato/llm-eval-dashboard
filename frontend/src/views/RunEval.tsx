import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAsync, usePolling } from "../lib/hooks";
import { configSummary } from "../lib/meta";
import { ErrorNote, Panel } from "../components/Ui";
import { JobProgress } from "../components/JobProgress";
import { SpeedProbe } from "../components/SpeedProbe";
import { TaskPicker } from "../components/TaskPicker";
import { SuiteSummary } from "../components/SuiteSummary";
import type { EvalJob, TaskSpec } from "../types";

function isJob(value: unknown): value is EvalJob {
  return !!value && typeof value === "object" && "state" in (value as Record<string, unknown>);
}

export function RunEval() {
  const modelsQ = useAsync(api.models, []);
  const suitesQ = useAsync(api.suites, []);
  const benchmarksQ = useAsync(api.benchmarks, []);
  const catalogQ = useAsync(api.catalog, []);
  const [preflightNonce, setPreflightNonce] = useState(0);
  const preflightQ = useAsync(() => api.preflight(preflightNonce > 0), [preflightNonce]);
  const [job, setJob] = useState<EvalJob | null>(null);

  const [mode, setMode] = useState<"suite" | "custom">("suite");
  const [model, setModel] = useState("");
  const [suite, setSuite] = useState("");
  const [custom, setCustom] = useState<TaskSpec[]>([]);
  const [limit, setLimit] = useState(20);
  const [repeats, setRepeats] = useState(1);
  const [epochs, setEpochs] = useState(1);
  const [advanced, setAdvanced] = useState(false);
  const [override, setOverride] = useState({ base_url: "", model_id: "", api_key_file: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  usePolling(api.evalStatus, true, 2000, (status) => setJob(isJob(status) ? status : null));

  useEffect(() => {
    if (!modelsQ.data?.length) return;
    setModel((prev) => prev || modelsQ.data![0].name);
  }, [modelsQ.data]);

  useEffect(() => {
    const names = suitesQ.data ? Object.keys(suitesQ.data) : [];
    if (!names.length) return;
    setSuite((prev) => prev || names[0]);
  }, [suitesQ.data]);

  const running = job?.state === "running";

  const addTask = (task: string) => {
    setCustom((prev) => (prev.some((t) => t.task === task) ? prev : [...prev, { task, limit }]));
  };
  const removeTask = (task: string) =>
    setCustom((prev) => prev.filter((t) => t.task !== task));
  const setTaskLimit = (task: string, value: number) =>
    setCustom((prev) => prev.map((t) => (t.task === task ? { ...t, limit: value } : t)));

  const start = async () => {
    setError(null);
    setNotice(null);
    if (mode === "custom" && custom.length === 0) {
      setError("Add at least one task.");
      return;
    }
    setBusy(true);
    try {
      const body: Record<string, unknown> = { model, repeats, epochs };
      if (mode === "suite") body.suite = suite;
      else body.tasks = custom;
      const ov = {
        base_url: override.base_url.trim(),
        model_id: override.model_id.trim(),
        api_key_file: override.api_key_file.trim(),
      };
      if (advanced && (ov.base_url || ov.model_id || ov.api_key_file)) {
        body.model_override = ov;
      }
      await api.runEval(body);
      setNotice("Eval started.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    try {
      const result = await api.cancelEval();
      setNotice(result.cancelled ? "Cancelled." : "No running job to cancel.");
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const models = modelsQ.data ?? [];
  const suites = suitesQ.data ? Object.keys(suitesQ.data) : [];
  const selectedModel = models.find((m) => m.name === model);
  const selectedConfig = selectedModel?.hardware
    ? configSummary({ declared: selectedModel.hardware })
    : "";

  const preflight = preflightQ.data;
  const normalize = (task: string) => task.replace(/^inspect_evals\//, "").toLowerCase();
  const tasksForRun =
    mode === "suite"
      ? (suitesQ.data?.[suite] ?? []).map((item) => item.task)
      : custom.map((item) => item.task);
  const blocked = preflight
    ? [
        ...new Set(
          tasksForRun.filter((task) =>
            (preflight.requirements[normalize(task)] ?? []).some(
              (req) => !preflight.capabilities[req]?.available,
            ),
          ),
        ),
      ]
    : [];

  return (
    <div className="stack">
      <Panel title="Run eval" hint="one job at a time">
        {modelsQ.error && <ErrorNote>Failed to load models: {modelsQ.error}</ErrorNote>}
        <div className="wb-bar">
          <div className="wb-bar-cell wb-bar-model">
            <span className="wb-bar-label">
              <span className="field-label">Model</span>
              <span className="wb-bar-note" title={selectedConfig || undefined}>
                {selectedConfig || "no hardware declared"}
              </span>
            </span>
            <select className="select" value={model} onChange={(e) => setModel(e.target.value)} disabled={running}>
              {models.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name}{m.has_key ? "" : " (no key)"}
                </option>
              ))}
            </select>
          </div>

          <div className="wb-bar-cell wb-bar-source">
            <span className="wb-bar-label">
              <span className="field-label">Source</span>
            </span>
            <div className="wb-seg">
              <button type="button" className={"wb-seg-btn" + (mode === "suite" ? " on" : "")} onClick={() => setMode("suite")} disabled={running}>Suite</button>
              <button type="button" className={"wb-seg-btn" + (mode === "custom" ? " on" : "")} onClick={() => setMode("custom")} disabled={running}>Custom tasks</button>
            </div>
          </div>

          {mode === "suite" && (
            <div className="wb-bar-cell wb-bar-suite">
              <span className="wb-bar-label">
                <span className="field-label">Suite</span>
              </span>
              <select className="select" value={suite} onChange={(e) => setSuite(e.target.value)} disabled={running}>
                {suites.map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
            </div>
          )}

          <div className="wb-bar-cell wb-bar-num">
            <span className="wb-bar-label">
              <span className="field-label">Repeats</span>
            </span>
            <input
              className="input"
              type="number"
              min={1}
              max={20}
              value={repeats}
              onChange={(e) => setRepeats(Math.min(20, Math.max(1, Number(e.target.value) || 1)))}
              disabled={running}
              title="Run each task this many times as separate evals; results are pooled into a mean ± 95% CI"
            />
          </div>
          <div className="wb-bar-cell wb-bar-num">
            <span className="wb-bar-label">
              <span className="field-label">Epochs</span>
            </span>
            <input
              className="input"
              type="number"
              min={1}
              max={20}
              value={epochs}
              onChange={(e) => setEpochs(Math.min(20, Math.max(1, Number(e.target.value) || 1)))}
              disabled={running}
              title="inspect --epochs: repeats within a single eval log"
            />
          </div>

          <div className="wb-bar-actions">
            <button
              className="btn btn-primary wb-run"
              onClick={start}
              disabled={busy || running || blocked.length > 0}
            >
              {running ? "Running…" : "Start eval"}
            </button>
            <button className="btn btn-danger" onClick={cancel} disabled={!running}>Cancel</button>
          </div>
        </div>

        {mode === "suite" && !!benchmarksQ.data?.suites[suite]?.description && (
          <p className="wb-bar-caption">{benchmarksQ.data?.suites[suite]?.description}</p>
        )}

        {mode === "suite" && (
          <SuiteSummary
            tasks={suitesQ.data?.[suite]}
            benchmarks={benchmarksQ.data?.benchmarks}
            requirements={preflight?.requirements}
            capabilities={preflight?.capabilities}
          />
        )}

        {mode === "custom" && (
          <div className="wb-custom">
            <div className="wb-custom-head">
              <div className="wb-bar-cell wb-bar-num">
                <span className="wb-bar-label">
                  <span className="field-label">Default limit</span>
                </span>
                <input className="input" type="number" min={1} value={limit} onChange={(e) => setLimit(Math.max(1, Number(e.target.value) || 1))} disabled={running} />
              </div>
              <span className="small muted wb-custom-hint">Click a task to add it; edit its limit in the table below.</span>
            </div>
            <TaskPicker
              catalog={catalogQ.data}
              benchmarks={benchmarksQ.data?.benchmarks}
              categories={benchmarksQ.data?.categories}
              chosen={custom.map((t) => t.task)}
              onAdd={addTask}
              disabled={running}
              requirements={preflight?.requirements}
              capabilities={preflight?.capabilities}
            />
            {custom.length > 0 && (
              <div className="table-wrap wb-selected">
                <table className="data">
                  <thead>
                    <tr><th>Task</th><th className="num">Limit</th><th /></tr>
                  </thead>
                  <tbody>
                    {custom.map((t) => (
                      <tr key={t.task}>
                        <td className="mono">{t.task}</td>
                        <td className="num">
                          <input className="input" style={{ width: 80 }} type="number" min={1} value={t.limit} onChange={(e) => setTaskLimit(t.task, Math.max(1, Number(e.target.value) || 1))} disabled={running} />
                        </td>
                        <td className="num">
                          <button className="btn btn-ghost btn-sm" onClick={() => removeTask(t.task)} disabled={running}>Remove</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        <details className="wb-advanced" onToggle={(e) => setAdvanced((e.target as HTMLDetailsElement).open)}>
          <summary className="small muted">Endpoint override (optional)</summary>
          <div className="wb-advanced-grid">
            <div className="wb-bar-cell">
              <span className="field-label">Base URL</span>
              <input className="input" value={override.base_url} onChange={(e) => setOverride({ ...override, base_url: e.target.value })} placeholder="http://host:port/v1" disabled={running} />
            </div>
            <div className="wb-bar-cell">
              <span className="field-label">Model id</span>
              <input className="input" value={override.model_id} onChange={(e) => setOverride({ ...override, model_id: e.target.value })} placeholder="served model name" disabled={running} />
            </div>
            <div className="wb-bar-cell">
              <span className="field-label">API key file</span>
              <input className="input" value={override.api_key_file} onChange={(e) => setOverride({ ...override, api_key_file: e.target.value })} placeholder="~/config/.strata/key" disabled={running} />
            </div>
          </div>
        </details>

        {blocked.length > 0 && (
          <div className="wb-alert">
            <span className="wb-alert-mark" />
            <span className="small wb-alert-body">
              Needs Docker, which is not available
              {preflight?.capabilities.docker?.detail
                ? ` (${preflight.capabilities.docker.detail})`
                : ""}
              : {blocked.join(", ")}. Start Docker, then recheck.{" "}
            </span>
            <button
              className="btn btn-sm wb-alert-action"
              onClick={() => setPreflightNonce((nonce) => nonce + 1)}
            >
              Recheck
            </button>
          </div>
        )}
        {error && <ErrorNote>{error}</ErrorNote>}
        {notice && <div className="small wb-notice">{notice}</div>}
      </Panel>

      {job && <JobProgress job={job} />}
      <SpeedProbe models={models} />
    </div>
  );
}
