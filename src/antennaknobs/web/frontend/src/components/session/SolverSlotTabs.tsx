import { backendDisplayLabel, slotOrder } from "../../lib/backends";
import type { BackendEntry, BackendOpts, Slot, SlotConfig } from "../../lib/backends";
import { AddSlotButton } from "./SlotStripControls";

export function SolverSlotTabs({
  slots,
  activeSlot,
  onSelect,
  onOpenGear,
  backend,
  currentOpts,
  nPerWire,
  fixedSegmentCounts = false,
  nextSlot = null,
  onAdd = () => {},
}: {
  slots: Record<Slot, SlotConfig>;
  activeSlot: Slot;
  onSelect: (s: Slot) => void;
  onOpenGear: (s: Slot) => void;
  backend: BackendEntry;
  currentOpts: BackendOpts;
  nPerWire: number;
  /** AK#1432: the design's wires carry their own counts (file designs), so
   *  the label says so instead of showing an N that does nothing. */
  fixedSegmentCounts?: boolean;
  /** The id the strip's + adds (AK#1801), or null: no + (the family is full). */
  nextSlot?: Slot | null;
  onAdd?: () => void;
}) {
  const nLabel = (n: number) => (fixedSegmentCounts ? "deck's own" : String(n));
  return (
    <div className="field">
      <label>
        <span>solver slot</span>
        <span>{backendDisplayLabel(backend, currentOpts)} · N={nLabel(nPerWire)}</span>
      </label>
      <div className="backend-tabs" role="tablist">
        {slotOrder(slots).map((s) => {
          const cfg = slots[s];
          return (
            <div key={s} className="backend-tab-cell">
              <button
                role="tab"
                aria-selected={activeSlot === s}
                aria-label={`Solver slot ${s}: ${backendDisplayLabel(cfg.backend, cfg.opts)}, N=${nLabel(cfg.opts.nPerWire)}`}
                className={`backend-tab-btn ${activeSlot === s ? "active" : ""}`}
                title={`${backendDisplayLabel(cfg.backend, cfg.opts)}, N=${nLabel(cfg.opts.nPerWire)}`}
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
        <AddSlotButton noun="solver" next={nextSlot} onAdd={onAdd} />
      </div>
    </div>
  );
}
