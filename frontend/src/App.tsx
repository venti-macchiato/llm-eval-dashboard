import { useState, type ComponentType, type ReactNode } from "react";
import { useTheme } from "./lib/theme";
import { Overview } from "./views/Overview";
import { Leaderboard } from "./views/Leaderboard";
import { Runs } from "./views/Runs";
import { Compare } from "./views/Compare";
import { RunEval } from "./views/RunEval";
import {
  IconBook,
  IconCheck,
  IconCompare,
  IconGrid,
  IconLayers,
  IconMoon,
  IconOverview,
  IconPlay,
  IconSun,
  IconTable,
} from "./components/Icons";
import { Benchmarks } from "./views/Benchmarks";
import { Variants } from "./views/Variants";
import { Prompts } from "./views/Prompts";

type ViewKey =
  | "overview"
  | "leaderboard"
  | "variants"
  | "runs"
  | "compare"
  | "run"
  | "prompts"
  | "benchmarks";

const NAV: {
  key: ViewKey;
  label: string;
  title: string;
  desc: string;
  icon: ReactNode;
}[] = [
  {
    key: "overview",
    label: "Overview",
    title: "Overview",
    desc: "Accuracy trends and streaming speed across your models",
    icon: <IconOverview />,
  },
  {
    key: "leaderboard",
    label: "Leaderboard",
    title: "Leaderboard",
    desc: "Latest score per model and task",
    icon: <IconGrid />,
  },
  {
    key: "variants",
    label: "Variants",
    title: "Variant matrix",
    desc: "Model variants grouped by base model, scored against a baseline",
    icon: <IconLayers />,
  },
  {
    key: "runs",
    label: "Runs",
    title: "Run history",
    desc: "Every ingested run, with drilldown and export",
    icon: <IconTable />,
  },
  {
    key: "compare",
    label: "Compare",
    title: "Compare runs",
    desc: "Head-to-head metrics between two runs",
    icon: <IconCompare />,
  },
  {
    key: "run",
    label: "Run eval",
    title: "Run eval",
    desc: "Launch benchmarks and speed probes",
    icon: <IconPlay />,
  },
  {
    key: "prompts",
    label: "Prompts",
    title: "Prompt tests",
    desc: "Custom prompts with pass/fail checks against your deployment",
    icon: <IconCheck />,
  },
  {
    key: "benchmarks",
    label: "Benchmarks",
    title: "Benchmark guide",
    desc: "What each task measures and how to read its score",
    icon: <IconBook />,
  },
];

const VIEWS: Record<ViewKey, ComponentType> = {
  overview: Overview,
  leaderboard: Leaderboard,
  variants: Variants,
  runs: Runs,
  compare: Compare,
  run: RunEval,
  prompts: Prompts,
  benchmarks: Benchmarks,
};

export function App() {
  const [view, setView] = useState<ViewKey>("overview");
  const { theme, toggle } = useTheme();
  const meta = NAV.find((item) => item.key === view) ?? NAV[0];
  const View = VIEWS[view];

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">LL</span>
          <span className="brand-name">Eval Dashboard</span>
        </div>
        <nav className="nav">
          {NAV.map((item) => (
            <button
              key={item.key}
              className={"nav-item" + (item.key === view ? " active" : "")}
              onClick={() => setView(item.key)}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <button className="btn btn-ghost btn-sm" onClick={toggle} title="Toggle theme">
            {theme === "dark" ? <IconSun /> : <IconMoon />}
            {theme === "dark" ? "Light" : "Dark"}
          </button>
        </div>
      </aside>
      <main className="main">
        <div className="main-inner">
          <div className="page-head">
            <div>
              <h1>{meta.title}</h1>
              <div className="sub">{meta.desc}</div>
            </div>
          </div>
          <View />
        </div>
      </main>
    </div>
  );
}
