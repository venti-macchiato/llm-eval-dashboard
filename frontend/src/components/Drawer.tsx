import type { ReactNode } from "react";
import { IconClose } from "./Icons";

export function Drawer({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="drawer-backdrop" onClick={onClose} role="presentation">
      <aside
        className="drawer"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="drawer-head">
          <div>
            <h2>{title}</h2>
            {subtitle && <div className="muted small" style={{ marginTop: 2 }}>{subtitle}</div>}
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            <IconClose />
          </button>
        </div>
        {children}
      </aside>
    </div>
  );
}
