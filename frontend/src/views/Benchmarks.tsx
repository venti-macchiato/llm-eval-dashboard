import { useMemo, useState } from "react";
import { api } from "../lib/api";
import { useAsync } from "../lib/hooks";
import { Empty, ErrorNote, Panel, Spinner } from "../components/Ui";
import type { BenchmarkEntry } from "../types";

type Entry = BenchmarkEntry & { task: string };

export function Benchmarks() {
  const dataQ = useAsync(api.benchmarks, []);
  const suitesQ = useAsync(api.suites, []);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");

  const suitesFor = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const [name, tasks] of Object.entries(suitesQ.data ?? {})) {
      for (const item of tasks) {
        const task = item.task.replace(/^inspect_evals\//, "");
        map.set(task, [...(map.get(task) ?? []), name]);
      }
    }
    return map;
  }, [suitesQ.data]);

  const entries = useMemo<Entry[]>(() => {
    if (!dataQ.data) return [];
    return Object.entries(dataQ.data.benchmarks).map(([task, entry]) => ({ task, ...entry }));
  }, [dataQ.data]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return entries.filter((entry) => {
      if (category !== "all" && entry.category !== category) return false;
      if (!needle) return true;
      return `${entry.task} ${entry.title} ${entry.measures}`.toLowerCase().includes(needle);
    });
  }, [entries, query, category]);

  // A user may add a category id that benchmarks.yaml does not declare; show
  // it rather than silently dropping the benchmark.
  const allCategories = useMemo(() => {
    const declared = dataQ.data?.categories ?? [];
    const known = new Set(declared.map((cat) => cat.id));
    // Derive extras from all entries, not the search result, so an undeclared
    // category's chip does not vanish while searching.
    const extra = [...new Set(entries.map((entry) => entry.category))]
      .filter((id) => !known.has(id))
      .map((id) => ({ id, label: id, description: "" }));
    return [...declared, ...extra];
  }, [dataQ.data, entries]);

  if (dataQ.error) return <ErrorNote>Failed to load benchmarks: {dataQ.error}</ErrorNote>;
  if (dataQ.loading && !dataQ.data) return <Spinner />;
  if (!dataQ.data) return null;

  const categories = allCategories;

  return (
    <div className="stack">
      <Panel title="How to read these scores">
        <p className="muted">
          Each benchmark measures a different capability, so scores are only comparable within the
          same task and sample count. Chance level differs per task (four options = 25%, yes/no =
          50%). Small sample limits are noisy — check the standard error shown on the Leaderboard
          and Runs pages before treating a difference as real.
        </p>
        <p className="muted" style={{ marginTop: 8 }}>
          Suites are starting points; compose your own in the Run eval tab. Code and agent
          benchmarks execute tools or generated programs and may need a sandbox.
        </p>
      </Panel>

      <div className="panel" style={{ padding: 16 }}>
        <div className="row" style={{ gap: 16, alignItems: "flex-end" }}>
          <div className="field" style={{ flex: 1, minWidth: 240 }}>
            <span className="field-label">Search</span>
            <input
              className="input"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="mmlu, math, long context…"
            />
          </div>
        </div>
        <div className="chips" style={{ marginTop: 12 }}>
          <button
            className={"chip" + (category === "all" ? " on" : "")}
            onClick={() => setCategory("all")}
          >
            All ({entries.length})
          </button>
          {categories.map((cat) => {
            const count = entries.filter((entry) => entry.category === cat.id).length;
            if (!count) return null;
            return (
              <button
                key={cat.id}
                className={"chip" + (category === cat.id ? " on" : "")}
                onClick={() => setCategory(cat.id)}
              >
                {cat.label} ({count})
              </button>
            );
          })}
        </div>
      </div>

      {categories.map((cat) => {
        const items = filtered.filter((entry) => entry.category === cat.id);
        if (!items.length) return null;
        return (
          <details className="panel bench-section" key={cat.id} id={`bench-${cat.id}`} open>
            <summary>
              <span className="bench-summary-title">{cat.label}</span>
              <span className="muted small">{items.length} task(s)</span>
              {cat.description && (
                <span className="muted small bench-summary-desc">{cat.description}</span>
              )}
            </summary>
            <div className="grid grid-auto" style={{ marginTop: 12 }}>
              {items.map((entry) => {
                const used = suitesFor.get(entry.task) ?? [];
                return (
                  <article className="panel bench-card" key={entry.task}>
                    <div className="row" style={{ justifyContent: "space-between", gap: 8 }}>
                      <h3>{entry.title}</h3>
                      <span className="mono faint small">{entry.task}</span>
                    </div>
                    <p className="bench-measures">{entry.measures}</p>
                    {entry.read && <p className="bench-read">{entry.read}</p>}
                    {used.length > 0 && (
                      <div className="chips" style={{ marginTop: 10 }}>
                        {used.map((name) => (
                          <span key={name} className="badge">{name}</span>
                        ))}
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          </details>
        );
      })}

      {filtered.length === 0 && (
        <Panel><Empty>No benchmarks match that search.</Empty></Panel>
      )}
    </div>
  );
}
