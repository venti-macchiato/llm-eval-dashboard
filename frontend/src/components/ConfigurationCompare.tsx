import { HARDWARE_FIELDS, configDiffs, hardwareValue } from "../lib/meta";
import type { HardwareInfo } from "../types";
import { Panel } from "./Ui";

const CONFIG_SNIPPET = `models:
  - name: polystrata-q3
    base_url: http://localhost:8080/v1
    hardware:
      backend: llama.cpp
      quant: Q3_K_XL
      gpu: RTX 4090
      vram_gb: 24
      ctx_size: 32768
      offload: "35/48 layers"`;

/**
 * Declared hardware for two pooled run groups, with a verdict on whether the
 * difference between their scores could come from the setup instead of the
 * model.
 */
export function ConfigurationCompare({
  a,
  b,
  pooled,
}: {
  a: HardwareInfo | null;
  b: HardwareInfo | null;
  pooled: boolean;
}) {
  const rows = HARDWARE_FIELDS.filter(
    (field) => field.key in (a?.declared ?? {}) || field.key in (b?.declared ?? {}),
  ).map((field) => {
    const left = hardwareValue(a?.declared, field.key);
    const right = hardwareValue(b?.declared, field.key);
    return { ...field, left, right, differs: left !== right };
  });
  const diffs = configDiffs(a, b);
  const bothDeclared = !!a?.declared && !!b?.declared;
  const probed = [a?.probe, b?.probe].filter(Boolean);

  return (
    <Panel
      title="Configuration"
      hint="declared in config.yaml"
      actions={
        rows.length ? (
          diffs.length ? (
            <span className="badge warn">
              {diffs.length} field{diffs.length === 1 ? "" : "s"} differ
            </span>
          ) : bothDeclared ? (
            <span className="badge ok">same configuration</span>
          ) : (
            <span className="badge">partial declaration</span>
          )
        ) : undefined
      }
    >
      {rows.length === 0 ? (
        <div className="cx-cfg-empty">
          <div className="cx-cfg-empty-head">
            <span className="cx-cfg-empty-badge" aria-hidden="true">!</span>
            <div className="cx-cfg-empty-copy">
              <div className="cx-cfg-empty-title">No configuration declared for these runs</div>
              <p className="cx-cfg-empty-body">
                No hardware declared for either run. Add a <span className="mono">hardware:</span>{" "}
                block to the model in config.yaml, then ingest to backfill it.
              </p>
            </div>
          </div>
          <pre className="cx-cfg-snippet"><code>{CONFIG_SNIPPET}</code></pre>
          <ol className="cx-cfg-steps">
            <li>
              Add the <span className="mono">hardware:</span> mapping under the model entry in{" "}
              <span className="mono">config.yaml</span>; every field is optional.
            </li>
            <li>
              Ingest again — earlier runs are backfilled and reported as{" "}
              <span className="mono">updated</span>.
            </li>
            <li>Reopen Compare: identical rows stay neutral, diverging rows warn.</li>
          </ol>
        </div>
      ) : (
        <>
          <table className="data cx-cfg-table">
            <thead>
              <tr>
                <th>Field</th>
                <th>A</th>
                <th>B</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className={`cx-cfg-row${row.differs ? " is-diff" : ""}`}>
                  <td className="cx-cfg-label">{row.label}</td>
                  <td className="cx-cfg-val">{row.left}</td>
                  <td className="cx-cfg-val">{row.right}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div
            className={`cx-cfg-verdict ${
              diffs.length ? "is-warn" : bothDeclared ? "is-ok" : "is-idle"
            }`}
          >
            {diffs.length
              ? `Different configuration (${diffs.map((d) => d.label.toLowerCase()).join(", ")}): a score difference may come from the setup, not the model.`
              : bothDeclared
                ? "Same declared configuration."
                : "Configuration is not declared for both runs; treat this comparison as provisional."}
          </div>
          {pooled && (
            <div className="cx-cfg-note">
              Score and CI come from pooled repeats; the ± column is the 95% interval of the
              pooled mean.
            </div>
          )}
          {probed.length > 0 && (
            <div className="cx-cfg-note">
              Local probe recorded for {probed.map((p) => p!.host).join(" and ")} — evidence about
              the dashboard host, not necessarily the server.
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
