import { useRef, useState } from "react";
import {
  type ModelOptionSpecs,
  type ServedSlotSeed,
  defaultOptsFor,
  defaultSlots,
  densityAdoptionNote,
  perDegreeNPerWire,
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
export function useSolverSlots({
  roster,
  specs,
  seeds,
}: {
  roster: BackendRoster;
  /** The served knob catalogue — slot defaults come from it (#1006 G2-6). */
  specs: ModelOptionSpecs;
  /** The served A/B/C seeds (#1006 G2-6). */
  seeds: ServedSlotSeed[];
}) {
  // Solver slots A / B / C — each one holds its own backend + options so
  // the user can switch between configured solvers with a single click
  // and tune each one independently from its gear menu.
  const [activeSlot, setActiveSlot] = useState<Slot>("A");
  const [slots, setSlots] = useState<Record<Slot, SlotConfig>>(() =>
    defaultSlots(roster, specs, seeds),
  );
  // Set once the user picks a backend by hand; after that we stop auto-seeding
  // the per-antenna recommended solver so their choice sticks.
  const backendTouchedRef = useRef(false);
  // Per slot: the sentence saying this slot's segments/wire came from the
  // engine and not from the user (#1543), or null. State rather than a field
  // on SlotConfig because it is about the last EDIT, not about the solver —
  // nothing that reads a slot to build a request or save a settings file has
  // any use for it.
  const [densityNotes, setDensityNotes] = useState<Record<Slot, string | null>>({
    A: null,
    B: null,
    C: null,
  });
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
    const cfg = slots[slot];
    // A degree change is a BASIS change, so the slot adopts the new basis's
    // density exactly as an engine swap does (#1543). Only where the server
    // serves a per-degree row: on a backend that merely ACCEPTS a degree,
    // falling back to its flat default would discard a hand-set N. A patch
    // carrying `nPerWire` too is the user's own edit and wins outright.
    const adopted =
      patch.model !== undefined &&
      patch.model.degree !== cfg.opts.model.degree &&
      patch.nPerWire === undefined
        ? perDegreeNPerWire(cfg.backend, patch.model.degree)
        : null;
    setSlots((prev) => {
      const p = prev[slot];
      const opts = { ...p.opts, ...patch };
      if (adopted !== null) opts.nPerWire = adopted;
      return { ...prev, [slot]: { ...p, opts } };
    });
    // Touching the knob clears the note: it exists to explain a value the
    // user did not choose, and once they have chosen one it is a lie.
    if (patch.nPerWire !== undefined) {
      setDensityNotes((notes) => ({ ...notes, [slot]: null }));
    } else if (adopted !== null) {
      const shown = { ...cfg.opts, ...patch, nPerWire: adopted };
      setDensityNotes((notes) => ({
        ...notes,
        [slot]: densityAdoptionNote(cfg.backend, shown),
      }));
    }
  }
  function setSlotBackend(slot: Slot, newBackend: BackendEntry) {
    // The slot ADOPTS the new engine's density, always, with no memory of a
    // hand-set value (#1543): "it does what the roster says, every time". The
    // segments/wire a solver needs to be converged is a property of its
    // basis, so carrying the old engine's number across the swap ran the new
    // engine at a mesh nothing had measured for it. Wire radius is preserved
    // — that is geometry, and it means the same thing on every solver.
    setSlots((prev) => {
      const prevOpts = prev[slot].opts;
      return {
        ...prev,
        [slot]: {
          backend: newBackend,
          opts: {
            ...defaultOptsFor(newBackend, specs),
            wireRadius: prevOpts.wireRadius,
          },
        },
      };
    });
    const adopted = defaultOptsFor(newBackend, specs);
    setDensityNotes((notes) => ({
      ...notes,
      [slot]: densityAdoptionNote(newBackend, adopted),
    }));
  }
  function resetSlot(slot: Slot) {
    setSlots((prev) => ({ ...prev, [slot]: defaultSlots(roster, specs, seeds)[slot] }));
    // Reset returns the slot to its SEED, which is not an adoption — the note
    // would be naming a number the seed chose, not the engine.
    setDensityNotes((notes) => ({ ...notes, [slot]: null }));
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
    densityNotes,
    backendOptsKey,
    updateSlotOpts,
    setSlotBackend,
    resetSlot,
  };
}
