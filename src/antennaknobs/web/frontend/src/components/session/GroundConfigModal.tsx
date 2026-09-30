import { useEffect, type ComponentProps } from "react";
import { GroundPanel } from "./GroundPanel";

// One ground slot's settings (AK#1801), behind that slot's ⚙ on the ground-
// slot tab strip: the ground panel's controls, editing THIS slot whether or
// not it is the active one, in the solver gear's modal (BackendConfigModal's
// overlay, card and header, which already fit a 390 px phone). The caller
// hands it the slot's own values and setters; which slot the solves read is
// the tab strip's business, not this panel's.
export function GroundConfigModal({
  slotId,
  label,
  onClose,
  ...panel
}: {
  slotId: string;
  /** The slot's one-line summary, as its tab shows it. */
  label: string;
  onClose: () => void;
} & ComponentProps<typeof GroundPanel>) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="backend-config-overlay" onClick={onClose}>
      <div
        className="backend-config-modal ground-config-modal"
        role="dialog"
        aria-label={`Ground slot ${slotId} settings`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="backend-config-header">
          <strong>
            Ground slot {slotId} — {label}
          </strong>
          <button className="backend-config-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="backend-config-body">
          <GroundPanel {...panel} />
        </div>
      </div>
    </div>
  );
}
