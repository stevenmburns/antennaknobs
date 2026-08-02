import { useEffect, useRef, useState } from "react";
import {
  DEFAULT_BACKEND_OPTS,
  DEFAULT_SLOTS,
  resolveSlotConfig,
  type Backend,
  type BackendOptsMap,
  type Slot,
  type SlotConfig,
} from "../../lib/backends";

// The A/B/C solver slots: each slot's backend + per-backend options, the
// derived view of the active one, the three mutators the gear modal drives,
// and the effect that remaps a PyNEC slot when the server reports no
// pynec-accel (#642 seam 5b-3). The cluster moves whole, so its one literal
// dep array and its global effect position are unchanged.
//
// backendTouchedRef comes back raw: the two "the user picked a backend by
// hand" call sites stay in the component's JSX and set it directly.
export function useSolverSlots({ havePynec }: { havePynec: boolean }) {
  // Solver slots A / B / C — each one holds its own backend + options so
  // the user can switch between configured solvers with a single click
  // and tune each one independently from its gear menu.
  const [activeSlot, setActiveSlot] = useState<Slot>("A");
  const [slots, setSlots] = useState<Record<Slot, SlotConfig>>(DEFAULT_SLOTS);
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
  const backendOptsKey = JSON.stringify(activeConfig);
  function updateSlotOpts(slot: Slot, patch: Partial<BackendOptsMap[Backend]>) {
    setSlots((prev) => ({
      ...prev,
      [slot]: {
        ...prev[slot],
        opts: { ...prev[slot].opts, ...patch } as BackendOptsMap[Backend],
      },
    }));
  }
  function setSlotBackend(slot: Slot, newBackend: Backend) {
    // Preserve segments-per-wire and wire-radius across the swap so the
    // user keeps their geometry-sizing choices when comparing models;
    // model-specific kwargs revert to that backend's defaults.
    setSlots((prev) => {
      const prevOpts = prev[slot].opts;
      const defaults = DEFAULT_BACKEND_OPTS[newBackend];
      return {
        ...prev,
        [slot]: {
          backend: newBackend,
          opts: {
            ...defaults,
            nPerWire: prevOpts.nPerWire,
            wireRadius: prevOpts.wireRadius,
          } as BackendOptsMap[Backend],
        },
      };
    });
  }
  function resetSlot(slot: Slot) {
    setSlots((prev) => ({
      ...prev,
      [slot]: resolveSlotConfig(DEFAULT_SLOTS[slot], havePynec),
    }));
  }
  // When the server reports no pynec-accel (#429), remap any slot still on
  // PyNEC — the default slot C, or a saved/URL slot — to the fallback backend,
  // so the panel never holds a backend the picker no longer offers (which the
  // /ws solve would silently run as momwire).
  useEffect(() => {
    if (havePynec) return;
    setSlots((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const s of Object.keys(prev) as Slot[]) {
        const resolved = resolveSlotConfig(prev[s], havePynec);
        if (resolved !== prev[s]) {
          next[s] = resolved;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [havePynec]);

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
