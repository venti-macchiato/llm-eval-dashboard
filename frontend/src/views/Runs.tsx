import { useMemo, useState } from "react";
import { api, exportUrl } from "../lib/api";
import type { Column } from "../components/SortableTable";
import { SortableTable } from "../components/SortableTable";
import { ChipFilter } from "../components/ChipFilter";
import { RunDrawer } from "../components/RunDrawer";
import { ErrorNote, Panel, Spinner } from "../components/Ui";
import { IconDownload, IconRefresh } from "../components/Icons";
import { fmtInt, fmtNum, shortDate, timeAgo, toDate } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { configSummary, hardwareOf, hardwareTooltip } from "../lib/meta";
import type { Run } from "../types";

const columns: Column<Run>[] = [
  {
    key: "created",
    header: "Created",
    sortValue: (r) => toDate(r.created)?.getTime() ?? 0,
    render: (r) => (
      <span className="hx-created" title={String(r.created)}>
        <span className="hx-created-ago">{timeAgo(r.created)}</span>
        <span className="faint small hx-created-date">· {shortDate(r.created)}</span>
      </span>
    ),
  },
  {
    key: "model",
    header: "Model",
    sortValue: (r) => r.model,
    render: (r) => <span className="hx-model">{r.model}</span>,
  },
  {
    key: "task",
    header: "Task",
    sortValue: (r) => r.task,
    render: (r) => <span className="hx-task">{r.task}</span>,
  },
  {
    key: "config",
    header: "Config",
    sortValue: (r) => configSummary(hardwareOf(r)),
    render: (r) => {
      const hardware = hardwareOf(r);
      const summary = configSummary(hardware);
      if (!summary) return <span className="faint">—</span>;
      return (
        <span className="hx-config" title={hardwareTooltip(hardware)}>
          {summary}
        </span>
      );
    },
  },
  {
    key: "score",
    header: "Score",
    align: "right",
    sortValue: (r) => r.score ?? -1,
    render: (r) => <strong className="hx-score">{fmtNum(r.score)}</strong>,
  },
  {
    key: "stderr",
    header: "Std err",
    align: "right",
    sortValue: (r) => r.stderr ?? -1,
    render: (r) => <span className="hx-stderr">{fmtNum(r.stderr, 4)}</span>,
  },
  {
    key: "samples",
    header: "Samples",
    align: "right",
    sortValue: (r) => r.samples ?? -1,
    render: (r) => <span className="hx-count">{fmtInt(r.samples)}</span>,
  },
  {
    key: "tokens",
    header: "Tokens in/out",
    align: "right",
    sortValue: (r) => r.input_tokens ?? -1,
    render: (r) => (
      <span className="hx-tok">
        <span className="hx-tok-label hx-tok-label-in">in</span>
        <span className="hx-tok-val hx-tok-val-in">{fmtInt(r.input_tokens)}</span>
        <span className="hx-tok-label hx-tok-label-out">out</span>
        <span className="hx-tok-val hx-tok-val-out">{fmtInt(r.output_tokens)}</span>
      </span>
    ),
  },
  {
    key: "duration_s",
    header: "Duration",
    align: "right",
    sortValue: (r) => r.duration_s ?? -1,
    render: (r) =>
      r.duration_s === null ? (
        "—"
      ) : (
        <span className="hx-dur">
          {fmtNum(r.duration_s, 1)}
          <span className="hx-unit">s</span>
        </span>
      ),
  },
];

export function Runs() {
  const runsQ = useAsync(() => api.runs(), []);
  const [selModels, setSelModels] = useState<Set<string>>(new Set());
  const [selTasks, setSelTasks] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [active, setActive] = useState<Run | null>(null);
  const [ingestMsg, setIngestMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const all = runsQ.data ?? [];
  const modelOptions = useMemo(() => [...new Set(all.map((r) => r.model))].sort(), [all]);
  const taskOptions = useMemo(() => [...new Set(all.map((r) => r.task))].sort(), [all]);

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return all.filter((r) => {
      if (selModels.size && !selModels.has(r.model)) return false;
      if (selTasks.size && !selTasks.has(r.task)) return false;
      if (!needle) return true;
      return `${r.eval_id} ${r.model} ${r.task} ${configSummary(hardwareOf(r))}`
        .toLowerCase()
        .includes(needle);
    });
  }, [all, selModels, selTasks, search]);

  const exportParams = {
    model: [...selModels],
    task: [...selTasks],
  };

  const ingest = async () => {
    setBusy(true);
    setIngestMsg(null);
    try {
      const result = await api.ingest();
      setIngestMsg(
        `Ingested ${result.new} new run(s), updated ${result.updated}, skipped ${result.skipped}.`,
      );
      runsQ.reload();
    } catch (err) {
      setIngestMsg(`Ingest failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  if (runsQ.error) return <ErrorNote>Failed to load runs: {runsQ.error}</ErrorNote>;
  if (runsQ.loading && !runsQ.data) return <Spinner />;

  return (
    <div className="stack">
      <div className="panel hx-filters">
        <div className="row hx-filters-row">
          <ChipFilter label="Models" options={modelOptions} selected={selModels} onChange={setSelModels} />
          <ChipFilter label="Tasks" options={taskOptions} selected={selTasks} onChange={setSelTasks} />
          <div className="field hx-search">
            <span className="field-label">Search</span>
            <input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="eval id, model, task" />
          </div>
        </div>
      </div>

      <Panel
        title={`Run history`}
        hint={`${rows.length} run(s)`}
        noBody
        actions={
          <div className="row" style={{ gap: 6 }}>
            <button className="btn btn-sm" onClick={ingest} disabled={busy}>
              <IconRefresh /> Ingest
            </button>
            <a className="btn btn-sm" href={exportUrl("runs", "csv", exportParams)}>
              <IconDownload /> CSV
            </a>
            <a className="btn btn-sm" href={exportUrl("runs", "json", exportParams)}>
              <IconDownload /> JSON
            </a>
          </div>
        }
      >
        {ingestMsg && (
          <div className="small muted hx-ingest-note">{ingestMsg}</div>
        )}
        <div className="hx-grid">
          <SortableTable
            rows={rows}
            columns={columns}
            rowKey={(r) => r.eval_id}
            initialSort={{ key: "created", dir: "desc" }}
            rowAction={(r) => (
              <button
                className="btn btn-sm"
                onClick={() => setActive(r)}
                aria-label={`Open run ${r.task} from ${r.model}`}
              >
                Open
              </button>
            )}
            empty="No runs match the current filters."
          />
        </div>
      </Panel>

      {active && <RunDrawer run={active} onClose={() => setActive(null)} />}
    </div>
  );
}
