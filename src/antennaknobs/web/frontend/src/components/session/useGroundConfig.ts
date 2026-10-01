import { useState } from "react";
import {
  activeGroundSlot,
  designSlotId,
  editActive,
  editSlot,
  groundRequest,
  withDesignGround,
  type GroundEdit,
  type GroundSlot,
  type GroundSlotId,
  type GroundSlotsState,
} from "../../lib/groundSlots";
import { type BackendEntry } from "../../lib/backends";
import {
  defaultSoil,
  groundSummaryLabel,
  soilSummaryLabel,
  type FiniteGroundMethod,
  type GroundModel,
  type GroundType,
  type SoilParams,
  type SoilPresetSchema,
  type SoilRanges,
  type TerrainParams,
} from "../../lib/ground";
import { BUILTIN_GROUND_SLOTS, type GroundSlotDefaults } from "../../lib/settings";

/** A slot's starting state from its served defaults. The terrain preset
 *  falls back to the panel's first preset, which a save leaves out (#1497). */
function slotFromDefaults(defaults: GroundSlotDefaults): GroundSlot {
  return {
    id: defaults.id,
    enabled: defaults.enabled,
    type: defaults.type,
    method: defaults.method,
    soil: defaults.soil,
    terrainPreset: defaults.terrain_preset ?? "levee",
    terrainParams: {},
    fromDesign: false,
  };
}

