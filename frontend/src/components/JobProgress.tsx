import { Panel } from "./Ui";
import type { EvalJob } from "../types";

const FAILURE = /error|traceback|exception|failed/i;

function logTone(line: string): string {
  if (FAILURE.test(line)) return "is-err";
  if (/^Log:/i.test(line)) return "is-ok";
  return "";
}

export function JobProgress({ job }: { job: EvalJob }) {
  const progressPct =
    job.samples_total > 0
      ? Math.min(100, (job.samples_done / job.samples_total) * 100)
      : job.task_total > 0
        ? Math.min(100, (job.task_index / job.task_total) * 100)
        : 0;

  return (
    <Panel
      title="Job progress"
      hint={job.current_task ?? job.suite}
      actions={
        <span
          className={
            "badge " +
            (job.state === "done" ? "ok" : job.state === "failed" ? "err" : "warn")
          }
        >
          {job.state}
        </span>
      }
    >
      <div className="wb-job">
        <div className="wb-job-meta">
          <span className="small muted">
            Task {job.task_index} of {job.task_total}
            {(job.repeat_total ?? 0) > 1 &&
              ` · repeat ${job.repeat_index}/${job.repeat_total}`}
            {job.samples_total > 0 &&
              ` · ${job.samples_done}/${job.samples_total} samples`}
          </span>
          {job.error && <span className="wb-job-error small">{job.error}</span>}
        </div>

        <div className="wb-progress">
          <span className="wb-progress-fill" style={{ width: `${progressPct}%` }} />
          {job.state === "running" && progressPct > 0 && (
            <span
              className="wb-progress-lead"
              style={{ left: `min(${progressPct}%, calc(100% - 6px))` }}
            />
          )}
        </div>

        {job.results?.length > 0 && (
          <div className="chips wb-results">
            {job.results.map((r) => (
              <span
                key={`${r.task}-${r.repeat ?? 0}`}
                className={"badge " + (r.ok ? "ok" : "err")}
              >
                {r.task}
                {(r.repeats ?? 0) > 1 ? ` #${r.repeat}` : ""}
              </span>
            ))}
          </div>
        )}

        {job.log_tail?.length > 0 && (
          <div className="wb-console">
            <div className="wb-console-bar">
              <span className="wb-console-dots">
                <i /><i /><i />
              </span>
              <span className="wb-console-label mono">{job.model || job.suite}</span>
              <span className="wb-console-count mono">{job.log_tail.length} lines</span>
            </div>
            <pre className="wb-console-body">
              {job.log_tail.map((line, i) => (
                <div key={i} className={"wb-log-line " + logTone(line)}>
                  {line}
                </div>
              ))}
            </pre>
          </div>
        )}
      </div>
    </Panel>
  );
}
