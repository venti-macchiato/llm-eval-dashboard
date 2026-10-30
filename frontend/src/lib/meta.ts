import type { HardwareDeclared, HardwareInfo, Run } from "../types";

/** Fields shown for declared hardware, in reading order. */
export const HARDWARE_FIELDS: { key: string; label: string }[] = [
  { key: "backend", label: "Backend" },
  { key: "backend_version", label: "Backend version" },
  { key: "quant", label: "Quantisation" },
  { key: "gpu", label: "GPU" },
  { key: "vram_gb", label: "VRAM (GB)" },
  { key: "ctx_size", label: "Context (tokens)" },
  { key: "offload", label: "Offload" },
  { key: "host", label: "Host" },
  { key: "notes", label: "Notes" },
];

/** Fields whose difference makes two scores not directly comparable. */
const COMPARABLE_FIELDS = ["backend", "backend_version", "quant", "gpu", "vram_gb", "ctx_size", "offload"];

/** Parse the run's stored meta JSON. Malformed rows are treated as absent. */
export function parseMeta(run: Run | null | undefined): Record<string, unknown> | null {
  if (!run?.meta) return null;
  try {
    const parsed = JSON.parse(run.meta) as unknown;
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** Hardware evidence recorded on a run, or null when it predates the feature. */
export function hardwareOf(run: Run | null | undefined): HardwareInfo | null {
  // Persisted boundary: ingest wrote this shape (see hardware.snapshot).
  const hw = parseMeta(run)?.hardware as HardwareInfo | undefined;
  if (!hw || typeof hw !== "object") return null;
  const declared =
    hw.declared && typeof hw.declared === "object" && !Array.isArray(hw.declared)
      ? hw.declared
      : undefined;
  const rawProbe = hw.probe;
  const probe =
    rawProbe && typeof rawProbe === "object"
      ? { ...rawProbe, gpus: Array.isArray(rawProbe.gpus) ? rawProbe.gpus : [] }
      : undefined;
  if (!declared && !probe) return null;
  return { declared, probe };
}

export function fmtCtx(tokens: number | null | undefined): string {
  if (!tokens) return "";
  return tokens >= 1024 ? `${Math.round(tokens / 1024)}k` : String(tokens);
}

export function hardwareValue(declared: HardwareDeclared | undefined, key: string): string {
  const value = declared?.[key];
  if (value === undefined || value === null || value === "") return "—";
  if (Array.isArray(value)) return value.join(", ") || "—";
  if (typeof value === "number") return value.toLocaleString();
  return String(value);
}

/** Short label for tables: "Q3_K_XL · 32k ctx". Empty when nothing is known. */
export function configSummary(hardware: HardwareInfo | null): string {
  const declared = hardware?.declared;
  if (!declared) return "";
  const parts: string[] = [];
  if (declared.quant) parts.push(String(declared.quant));
  if (declared.ctx_size) parts.push(`${fmtCtx(declared.ctx_size)} ctx`);
  if (!parts.length) {
    // Any other declaration (gpu, vram_gb, offload, host, backend, …) still
    // tells variants apart, so fall back to the first field present.
    const first = HARDWARE_FIELDS.find((field) => field.key in declared);
    if (first) parts.push(hardwareValue(declared, first.key));
  }
  return parts.join(" · ");
}

/** Multi-line tooltip listing every declared field. */
export function hardwareTooltip(hardware: HardwareInfo | null): string {
  const declared = hardware?.declared;
  if (!declared) return "";
  return HARDWARE_FIELDS.filter((field) => field.key in declared)
    .map((field) => `${field.label}: ${hardwareValue(declared, field.key)}`)
    .join("\n");
}

export interface ConfigDiff {
  key: string;
  label: string;
  a: string;
  b: string;
}

/** Fields where two runs' declared configurations differ (missing counts). */
export function configDiffs(a: HardwareInfo | null, b: HardwareInfo | null): ConfigDiff[] {
  const da = a?.declared ?? {};
  const db = b?.declared ?? {};
  return COMPARABLE_FIELDS.map((key) => {
    const field = HARDWARE_FIELDS.find((item) => item.key === key);
    return { key, label: field?.label ?? key, a: hardwareValue(da, key), b: hardwareValue(db, key) };
  }).filter((diff) => diff.a !== diff.b);
}
