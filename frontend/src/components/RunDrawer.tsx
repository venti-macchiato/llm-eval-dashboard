import { useMemo } from "react";
import { fmtInt, fmtNum, shortDate } from "../lib/format";
import { hardwareOf, parseMeta } from "../lib/meta";
import { Drawer } from "./Drawer";
import { HardwareBlock } from "./HardwareBlock";
import { SampleList } from "./SampleList";
import type { Run } from "../types";

function MetaValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <>—</>;
  if (typeof value === "object") {
    return <span className="mono small">{JSON.stringify(value)}</span>;
  }
  return <>{String(value)}</>;
}

export function RunDrawer({ run, onClose }: { run: Run; onClose: () => void }) {
  const meta = useMemo(() => parseMeta(run), [run]);
  const hardware = useMemo(() => hardwareOf(run), [run]);

  return (
    <Drawer
      title={run.task}
      subtitle={`${run.model} · ${shortDate(run.created)}`}
      onClose={onClose}
    >
      <dl className="kv">
        <dt>Score</dt>
        <dd>
          {fmtNum(run.score)}
          {run.stderr != null && (
            <span className="muted"> ± {fmtNum(run.stderr, 4)}</span>
          )}
        </dd>
        <dt>Samples</dt>
        <dd>
          {fmtInt(run.samples)}
          {run.error_samples ? (
            <span style={{ color: "var(--error)" }}> · {run.error_samples} errored</span>
          ) : null}
        </dd>
        <dt>Tokens in / out</dt>
        <dd>{fmtInt(run.input_tokens)} / {fmtInt(run.output_tokens)}</dd>
        <dt>Duration</dt>
        <dd>{run.duration_s === null ? "—" : `${fmtNum(run.duration_s, 1)}s`}</dd>
        <dt>Eval id</dt>
        <dd className="mono small" style={{ wordBreak: "break-all" }}>{run.eval_id}</dd>
        <dt>Log</dt>
        <dd className="mono small" style={{ wordBreak: "break-all" }}>{run.log_path ?? "—"}</dd>
      </dl>

      {meta && (
        <div>
          <h3 style={{ marginBottom: 8 }}>Run provenance</h3>
          <dl className="kv">
            {["inspect_model", "base_url", "model_id", "dataset", "epochs", "git_commit", "generate_config", "packages"].map(
              (key) =>
                key in meta ? (
                  <div key={key} style={{ display: "contents" }}>
                    <dt>{key.replace("_", " ")}</dt>
                    <dd><MetaValue value={meta[key]} /></dd>
                  </div>
                ) : null,
            )}
          </dl>
        </div>
      )}

      <div>
        <h3 style={{ marginBottom: 8 }}>Hardware</h3>
        <HardwareBlock hardware={hardware} />
      </div>

      <SampleList run={run} />
    </Drawer>
  );
}
