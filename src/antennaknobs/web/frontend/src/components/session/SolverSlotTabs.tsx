import { backendDisplayLabel, SLOT_ORDER } from "../../lib/backends";
import type { BackendEntry, BackendOpts, Slot, SlotConfig } from "../../lib/backends";

export function SolverSlotTabs({
  slots,
  activeSlot,
  onSelect,
  onOpenGear,
  backend,
  currentOpts,
  nPerWire,
}: {
  slots: Record<Slot, SlotConfig>;
  activeSlot: Slot;
  onSelect: (s: Slot) => void;
  onOpenGear: (s: Slot) => void;
  backend: BackendEntry;
  currentOpts: BackendOpts;
  nPerWire: number;
}) {
  return (
    <div className="field">
      <label>
        <span>solver slot</span>
        <span>{backendDisplayLabel(backend, currentOpts)} · N={nPerWire}</span>
      </label>
      <div className="backend-tabs" role="tablist">
        {SLOT_ORDER.map((s) => {
          const cfg = slots[s];
          return (
            <div key={s} className="backend-tab-cell">
              <button
                role="tab"
                aria-selected={activeSlot === s}
                aria-label={`Solver slot ${s}: ${backendDisplayLabel(cfg.backend, cfg.opts)}, N=${cfg.opts.nPerWire}`}
                className={`backend-tab-btn ${activeSlot === s ? "active" : ""}`}
                title={`${backendDisplayLabel(cfg.backend, cfg.opts)}, N=${cfg.opts.nPerWire}`}
                onClick={() => onSelect(s)}
              >
                <span className="slot-letter">{s}</span>
                <span className="slot-sub">{backendDisplayLabel(cfg.backend, cfg.opts)}</span>
              </button>
              <button
                className="backend-gear-btn"
                title={`Slot ${s} options`}
                aria-label={`Slot ${s} options`}
                onClick={() => onOpenGear(s)}
              >
                ⚙
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
