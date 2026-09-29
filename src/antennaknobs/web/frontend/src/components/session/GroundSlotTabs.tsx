import type { SoilPresetSchema } from "../../lib/ground";
import { groundSlotLabel, type GroundSlot, type GroundSlotId } from "../../lib/groundSlots";

// The ground slots' tab strip (AK#1794), the SolverSlotTabs twin: one click
// switches the ground every solve and chart reads. No gear: the ground panel
// right below it edits the active slot. Renders however many slots it is
// given.
export function GroundSlotTabs({
  slots,
  activeSlot,
  onSelect,
  soilPresets = [],
}: {
  slots: GroundSlot[];
  activeSlot: GroundSlotId;
  onSelect: (id: GroundSlotId) => void;
  soilPresets?: SoilPresetSchema[];
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
            </div>
          );
        })}
      </div>
    </div>
  );
}
