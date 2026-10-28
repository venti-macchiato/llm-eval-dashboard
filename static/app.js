"use strict";

/* LLM eval dashboard frontend.
 * Fetches from the FastAPI JSON endpoints and renders:
 *   - summary cards (latest score + delta vs previous)
 *   - accuracy trend, throughput, and TTFT charts (Chart.js)
 *   - sortable run-history table
 * All dynamic text is inserted via textContent (no innerHTML) to avoid XSS.
 */

const state = {
  models: [],
  tasks: [],
  selectedModels: new Set(),
  selectedTasks: new Set(),
  runs: [],
  speed: [],
  sortKey: "created",
  sortDir: "desc",
};

const charts = { trend: null, tp: null, ttft: null };

const $ = (sel) => document.querySelector(sel);

function setStatus(msg, kind) {
  const el = $("#status");
  el.textContent = msg || "";
  el.className = "status" + (kind ? " " + kind : "");
}

function esc(value) {
  return String(value == null ? "" : value);
}

function fmt(n, digits = 3) {
  if (n == null || n === "") return "—";
  const f = Number(n);
  if (Number.isNaN(f)) return esc(n);
  return f.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

async function api(path, opts) {
  const resp = await fetch(path, opts);
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  return resp.json();
}

async function loadModels() {
  state.models = await api("/api/models");
  populatePickers();
  if (state.models.length && state.selectedModels.size === 0) {
    state.models.forEach((m) => state.selectedModels.add(m));
  }
}

async function loadTasks() {
  const runs = await api("/api/runs?limit=10000");
  const tasks = [...new Set(runs.map((r) => r.task)).filter(Boolean)];
  state.tasks = tasks;
  const picker = $("#task-picker");
  picker.innerHTML = "";
  tasks.forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = t;
    picker.appendChild(opt);
  });
}

function populatePickers() {
  const picker = $("#model-picker");
  picker.innerHTML = "";
  state.models.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    if (state.selectedModels.has(m)) opt.selected = true;
    picker.appendChild(opt);
  });
}

function collectSelected(pickerId) {
  const picker = $(pickerId);
  const selected = new Set();
  [...picker.options].forEach((o) => {
    if (o.selected) selected.add(o.value);
  });
  return selected;
}

function bindPickers() {
  $("#model-picker").addEventListener("change", () => {
    state.selectedModels = collectSelected("#model-picker");
    render();
  });
  $("#task-picker").addEventListener("change", () => {
    state.selectedTasks = collectSelected("#task-picker");
    render();
  });
}

function bindButtons() {
  $("#btn-ingest").addEventListener("click", async () => {
    const btn = $("#btn-ingest");
    btn.disabled = true;
    setStatus("Ingesting…", "busy");
    try {
      const body = await api("/api/ingest", { method: "POST" });
      setStatus(`Ingested ${body.new} new run(s).`, "ok");
      await refreshAll();
    } catch (err) {
      setStatus(`Ingest failed: ${err.message}`, "err");
    } finally {
      btn.disabled = false;
    }
  });

  $("#btn-speed").addEventListener("click", async () => {
    const btn = $("#btn-speed");
    btn.disabled = true;
    setStatus("Speed probe started in background.", "busy");
    try {
      await api("/api/speed/run", { method: "POST" });
      setTimeout(() => setStatus("Probe running; results appear shortly.", "ok"), 1500);
    } catch (err) {
      setStatus(`Speed probe failed: ${err.message}`, "err");
    } finally {
      btn.disabled = false;
      setTimeout(refreshSpeed, 2000);
    }
  });
}

async function refreshAll() {
  try {
    await Promise.all([loadModels(), loadTasks()]);
    await Promise.all([loadRuns(), loadSpeed()]);
    render();
    setStatus("Loaded.", "ok");
  } catch (err) {
    setStatus(`Load failed: ${err.message}`, "err");
  }
}

async function loadRuns() {
  const models = [...state.selectedModels];
  const tasks = [...state.selectedTasks];
  let path = "/api/runs?limit=10000";
  if (models.length) path += "&model=" + encodeURIComponent(models[0]);
  if (tasks.length) path += "&task=" + encodeURIComponent(tasks[0]);
  state.runs = await api(path);
}

async function loadSpeed() {
  const models = [...state.selectedModels];
  let path = "/api/speed?limit=10000";
  if (models.length) path += "&model=" + encodeURIComponent(models[0]);
  state.speed = await api(path);
}

