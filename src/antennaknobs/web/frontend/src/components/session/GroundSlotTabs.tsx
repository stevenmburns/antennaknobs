import type { ReactNode } from "react";
import type { SoilPresetSchema } from "../../lib/ground";
import { groundSlotLabel, type GroundSlot, type GroundSlotId } from "../../lib/groundSlots";

// The ground slots' tab strip (AK#1794), the SolverSlotTabs twin: one click
// switches the ground every solve and chart reads, and each tab's ⚙ opens
// THAT slot's ground settings (AK#1801), as a solver tab's ⚙ opens its
// slot's options, so the input pane carries one line per slot instead of the
// whole ground panel. `children` is the compact notices line for the active
// slot, under the strip. Renders however many slots it is given.
export function GroundSlotTabs({
  slots,
  activeSlot,
  onSelect,
  onOpenGear,
  soilPresets = [],
  children,
}: {
  slots: GroundSlot[];
  activeSlot: GroundSlotId;
  onSelect: (id: GroundSlotId) => void;
  onOpenGear: (id: GroundSlotId) => void;
  soilPresets?: SoilPresetSchema[];
  children?: ReactNode;
}) {
  const active = slots.find((s) => s.id === activeSlot) ?? slots[0];
  return (
    <div className="field">
      <label>
        <span>ground slot</span>
        <span>{groundSlotLabel(active, soilPresets)}</span>
      </label>
      <div className="backend-tabs" role="tablist" aria-label="Ground slots">
        {slots.map((slot) => {
          const label = groundSlotLabel(slot, soilPresets);
          return (
            <div key={slot.id} className="backend-tab-cell">
              <button
                role="tab"
                aria-selected={activeSlot === slot.id}
                aria-label={`Ground slot ${slot.id}: ${label}`}
                className={`backend-tab-btn ${activeSlot === slot.id ? "active" : ""}`}
                title={label}
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
      </div>
      {children}
    </div>
  );
}
