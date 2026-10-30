import type { ReactNode } from "react";

export function Panel({
  title,
  hint,
  actions,
  children,
  noBody,
}: {
  title?: ReactNode;
  hint?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  noBody?: boolean;
}) {
  return (
    <section className="panel">
      {(title || actions) && (
        <header className="panel-head">
          <div className="row" style={{ gap: 8 }}>
            {title && <span className="panel-title">{title}</span>}
            {hint && <span className="panel-hint">{hint}</span>}
          </div>
          {actions}
        </header>
      )}
      {noBody ? children : <div className="panel-body">{children}</div>}
    </section>
  );
}

export function Kpi({
  label,
  value,
  sub,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="panel kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty-state">{children}</div>;
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <div className="empty-state" style={{ color: "var(--error)" }}>{children}</div>;
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return <div className="empty-state">{label}</div>;
}
