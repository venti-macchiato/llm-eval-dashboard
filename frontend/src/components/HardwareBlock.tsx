import type { HardwareInfo } from "../types";
import { HARDWARE_FIELDS, hardwareValue } from "../lib/meta";
import { shortDate } from "../lib/format";

/**
 * Neon channel for each critical hardware vector. Declared values stay
 * verbatim — only the presentation layer assigns colour.
 */
const SIGNALS: Record<string, string> = {
  quant: "hw-quant",
  vram_gb: "hw-vram",
  ctx_size: "hw-ctx",
  backend: "hw-backend",
};

/** Free-text fields that need the full row instead of one narrow cell. */
const WIDE: Record<string, true> = { notes: true };

/** Declared + probed hardware evidence for one run. */
export function HardwareBlock({ hardware }: { hardware: HardwareInfo | null }) {
  if (!hardware) {
    return (
      <div className="small muted">
        No hardware recorded. Declare it under <span className="mono">hardware:</span> for this
        model in config.yaml, then ingest again.
      </div>
    );
  }

  const declared = hardware.declared;
  const probe = hardware.probe;
  const declaredFields = HARDWARE_FIELDS.filter((field) => field.key in (declared ?? {}));
  const gpus = probe?.gpus ?? [];
  const host = probe?.host ?? "unknown host";

  return (
    <div className="hw">
      {declaredFields.length > 0 ? (
        <div className="hw-grid">
          {declaredFields.map((field) => {
            const signal = SIGNALS[field.key];
            const className = [
              "hw-card",
              signal ?? "",
              WIDE[field.key] ? "hw-wide" : "",
            ]
              .filter(Boolean)
              .join(" ");
            return (
              <div key={field.key} className={className}>
                <span className="hw-label">{field.label}</span>
                <span className="hw-value mono">{hardwareValue(declared, field.key)}</span>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="hw-empty">No declared hardware for this model.</div>
      )}

      {probe && (
        <div className="hw-probe">
          <div className="hw-probe-head">
            <span className="hw-probe-badge">local probe</span>
            <span className="hw-probe-host mono">{host}</span>
            {probe.captured_at && (
              <span className="hw-probe-time mono">{shortDate(probe.captured_at)}</span>
            )}
          </div>

          <div className="hw-gpus">
            {gpus.length > 0 ? (
              gpus.map((gpu, index) => (
                <div className="hw-gpu" key={`${gpu.name}-${index}`}>
                  <span className="hw-gpu-name">{gpu.name}</span>
                  {gpu.memory_gb ? <span className="hw-gpu-meta">{gpu.memory_gb} GB</span> : null}
                  {gpu.driver ? <span className="hw-gpu-meta">driver {gpu.driver}</span> : null}
                </div>
              ))
            ) : (
              <div className="hw-empty mono">— no GPUs reported</div>
            )}
          </div>

          <p className="hw-probe-note">
            Measured on {host}; attached only because the endpoint runs there. Not evidence about a
            remote server.
          </p>
        </div>
      )}
    </div>
  );
}
