import { useMemo, useState } from "react";
import { api } from "../lib/api";
import { fmtInt, fmtNum, scoreTint } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { configSummary } from "../lib/meta";
import { Empty, ErrorNote, Panel, Spinner } from "../components/Ui";
import type { Group, Regression } from "../types";

function signed(value: number): string {
  return `${value > 0 ? "+" : ""}${fmtNum(value)}`;
}

type DeltaTone = "ns" | "up" | "down" | "na";

/** Presentation only: the tone is read straight off the stored regression. */
function deltaTone(reg: Regression | null): DeltaTone {
  if (!reg || reg.within_noise === null) return "na";
  if (reg.within_noise) return "ns";
  return reg.delta > 0 ? "up" : "down";
}

function deltaTag(reg: Regression): string {
  if (reg.within_noise === true) return "ns";
  if (reg.within_noise === null) return "?";
  return reg.delta > 0 ? "↑" : "↓";
}

function noiseLabel(reg: Regression): string {
  if (reg.within_noise === true) return "within 95% sampling noise";
  if (reg.within_noise === false) return "outside 95% sampling noise";
  return "interval unavailable, difference unresolved";
}

function cellTitle(cell: Group, reg: Regression | null, isBaseline: boolean): string {
  const parts = [`${fmtNum(cell.score)}${cell.stderr != null ? ` ±${fmtNum(1.96 * cell.stderr)}` : ""}`];
  if (cell.samples) parts.push(`${cell.samples} samples`);
  if (cell.k > 1) parts.push(`${cell.k} runs pooled`);
  if (!isBaseline) {
    parts.push(
      reg
        ? `Δ vs baseline ${signed(reg.delta)} (${noiseLabel(reg)})`
        : "Δ n/a (no baseline run for this task)",
    );
  }
  return parts.join(" · ");
}

export function Variants() {
  const [baseline, setBaseline] = useState<string | null>(null);
  const [familyIdx, setFamilyIdx] = useState(0);
  const query = useAsync(() => api.variants({ baseline }), [baseline]);
  const families = useMemo(() => query.data?.families ?? [], [query.data]);
  const family = families[Math.min(familyIdx, Math.max(families.length - 1, 0))];
  // Read the reference from the loaded payload, not the request state: during a
  // refetch the rendered table is still the previous payload's.
  const activeBaseline = family?.baseline ?? "";

  if (query.error) return <ErrorNote>Failed to load variants: {query.error}</ErrorNote>;
  if (query.loading && !query.data) return <Spinner />;
  if (!families.length) {
    return (
      <Panel>
        <Empty>
          No variants yet. Add a <span className="mono">base_model</span> to model entries in
          config.yaml to group them, then run an eval.
        </Empty>
      </Panel>
    );
  }

  return (
    <div className="stack">
      {families.length > 1 && (
        <div className="panel vr-family-bar">
          <div className="chips">
            {families.map((fam, index) => (
              <button
                key={fam.base_model}
                className={"chip vr-family-chip" + (index === familyIdx ? " on" : "")}
                onClick={() => {
                  setFamilyIdx(index);
                  setBaseline(null);
                }}
              >
                {fam.base_model}
                <span className="faint"> · {fam.variants.length}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <Panel
        title={family?.base_model ?? "Variant matrix"}
        hint={family ? `${family.variants.length} variant(s) · ${family.tasks.length} task(s)` : undefined}
        noBody
        actions={
          family && family.variants.length > 1 ? (
            <div className="field vr-baseline-field">
              <span className="field-label">Baseline</span>
              <select
                className="select vr-baseline-select"
                value={activeBaseline}
                onChange={(event) => setBaseline(event.target.value)}
              >
                {family.variants.map((variant) => (
                  <option key={variant.model} value={variant.model}>
                    {variant.model}
                  </option>
                ))}
              </select>
            </div>
          ) : undefined
        }
      >
        {!family || family.tasks.length === 0 ? (
          <Empty>These variants have no scored runs yet.</Empty>
        ) : (
          <div className="matrix-wrap vr-wrap">
            <table className="matrix vr-matrix">
              <thead>
                <tr>
                  <th className="row-head">Variant</th>
                  {family.tasks.map((task) => (
                    <th key={task} className="vr-col-head">
                      {task}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {family.variants.map((variant) => {
                  const config = configSummary({ declared: variant.config });
                  return (
                    <tr
                      key={variant.model}
                      className={variant.is_baseline ? "vr-row--baseline" : undefined}
                    >
                      <th className="row-head" scope="row">
                        <span className="vr-row-id" title={variant.model}>
                          {variant.model}
                        </span>
                        <span className="vr-row-meta">
                          {variant.is_baseline && <span className="badge vr-baseline-badge">baseline</span>}
                          {config && <span className="vr-row-config">{config}</span>}
                        </span>
                      </th>
                      {family.tasks.map((task) => {
                        const cell = family.cells[variant.model]?.[task] ?? null;
                        if (!cell) {
                          return (
                            <td key={task}>
                              <span className="cell empty vr-cell">—</span>
                            </td>
                          );
                        }
                        const reg = family.regressions[variant.model]?.[task] ?? null;
                        const ci =
                          cell.ci_low != null && cell.ci_high != null
                            ? `${fmtNum(cell.ci_low)}–${fmtNum(cell.ci_high)}`
                            : null;
                        const stats = [
                          cell.stderr != null ? `±${fmtNum(1.96 * cell.stderr)}` : null,
                          cell.stderr != null ? `se ${fmtNum(cell.stderr, 3)}` : null,
                        ]
                          .filter(Boolean)
                          .join(" · ");
                        const counts = [
                          cell.samples != null ? `n=${fmtInt(cell.samples)}` : null,
                          cell.k > 1 ? `k=${cell.k}` : null,
                        ]
                          .filter(Boolean)
                          .join(" · ");
                        const tint = scoreTint(cell.score);
                        const tone = deltaTone(reg);
                        return (
                          <td key={task}>
                            <span
                              className="cell vr-cell"
                              style={tint ? { backgroundColor: tint } : undefined}
                              title={cellTitle(cell, reg, variant.is_baseline)}
                            >
                              <span className="vr-cell-score">{fmtNum(cell.score)}</span>
                              {ci && <span className="cell-sub">CI {ci}</span>}
                              {stats && <span className="cell-sub">{stats}</span>}
                              {counts && <span className="cell-sub">{counts}</span>}
                              {!variant.is_baseline &&
                                (reg ? (
                                  <span className={`vr-delta vr-delta--${tone}`}>
                                    <span className="vr-delta-value">Δ {signed(reg.delta)}</span>
                                    <span className="vr-delta-tag">{deltaTag(reg)}</span>
                                  </span>
                                ) : (
                                  <span className="vr-delta vr-delta--na">
                                    <span className="vr-delta-value">Δ n/a</span>
                                  </span>
                                ))}
                            </span>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <div className="panel vr-legend">
        <div className="small muted vr-legend-text">
          Δ is the difference of pooled means against the baseline variant for the same task.{" "}
          <span className="vr-legend-ns">Amber</span> / <span className="mono">ns</span>{" "}
          = within 95% sampling noise, <span className="vr-legend-better">green</span> =
          better than baseline outside noise,{" "}
          <span className="vr-legend-worse">red</span> = worse, grey /{" "}
          <span className="mono">?</span> = interval unavailable. Each cell uses the
          best-supported group for that variant and task; declare one model entry per variant and
          group them with <span className="mono">base_model</span>.
        </div>
      </div>
    </div>
  );
}
