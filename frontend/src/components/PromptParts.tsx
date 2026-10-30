import { useMemo, useState } from "react";
import { fmtInt, fmtNum } from "../lib/format";
import { Panel } from "./Ui";
import type { PromptResult, PromptTest } from "../types";

/**
 * Presentation-only health thresholds for the latency column, expressed as
 * end-to-end throughput (output tokens / wall-clock latency, prefill and TTFT
 * included). Nothing here feeds back into scoring or stored metrics.
 */
const HEALTHY_TPS = 15;
const BOTTLENECK_TPS = 6;

interface LatencySignal {
  className: string;
  title: string | undefined;
}

function latencySignal(row: PromptResult): LatencySignal {
  if (row.error) return { className: "num latency is-bad", title: "request failed" };
  if (row.latency_s == null) return { className: "num latency is-na", title: undefined };

  const outTokens = row.output_tokens ?? 0;
  if (!(row.latency_s > 0) || outTokens <= 0) {
    return { className: "num latency", title: `${fmtNum(row.latency_s, 2)}s wall clock` };
  }

  const tps = outTokens / row.latency_s;
  const measured = `${fmtNum(tps, 2)} tok/s end-to-end (${fmtInt(outTokens)} out / ${fmtNum(
    row.latency_s,
    2,
  )}s, prefill included)`;

  if (tps < BOTTLENECK_TPS) {
    return { className: "num latency is-bad", title: `${measured} — below ${BOTTLENECK_TPS} tok/s, bottleneck` };
  }
  if (tps < HEALTHY_TPS) {
    return { className: "num latency is-warn", title: `${measured} — under ${HEALTHY_TPS} tok/s healthy floor` };
  }
  return { className: "num latency", title: measured };
}

export function ResultBadge({ passed }: { passed: boolean }) {
  return <span className={"badge " + (passed ? "ok" : "err")}>{passed ? "pass" : "fail"}</span>;
}

export function ResultRow({ row }: { row: PromptResult }) {
  const [open, setOpen] = useState(false);
  const signal = latencySignal(row);

  return (
    <>
      <tr>
        <td className="cell-cat">{row.category}</td>
        <td className="cell-test">
          <span className="result-title" title={row.title}>
            {row.title}
          </span>
          {row.repeat > 1 && <span className="repeat-tag">#{row.repeat}</span>}
        </td>
        <td>
          <ResultBadge passed={!!row.passed} />
        </td>
        <td className={signal.className} title={signal.title}>
          {row.latency_s == null ? "—" : `${fmtNum(row.latency_s, 2)}s`}
        </td>
        <td className="cell-detail">
          <div className={"detail-clamp" + (row.error ? " is-error" : "")} title={row.error ?? row.detail ?? undefined}>
            {row.error ?? row.detail ?? "—"}
          </div>
        </td>
        <td className="num">
          <button
            className="btn btn-sm"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            aria-label={`${open ? "Hide" : "Show"} ${row.title} output`}
          >
            {open ? "Hide" : "Details"}
          </button>
        </td>
      </tr>
      {open && (
        <tr className="expand-row">
          <td colSpan={6}>
            <div className="terminal">
              <div className="terminal-head">
                <span className="terminal-caret" aria-hidden="true">
                  ❯
                </span>
                <span className="terminal-title">{row.test_id}</span>
                <span className="terminal-spacer" />
                <span className="terminal-tag in">
                  in <b>{fmtInt(row.input_tokens)}</b>
                </span>
                <span className="terminal-tag out">
                  out <b>{fmtInt(row.output_tokens)}</b>
                </span>
                <span className="terminal-tag">
                  lat <b>{row.latency_s == null ? "—" : `${fmtNum(row.latency_s, 2)}s`}</b>
                </span>
              </div>
              <div className="terminal-body">
                {row.output && (
                  <div className="term-block">
                    <div className="term-label">assistant completion</div>
                    <pre className="term-pre">{row.output}</pre>
                  </div>
                )}
                {row.error && (
                  <div className="term-block">
                    <div className="term-label">traceback</div>
                    <pre className="term-pre err">{row.error}</pre>
                  </div>
                )}
                {!row.output && !row.error && (
                  <div className="term-empty">— no payload recorded for this test</div>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function TestDefinitions({ tests }: { tests: PromptTest[] }) {
  const byCategory = useMemo(() => {
    const groups = new Map<string, PromptTest[]>();
    for (const test of tests) {
      groups.set(test.category, [...(groups.get(test.category) ?? []), test]);
    }
    return [...groups.entries()];
  }, [tests]);

  return (
    <Panel title="Defined tests" hint={`${tests.length} in prompts.yaml`}>
      <div className="stack" style={{ gap: 14 }}>
        {byCategory.map(([category, items]) => (
          <div key={category}>
            <div className="field-label">{category}</div>
            <div className="stack" style={{ gap: 6, marginTop: 6 }}>
              {items.map((test) => (
                <div key={test.id} className="row" style={{ gap: 10, alignItems: "flex-start" }}>
                  <span className="mono small" style={{ minWidth: 130 }}>{test.id}</span>
                  <span className="small" style={{ whiteSpace: "normal" }}>
                    {test.title}
                    {test.description && <span className="muted"> — {test.description}</span>}
                    <span className="faint"> · check: {test.check.type}</span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}
