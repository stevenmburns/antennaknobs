import { useRef, useState } from "react";
import {
  defaultOptsFor,
  defaultSlots,
  type BackendEntry,
  type BackendOpts,
  type BackendRoster,
  type Slot,
  type SlotConfig,
} from "../../lib/backends";

// The A/B/C solver slots: each slot's backend + per-backend options, the
// derived view of the active one, and the three mutators the gear modal
// drives (#642 seam 5b-3).
//
// Seeded from the SERVED roster (#628), which is why this hook has no effects
// any more: the session only mounts once /capabilities has answered, so the
// seeds resolve against a real roster on the very first render. The former
// "remap a PyNEC slot when the server reports no pynec-accel" effect (#429) is
// subsumed — a server without pynec-accel simply doesn't serve the entry, and
// slotFromSeed falls back to the roster's first backend.
//
// backendTouchedRef comes back raw: the two "the user picked a backend by
// hand" call sites stay in the component's JSX and set it directly.
export function useSolverSlots({ roster }: { roster: BackendRoster }) {
  // Solver slots A / B / C — each one holds its own backend + options so
  // the user can switch between configured solvers with a single click
  // and tune each one independently from its gear menu.
  const [activeSlot, setActiveSlot] = useState<Slot>("A");
  const [slots, setSlots] = useState<Record<Slot, SlotConfig>>(() =>
    defaultSlots(roster),
  );
  // Set once the user picks a backend by hand; after that we stop auto-seeding
  // the per-antenna recommended solver so their choice sticks.
  const backendTouchedRef = useRef(false);
  const [gearOpen, setGearOpen] = useState<Slot | null>(null);
  const activeConfig = slots[activeSlot];
  const backend = activeConfig.backend;
  const currentOpts = activeConfig.opts;
  const nPerWire = currentOpts.nPerWire;
  const wireRadius = currentOpts.wireRadius;
  // Stable hash of the active slot's config so useEffect can depend on it.
  // The backend contributes its name only — the roster entry is server data
  // that never changes within a session, so hashing it would just be noise.
  const backendOptsKey = JSON.stringify([backend.name, currentOpts]);
  function updateSlotOpts(slot: Slot, patch: Partial<BackendOpts>) {
    setSlots((prev) => ({
      ...prev,
      [slot]: { ...prev[slot], opts: { ...prev[slot].opts, ...patch } },
    }));
  }
  function setSlotBackend(slot: Slot, newBackend: BackendEntry) {
    // Preserve segments-per-wire and wire-radius across the swap so the
    // user keeps their geometry-sizing choices when comparing models;
    // model-specific kwargs revert to that backend's defaults.
    setSlots((prev) => {
      const prevOpts = prev[slot].opts;
      return {
        ...prev,
        [slot]: {
          backend: newBackend,
          opts: {
            ...defaultOptsFor(newBackend),
            nPerWire: prevOpts.nPerWire,
            wireRadius: prevOpts.wireRadius,
          },
        },
      };
    });
  }
  function resetSlot(slot: Slot) {
    setSlots((prev) => ({ ...prev, [slot]: defaultSlots(roster)[slot] }));
  }

  return {
    activeSlot,
    setActiveSlot,
    slots,
    backendTouchedRef,
    gearOpen,
    setGearOpen,
    backend,
    currentOpts,
    nPerWire,
    wireRadius,
    backendOptsKey,
    updateSlotOpts,
    setSlotBackend,
    resetSlot,
  };
}
