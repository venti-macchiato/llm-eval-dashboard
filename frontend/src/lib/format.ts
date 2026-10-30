export function toDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const iso = value.includes("T") ? value : value.replace(" ", "T");
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function fmtNum(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtInt(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  return Number.isNaN(n) ? "—" : Math.round(n).toLocaleString();
}

export function shortDate(value: string | null | undefined): string {
  const d = toDate(value);
  if (!d) return "—";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function timeAgo(value: string | null | undefined): string {
  const d = toDate(value);
  if (!d) return "—";
  const secs = Math.round((Date.now() - d.getTime()) / 1000);
  if (secs < 60) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return shortDate(value);
}

/** Background tint for a score in [0,1]; higher = stronger success tint. */
export function scoreTint(score: number | null): string | undefined {
  if (score === null) return undefined;
  const s = Math.max(0, Math.min(1, Number(score)));
  const pct = Math.round(6 + s * 52);
  return `color-mix(in srgb, var(--success) ${pct}%, transparent)`;
}
