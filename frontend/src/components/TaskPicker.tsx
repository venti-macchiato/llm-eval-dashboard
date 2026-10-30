import { useMemo, useState } from "react";
import type { BenchmarkCategory, BenchmarkEntry, CatalogEntry } from "../types";

interface Item {
  task: string;
  title: string;
  measures: string;
}

type Capability = { available: boolean; detail?: string | null };

export function TaskPicker({
  catalog,
  benchmarks,
  categories,
  chosen,
  onAdd,
  disabled,
  requirements,
  capabilities,
}: {
  catalog: CatalogEntry[] | null;
  benchmarks: Record<string, BenchmarkEntry> | undefined;
  categories?: BenchmarkCategory[];
  chosen: string[];
  onAdd: (task: string) => void;
  disabled?: boolean;
  requirements?: Record<string, string[]>;
  capabilities?: Record<string, Capability>;
}) {
  const [query, setQuery] = useState("");

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const picked = new Set(chosen);
    const order = new Map((categories ?? []).map((category, index) => [category.id, index]));
    const items: Item[] = (catalog ?? [])
      .filter((entry) => !picked.has(entry.task))
      .filter((entry) => {
        if (!needle) return true;
        const meta = benchmarks?.[entry.task];
        return `${entry.task} ${meta?.title ?? ""} ${meta?.measures ?? ""}`
          .toLowerCase()
          .includes(needle);
      })
      .map((entry) => ({
        task: entry.task,
        title: benchmarks?.[entry.task]?.title ?? entry.task,
        measures: benchmarks?.[entry.task]?.measures ?? "No curated description yet.",
      }))
      .sort((a, b) => {
        const catA = order.get(benchmarks?.[a.task]?.category ?? "other") ?? 99;
        const catB = order.get(benchmarks?.[b.task]?.category ?? "other") ?? 99;
        return catA === catB ? a.title.localeCompare(b.title) : catA - catB;
      })
      .slice(0, 80);

    const byCategory = new Map<string, Item[]>();
    for (const item of items) {
      const category = benchmarks?.[item.task]?.category ?? "other";
      byCategory.set(category, [...(byCategory.get(category) ?? []), item]);
    }
    return [...byCategory.entries()];
  }, [catalog, benchmarks, chosen, query]);

  return (
    <div className="wb-picker">
      <input
        className="input wb-search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="search inspect_evals tasks…"
        disabled={disabled}
      />
      {catalog === null && <span className="muted small">Loading catalog…</span>}
      {catalog !== null && groups.length === 0 && (
        <span className="muted small">No matching tasks.</span>
      )}
      {groups.map(([category, items]) => (
        <div className="wb-picker-group" key={category}>
          <div className="wb-cat-head">
            <span className="field-label">{category.replace("_", " ")}</span>
            <span className="wb-cat-count mono">{items.length}</span>
          </div>
          <div className="wb-cards">
            {items.map((item) => {
              const reqs = requirements?.[item.task] ?? [];
              const blocked = capabilities
                ? reqs.filter((req) => !capabilities[req]?.available)
                : [];
              const isBlocked = blocked.length > 0;
              return (
                <button
                  type="button"
                  key={item.task}
                  className={"wb-card wb-card-action" + (isBlocked ? " is-blocked" : "")}
                  onClick={() => onAdd(item.task)}
                  disabled={disabled || isBlocked}
                >
                  <span className="wb-card-top">
                    <span className="wb-card-title">{item.title}</span>
                    <span className="wb-card-cta">{isBlocked ? "Unavailable" : "Add"}</span>
                  </span>
                  <span className="wb-card-id mono">{item.task}</span>
                  <span className="wb-card-desc">{item.measures}</span>
                  {reqs.length > 0 && (
                    <span className="wb-reqs">
                      {reqs.map((req) => {
                        const available = capabilities
                          ? capabilities[req]?.available === true
                          : undefined;
                        return (
                          <span
                            key={req}
                            className={
                              "wb-req" +
                              (available === true
                                ? " ok"
                                : available === false
                                  ? " blocked"
                                  : "")
                            }
                            title={
                              available === true
                                ? `${req} available`
                                : available === false
                                  ? `${req} is not available`
                                  : `${req} availability unknown`
                            }
                          >
                            {req}
                          </span>
                        );
                      })}
                    </span>
                  )}
                  {isBlocked && (
                    <span className="wb-card-alert">
                      {blocked.map((req) => {
                        const detail = capabilities?.[req]?.detail;
                        return (
                          <span className="wb-card-alert-line" key={req}>
                            {req} is not available
                            {detail ? ` (${detail})` : ""}
                          </span>
                        );
                      })}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
