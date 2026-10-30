import { useState } from "react";
import { api } from "../lib/api";
import { usePolling } from "../lib/hooks";
import { Empty, Panel } from "./Ui";
import type { ModelInfo } from "../types";

const LEVELS = [1, 2, 4, 8];

export function SpeedProbe({ models }: { models: ModelInfo[] }) {
  const [sizes, setSizes] = useState("2000,16000,64000");
  const [levels, setLevels] = useState<number[]>([1]);
  const [iterations, setIterations] = useState(1);
  const [message, setMessage] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  usePolling(api.speedStatus, true, 3000, (status) => {
    setRunning(status.running);
    if (status.error) {
      setMessage(`Probe failed: ${status.error}`);
    } else if (!status.running) {
      setMessage((prev) => (prev === "Probe started…" ? "Probe finished." : prev));
    }
  });

  const start = async () => {
    setMessage(null);
    const parsed = sizes
      .split(",")
      .map((value) => Number(value.trim()))
      .filter((value) => Number.isFinite(value) && value > 0);
    if (!parsed.length) {
      setMessage("Enter at least one positive context size.");
      return;
    }
    if (!levels.length) {
      setMessage("Select at least one concurrency level.");
      return;
    }
    try {
      await api.speedRun({
        context_sizes: parsed,
        concurrency: levels,
        iterations,
      });
      setRunning(true);
      setMessage("Probe started…");
    } catch (err) {
      setMessage(`Probe failed to start: ${(err as Error).message}`);
    }
  };

  const hasKey = models.some((model) => model.has_key);

  return (
    <Panel title="Speed probe" hint="streaming, OpenAI-compatible endpoint · serial batches by default">
      <div className="row" style={{ gap: 12, alignItems: "flex-end" }}>
        <div className="field" style={{ flex: 1, minWidth: 220 }}>
          <span className="field-label">Context sizes (tokens, comma-separated)</span>
          <input
            className="input"
            value={sizes}
            onChange={(event) => setSizes(event.target.value)}
            disabled={running}
          />
        </div>
        <div className="field">
          <span className="field-label">Parallel requests</span>
          <div className="chips">
            {LEVELS.map((level) => (
              <button
                key={level}
                className={"chip" + (levels.includes(level) ? " on" : "")}
                onClick={() =>
                  setLevels((prev) =>
                    prev.includes(level)
                      ? prev.filter((value) => value !== level)
                      : [...prev, level].sort((a, b) => a - b),
                  )
                }
                disabled={running}
              >
                {level}
              </button>
            ))}
          </div>
        </div>
        <div className="field" style={{ width: 96 }}>
          <span className="field-label">Iterations</span>
          <input
            className="input"
            type="number"
            min={1}
            max={20}
            value={iterations}
            onChange={(event) =>
              setIterations(Math.min(20, Math.max(1, Number(event.target.value) || 1)))
            }
            disabled={running}
            title="Repeat each batch back-to-back to expose drift under sustained load"
          />
        </div>
        <button className="btn" onClick={start} disabled={running}>
          {running ? "Probing…" : "Run speed probe"}
        </button>
      </div>
      {message && (
        <div className="small muted" style={{ marginTop: 10 }}>
          {message}
        </div>
      )}
      {models.length > 0 && !hasKey && (
        <div className="small muted" style={{ marginTop: 8 }}>
          Warning: no configured model has an API key file present.
        </div>
      )}
      {!message && !running && (
        <Empty>
          Each batch records TTFT p50/p95, per-request rates, and aggregate tokens/sec.
          Iterations above 1 share a batch id so the Overview can plot drift.
        </Empty>
      )}
    </Panel>
  );
}
