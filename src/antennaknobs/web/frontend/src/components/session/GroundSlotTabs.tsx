import type { ReactNode } from "react";
import type { BackendEntry } from "../../lib/backends";
import type { SoilPresetSchema } from "../../lib/ground";
import {
  appliedGroundChange,
  groundRefusal,
  groundSlotLabel,
  type GroundSlot,
  type GroundSlotId,
} from "../../lib/groundSlots";
import { AddSlotButton } from "./SlotStripControls";

// The ground slots' tab strip (AK#1794), the SolverSlotTabs twin: one click
// switches the ground every solve and chart reads, and each tab's ⚙ opens
// THAT slot's ground settings (AK#1801), as a solver tab's ⚙ opens its
// slot's options, so the input pane carries one line per slot instead of the
// whole ground panel. `children` is the compact notices line for the active
// slot, under the strip. Renders however many slots it is given, then the +
// that adds one (AK#1801). With `backend` (the ACTIVE solver slot's), each tab
// also says when that solver refuses the slot (AK#1856: NEC-5 has no
// refl-coef, so the tab reads "refl-coef ⊘" and its hover gives the server's
// sentence) or runs something other than what it holds (AK#1854: "refl-coef
// → PEC image" on a momwire solver without the model). The tabs size to their own labels rather than to the solver
// strip's columns above, so the two strips do not read as pairs.
export function GroundSlotTabs({
  slots,
  activeSlot,
  onSelect,
  onOpenGear,
  soilPresets = [],
  backend,
  nextSlot = null,
  onAdd = () => {},
  children,
}: {
  slots: GroundSlot[];
  activeSlot: GroundSlotId;
  onSelect: (id: GroundSlotId) => void;
  onOpenGear: (id: GroundSlotId) => void;
  soilPresets?: SoilPresetSchema[];
  /** The active solver slot's backend: what each ground is solved as. */
  backend?: BackendEntry | undefined;
  /** The id the strip's + adds (AK#1801), or null: no + (the family is full). */
  nextSlot?: GroundSlotId | null;
  onAdd?: () => void;
  children?: ReactNode;
}) {
  const active = slots.find((s) => s.id === activeSlot) ?? slots[0];
  return (
    <div className="field">
      <label>
        <span>ground slot</span>
        <span>{groundSlotLabel(active, soilPresets, backend)}</span>
      </label>
      <div className="backend-tabs ground-slot-tabs" role="tablist" aria-label="Ground slots">
        {slots.map((slot) => {
          const label = groundSlotLabel(slot, soilPresets, backend);
          const refused = backend ? groundRefusal(slot, backend) : null;
          const changed = backend && !refused ? appliedGroundChange(slot, backend) : null;
          const title = refused
            ? `${label}: refused on ${backend!.label}. ${refused}`
            : changed
              ? `${label} (solved as ${changed} on ${backend!.label})`
              : label;
          return (
            <div key={slot.id} className="backend-tab-cell">
              <button
                role="tab"
                aria-selected={activeSlot === slot.id}
                aria-label={`Ground slot ${slot.id}: ${label}`}
                data-refused={refused ? "1" : "0"}
                className={`backend-tab-btn ${activeSlot === slot.id ? "active" : ""}${refused ? " is-refused" : ""}`}
                title={title}
                onClick={() => onSelect(slot.id)}
              >
                <span className="slot-letter">{slot.id}</span>
                <span className="slot-sub">{label}</span>
              </button>
              <button
                className="backend-gear-btn"
                title={`Ground slot ${slot.id} settings`}
                aria-label={`Ground slot ${slot.id} settings`}
                onClick={() => onOpenGear(slot.id)}
              >
                ⚙
              </button>
            </div>
          );
        })}
        <AddSlotButton noun="ground" next={nextSlot} onAdd={onAdd} />
      </div>
      {children}
    </div>
  );
}