async function refreshSpeed() {
  try {
    await loadSpeed();
    render();
  } catch (err) {
    setStatus(`Speed load failed: ${err.message}`, "err");
  }
}

function filteredRuns() {
  if (!state.selectedModels.size && !state.selectedTasks.size) return state.runs;
  return state.runs.filter(
    (r) =>
      (!state.selectedModels.size || state.selectedModels.has(r.model)) &&
      (!state.selectedTasks.size || state.selectedTasks.has(r.task))
  );
}

function renderCards() {
  const wrap = $("#cards");
  wrap.innerHTML = "";
  const runs = filteredRuns();
  if (!runs.length) {
    wrap.innerHTML = "";
    return;
  }
  // Group latest (model, task) by newest created.
  const grouped = new Map();
  runs
    .slice()
    .sort((a, b) => String(b.created).localeCompare(String(a.created)))
    .forEach((r) => {
      const key = r.model + "�|"�| + r.task;
      if (!grouped.has(key)) grouped.set(key, r);
    });
  const items = [...grouped.values()];

  items.forEach((r) => {
    const card = document.createElement("div");
    card.className = "card";

    const model = document.createElement("div");
    model.className = "model";
    model.textContent = r.model;
    card.appendChild(model);

    const task = document.createElement("div");
    task.className = "task";
    task.textContent = r.task;
    card.appendChild(task);

    const score = document.createElement("div");
    score.className = "score";
    score.textContent = fmt(r.score);
    card.appendChild(score);

    const delta = document.createElement("div");
    delta.className = "delta";
    if (r.prev_score == null) {
      delta.classList.add("none");
      delta.textContent = "no previous run";
    } else if (r.score == null) {
      delta.classList.add("none");
      delta.textContent = "score unknown";
    } else {
      const diff = r.score - r.prev_score;
      const arrow = diff > 0 ? "▲" : diff < 0 ? "▼" : "▬";
      delta.classList.add(diff > 0 ? "up" : diff < 0 ? "down" : "none");
      delta.textContent = `${arrow} ${fmt(Math.abs(diff), 3)} vs prev`;
    }
    card.appendChild(delta);
    wrap.appendChild(card);
  });
}

function renderTrend() {
  const empty = $("#empty-trend");
  const runs = filteredRuns();
  if (!runs.length) {
    charts.trend && charts.trend.destroy();
    charts.trend = null;
    empty.classList.remove("hidden");
    $("#chart-trend").classList.add("hidden");
    return;
  }
  empty.classList.add("hidden");
  $("#chart-trend").classList.remove("hidden");

  // One line per (model, task), sorted by created.
  const series = new Map();
  runs.forEach((r) => {
    const key = r.model + "‖" + r.task;
    if (!series.has(key)) series.set(key, []);
    series.get(key).push(r);
  });
  const datasets = [...series.entries()].map(([key, rows]) => {
    rows.sort((a, b) => String(a.created).localeCompare(String(b.created)));
    const color = seriesColor(key);
    return {
      label: key.replace("‖", " / "),
      data: rows.map((r) => ({ x: r.created, y: r.score })),
      borderColor: color,
      backgroundColor: color,
      borderWidth: 2,
      tension: 0.2,
      pointRadius: 3,
    };
  });

  const ctx = $("#trend-canvas");
  if (charts.trend) charts.trend.destroy();
  charts.trend = new Chart(ctx, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { beginAtZero: false, title: { display: true, text: "accuracy" } },
        x: { type: "time", title: { display: true, text: "run time" } },
      },
    },
  });
}

function seriesColor(key) {
  const colors = [
    getCss("--c1"), getCss("--c2"), getCss("--c3"),
    getCss("--c4"), getCss("--c5"), getCss("--c6"),
  ];
  let hash = 0;
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  return colors[hash % colors.length];
}

function getCss(varName) {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
}

function renderThroughput() {
  const empty = $("#empty-tp");
  if (!state.speed.length) {
    charts.tp && charts.tp.destroy();
    charts.tp = null;
    empty.classList.remove("hidden");
    $("#chart-tp").classList.add("hidden");
    return;
  }
  empty.classList.add("hidden");
  $("#chart-tp").classList.remove("hidden");

  const models = [...new Set(state.speed.map((s) => s.model))];
  const datasets = models.map((model, i) => {
    const rows = state.speed.filter((s) => s.model === model).sort(
      (a, b) => Number(a.ctx_tokens) - Number(b.ctx_tokens)
    );
    const colors = [getCss("--c1"), getCss("--c2"), getCss("--c3"), getCss("--c4")];
    return {
      label: model,
      data: rows.map((s) => ({ x: s.ctx_tokens, y: s.gen_tps })),
      borderColor: colors[i % colors.length],
      backgroundColor: colors[i % colors.length],
      type: "line",
      showLine: false,
      pointRadius: 6,
    };
  });

  const ctx = $("#tp-canvas");
  if (charts.tp) charts.tp.destroy();
  charts.tp = new Chart(ctx, {
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { type: "linear", title: { display: true, text: "context tokens" } },
        y: { title: { display: true, text: "gen tokens/sec" } },
      },
    },
  });
}