// The ground/terrain selection and everything derived from it: the wire
// `ground_model` value the server protocol takes, the terrain change-detector
// string the solve and norm-check effects depend on, and the one-line summary
// the tab hover shows (#642 seam 5b-3), all of it for the ACTIVE ground slot
// (AK#1794). No effects here — the cluster is state plus derivations, so the
// component's global effect order is untouched.
export function useGroundConfig({
  backend,
  soilRanges,
  soilPresets,
  slots: slotDefaults = BUILTIN_GROUND_SLOTS,
}: {
  backend: BackendEntry;
  /** Served bounds+defaults, null on a server predating #1173. */
  soilRanges?: SoilRanges | null;
  soilPresets?: SoilPresetSchema[];
  /** Where each ground slot starts (AK#1794, settings.toml's [grounds.X],
   *  slot X also [ground]); the stock set if omitted. */
  slots?: GroundSlotDefaults[];
}) {
  // The ground slots (AK#1794), the A/B/C solver slots' twin: each holds a
  // whole ground, the active one is what every solve and chart reads, and
  // the ground panel edits the active one. Slot X starts active, so a
  // session that never touches the slots is the single ground it always was.
  //
  // What a slot holds, field by field (the notes the single ground carried):
  //  - enabled: the ground plane at z = 0, ON by default: this is an HF
  //    wire-antenna workbench, and the over-ground picture (takeoff angle,
  //    ground-lobed elevation pattern, shifted Z) is the decision-relevant
  //    one — free space is the idealization you opt into.
  //  - type: one selector describing the GROUND (finite / PEC / terrain);
  //    every backend solves it as best it can (see the GroundType note).
  //  - method: the finite-ground method; hidden (and inert) on backends with
  //    a single finite model, but kept so it survives backend flips during
  //    engine comparison. "fast" is the default — Sommerfeld is opt-in.
  //  - terrainPreset / terrainParams: one flat params object for both
  //    presets so values survive preset flips.
  const [state, setState] = useState<GroundSlotsState>(() => ({
    slots: slotDefaults.map(slotFromDefaults),
    active: slotDefaults[0]?.id ?? BUILTIN_GROUND_SLOTS[0].id,
  }));

  // Soil constants for the finite models (issue #1173). Seeded from the
  // SERVED defaults once /capabilities resolves — never from a literal here,
  // which would be a second copy of a number the server already owns and
  // clamps. Null until then (and forever on a server predating #1173), and
  // the panel renders no soil controls while it is null.
  //
  // Seeded DURING RENDER, not in an effect — the same #768 idiom as
  // fields.tsx's useNumericDraft, and what react-hooks/set-state-in-effect
  // requires. The effect spelling would paint one frame with no soil
  // controls and correct it on a second pass; this re-renders before
  // committing to the DOM, so the un-seeded state is never shown.
  //
  // Seeds each slot ONCE, on its null→value transition only: re-seeding
  // whenever the served default changed would stomp a soil the user had
  // dialled. A settings.toml soil (AK#1492) seeds instead of the served
  // default. The served default itself is untouched, because the request
  // path omits a default-valued soil and the server then solves its own
  // default.
  const servedDefault = defaultSoil(soilRanges ?? null);
  if (servedDefault !== null && state.slots.some((s) => s.soil === null)) {
    setState((st) => ({
      ...st,
      slots: st.slots.map((s) => (s.soil === null ? { ...s, soil: servedDefault } : s)),
    }));
  }

  const active = activeGroundSlot(state);
  const groundEnabled = active.enabled;
  const groundType = active.type;
  const finiteGroundMethod = active.method;
  const terrainPreset = active.terrainPreset;
  const terrainParams = active.terrainParams;
  const soil = active.soil;

  // The ground panel's setters, each an edit to the ACTIVE slot.
  const edit = (e: GroundEdit | ((slot: GroundSlot) => GroundEdit)) =>
    setState((st) => editActive(st, e));
  const setGroundEnabled = (v: boolean) => edit({ enabled: v });
  const setGroundType = (v: GroundType) => edit({ type: v });
  const setFiniteGroundMethod = (v: FiniteGroundMethod) => edit({ method: v });
  const setTerrainPreset = (v: string) => edit({ terrainPreset: v });
  const setTerrainParams = (fn: (p: TerrainParams) => TerrainParams) =>
    edit((slot) => ({ terrainParams: fn(slot.terrainParams) }));
  const setSoil = (v: SoilParams) => edit({ soil: v });
  // Slot `id`'s settings, as its ⚙ edits them (AK#1801): the values the
  // ground panel shows and its setters, each an edit to THAT slot whether or
  // not it is the active one. Null for an id no slot has.
  const slotSettings = (id: GroundSlotId) => {
    const slot = state.slots.find((s) => s.id === id);
    if (!slot) return null;
    const editIt = (e: GroundEdit | ((s: GroundSlot) => GroundEdit)) =>
      setState((st) => editSlot(st, id, e));
    return {
      slot,
      setGroundEnabled: (v: boolean) => editIt({ enabled: v }),
      setGroundType: (v: GroundType) => editIt({ type: v }),
      setFiniteGroundMethod: (v: FiniteGroundMethod) => editIt({ method: v }),
      setTerrainPreset: (v: string) => editIt({ terrainPreset: v }),
      setTerrainParams: (fn: (p: TerrainParams) => TerrainParams) =>
        editIt((s) => ({ terrainParams: fn(s.terrainParams) })),
      setSoil: (v: SoilParams) => editIt({ soil: v }),
    };
  };
  const setActiveGroundSlot = (id: GroundSlotId) =>
    setState((st) => (st.slots.some((s) => s.id === id) ? { ...st, active: id } : st));

  // A design load (DesignSession's design resets): see withDesignGround. The
  // session default is slot X as the settings file starts it.
  function applyDesignGround(own: GroundEdit | null) {
    const start = slotFromDefaults(slotDefaults[0] ?? BUILTIN_GROUND_SLOTS[0]);
    const sessionDefault = { ...start, soil: start.soil ?? servedDefault };
    setState((st) => withDesignGround(st, own, sessionDefault));
  }

  // Wire value derived for the server protocol (see GroundModel). A
  // terrain selection quietly degrades to the finite method on any future
  // backend without terrain support (all current ground-capable backends
  // have it — PyNEC via the #553 hybrid).
  const activeRequest = groundRequest(active, backend, servedDefault);
  const groundModel: GroundModel = activeRequest.model;

  // Solve-effect dep for the terrain knobs: only bites while terrain is
  // the active model, so parked levee state never re-solves a flat-ground
  // setup (and vice versa).
  const terrainKey =
    groundModel === "terrain"
      ? JSON.stringify([terrainPreset, terrainParams])
      : "";

  // Whether the finite models are the active ones. pec and terrain carry no
  // soil: terrain media are fixed (the #1173 non-goal) and PEC has none. The
  // MININEC-type ground (AK#1655) does: its pattern reflects off it.
  const soilApplies =
    groundModel === "fast" ||
    groundModel === "sommerfeld" ||
    groundModel === "mininec";

  // What rides on the request, or undefined. Omitted when it equals the
  // served default so that a default-soil request is byte-identical to a
  // pre-#1173 one: same cache key, same curve, nothing shipped changes.
  const soilForRequest: SoilParams | undefined = activeRequest.soil;

  // Solve-effect dep, same shape as terrainKey: only bites while a finite
  // model is active, so a parked soil never re-solves a PEC setup. Keyed off
  // what is SENT, so dialling back to the default settles on the same key
  // the session started with rather than a third distinct value.
  const soilKey = soilForRequest
    ? JSON.stringify([soilForRequest.eps_r, soilForRequest.sigma])
    : "";

  const soilSummary = soilApplies
    ? soilSummaryLabel(soil, soilPresets ?? [])
    : "";

  // One-line tab-hover summary: design · solver N=segs · ground model.
  // Every backend honours the selected method (momwire >= 0.8.0), so the
  // wording is uniform; "free space" when ground is off or unsupported.
  const groundSummary = groundSummaryLabel(
    groundEnabled,
    backend,
    groundModel,
    terrainPreset,
  );

  // Any slot's ground on any engine, for an analysis chart's cell (AK#1757
  // step 5 unit 4): the same derivation as the active one above. An id no
  // slot has reads as the active slot.
  const groundRequestFor = (id: GroundSlotId, b: BackendEntry) =>
    groundRequest(state.slots.find((s) => s.id === id) ?? active, b, servedDefault);

  return {
    groundSlots: state.slots,
    groundRequestFor,
    groundSlotSettings: slotSettings,
    servedDefaultSoil: servedDefault,
    activeGroundSlot: active.id,
    designGroundSlot: designSlotId(state),
    setActiveGroundSlot,
    applyDesignGround,
    groundEnabled,
    setGroundEnabled,
    groundType,
    setGroundType,
    finiteGroundMethod,
    setFiniteGroundMethod,
    terrainPreset,
    setTerrainPreset,
    terrainParams,
    setTerrainParams,
    groundModel,
    terrainKey,
    groundSummary,
    soil,
    setSoil,
    soilApplies,
    soilForRequest,
    soilKey,
    soilSummary,
  };
}
