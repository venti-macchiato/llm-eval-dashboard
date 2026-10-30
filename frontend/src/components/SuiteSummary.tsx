import type { BenchmarkEntry, TaskSpec } from "../types";

type Capability = { available: boolean; detail?: string | null };

export function SuiteSummary({
  tasks,
  benchmarks,
  requirements,
  capabilities,
}: {
  tasks: TaskSpec[] | undefined;
  benchmarks: Record<string, BenchmarkEntry> | undefined;
  requirements?: Record<string, string[]>;
  capabilities?: Record<string, Capability>;
}) {
  if (!tasks?.length) return null;
  return (
    <div className="wb-cards wb-suite-cards">
      {tasks.map((item) => {
        const task = item.task.replace(/^inspect_evals\//, "");
        const meta = benchmarks?.[task];
        const reqs = requirements?.[task.toLowerCase()] ?? [];
        const missing = capabilities
          ? reqs.filter((req) => !capabilities[req]?.available)
          : [];
        return (
          <div
            className={"wb-card wb-card-static" + (missing.length > 0 ? " is-blocked" : "")}
            key={item.task}
          >
            <span className="wb-card-top">
              <span className="wb-card-title">{meta?.title ?? task}</span>
            </span>
            <span className="wb-card-id mono">{task} · {item.limit} samples</span>
            <span className="wb-card-desc">
              {meta?.measures ?? "No curated description yet."}
            </span>
            {reqs.length > 0 && (
              <span className="wb-reqs">
                {reqs.map((req) => {
                  const available = capabilities ? capabilities[req]?.available === true : undefined;
                  return (
                    <span
                      key={req}
                      className={
                        "wb-req" +
                        (available === true ? " ok" : available === false ? " blocked" : "")
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
            {missing.length > 0 && (
              <span className="wb-card-alert">
                {missing.map((req) => (
                  <span className="wb-card-alert-line" key={req}>
                    {req} is not available
                    {capabilities?.[req]?.detail ? ` (${capabilities?.[req]?.detail})` : ""}
                  </span>
                ))}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