function renderTTFT() {
  const empty = $("#empty-ttft");
  if (!state.speed.length) {
    charts.ttft && charts.ttft.destroy();
    charts.ttft = null;
    empty.classList.remove("hidden");
    $("#chart-ttft").classList.add("hidden");
    return;
  }
  empty.classList.add("hidden");
  $("#chart-ttft").classList.remove("hidden");

  const models = [...new Set(state.speed.map((s) => s.model))];
  const datasets = models.map((model, i) => {
    const rows = state.speed.filter((s) => s.model === model).sort(
      (a, b) => Number(a.ctx_tokens) - Number(b.ctx_tokens)
    );
    const colors = [getCss("--c1"), getCss("--c2"), getCss("--c3"), getCss("--c4")];
    return {
      label: model,
      data: rows.map((s) => ({ x: s.ctx_tokens, y: s.ttft_s })),
      borderColor: colors[i % colors.length],
      backgroundColor: colors[i % colors.length],
      type: "line",
      showLine: false,
      pointRadius: 6,
    };
  });

  const ctx = $("#ttft-canvas");
  if (charts.ttft) charts.ttft.destroy();
  charts.ttft = new Chart(ctx, {
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { type: "linear", title: { display: true, text: "context tokens" } },
        y: { title: { display: true, text: "TTFT (s)" } },
      },
    },
  });
}

function renderTable() {
  const tbody = $("#runs-table tbody");
  tbody.innerHTML = "";
  const rows = filterAndSortRuns();
  rows.forEach((r) => {
    const tr = document.createElement("tr");

    const tCreated = document.createElement("td");
    tCreated.textContent = esc(r.created);
    tr.appendChild(tCreated);

    const tModel = document.createElement("td");
    tModel.textContent = esc(r.model);
    tr.appendChild(tModel);

    const tTask = document.createElement("td");
    tTask.textContent = esc(r.task);
    tr.appendChild(tTask);

    const tScore = document.createElement("td");
    tScore.className = "num";
    tScore.textContent = fmt(r.score);
    tr.appendChild(tScore);

    const tStderr = document.createElement("td");
    tStderr.className = "num";
    tStderr.textContent = fmt(r.stderr, 4);
    tr.appendChild(tStderr);

    const tSamples = document.createElement("td");
    tSamples.className = "num";
    tSamples.textContent = r.samples != null ? Number(r.samples).toLocaleString() : "—";
    tr.appendChild(tSamples);

    tbody.appendChild(tr);
  });
  updateHeaderStates();
}

function filterAndSortRuns() {
  const runs = filteredRuns();
  const key = state.sortKey;
  const dir = state.sortDir === "asc" ? 1 : -1;
  return runs.slice().sort((a, b) => {
    let av = a[key];
    let bv = b[key];
    if (key === "score" || key === "stderr" || key === "samples") {
      if (av == null) av = -Infinity;
      if (bv == null) bv = -Infinity;
      return (Number(av) - Number(bv)) * dir;
    }
    return String(av).localeCompare(String(bv)) * dir;
  });
}

function updateHeaderStates() {
  document.querySelectorAll("#runs-table th").forEach((th) => {
    th.classList.remove("asc", "desc");
    if (th.dataset.key === state.sortKey) th.classList.add(state.sortDir);
  });
}

function bindTableSort() {
  document.querySelectorAll("#runs-table th").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.key;
      if (state.sortKey === key) {
        state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
      } else {
        state.sortKey = key;
        state.sortDir = "asc";
      }
      renderTable();
    });
  });
}

function render() {
  renderCards();
  renderTrend();
  renderThroughput();
  renderTTFT();
  renderTable();
}

async function init() {
  bindPickers();
  bindButtons();
  bindTableSort();
  setStatus("Loading…", "busy");
  await refreshAll();
}

document.addEventListener("DOMContentLoaded", init);
