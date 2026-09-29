// Ground slots (AK#1794): the A/B/C solver slots' twin. Each slot holds a
// whole ground (on/off, type, finite method, soil, terrain preset and knobs),
// one of them is active, and every solve and chart reads the active one. The
// pure state steps live here; useGroundConfig holds the state.
import {
  soilSummaryLabel,
  type FiniteGroundMethod,
  type GroundType,
  type SoilParams,
  type SoilPresetSchema,
  type TerrainParams,
} from "./ground";

export type GroundSlotId = string;

export type GroundSlot = {
  /** "1", "2", ...: the key of the settings file's [grounds.N] table. */
  id: GroundSlotId;
  enabled: boolean;
  type: GroundType;
  method: FiniteGroundMethod;
  /** Null only until the served soil default is known (useGroundConfig). */
  soil: SoilParams | null;
  terrainPreset: string;
  terrainParams: TerrainParams;
  /** The slot holds a design's own ground, untouched since that design
   *  loaded; a design without one then puts the session default back. */
  fromDesign: boolean;
};

export type GroundSlotsState = { slots: GroundSlot[]; active: GroundSlotId };

/** The fields of a slot the ground panel edits. */
export type GroundEdit = Partial<
  Pick<GroundSlot, "enabled" | "type" | "method" | "soil" | "terrainPreset" | "terrainParams">
>;

/** The ground a design brings with it, or null: a buried design's Sommerfeld
 *  requirement, then a file design's own GE/GN/GD (AK#1432, AK#1655) on top,
 *  in the order the session always applied them. */
export function designGround(ex: {
  ground_requirement?: string | null;
  ground_seed?: string | null;
  ground_medium?: { eps_r: number; sigma: number } | null;
}): GroundEdit | null {
  let own: GroundEdit | null = null;
  if (ex.ground_requirement === "sommerfeld") {
    own = { enabled: true, type: "finite", method: "sommerfeld" };
  }
  const seed = ex.ground_seed ?? null;
  if (!seed) return own;
  own = { ...own };
  if (seed === "free") return { ...own, enabled: false };
  if (seed === "pec") return { ...own, enabled: true, type: "pec" };
  own = {
    ...own,
    enabled: true,
    type: "finite",
    method: seed === "fast" ? "fast" : seed === "mininec" ? "mininec" : "sommerfeld",
  };
  const m = ex.ground_medium ?? null;
  return m ? { ...own, soil: { eps_r: m.eps_r, sigma: m.sigma } } : own;
}

/** The design slot: the first, "1" in the stock set. */
export function designSlotId(state: GroundSlotsState): GroundSlotId {
  return state.slots[0].id;
}

/** A design load. A design with its own ground puts it in the design slot
 *  over what that slot held (as the single ground took it before slots) and
 *  makes that slot active, so the design opens on the ground its file or its
 *  buried wires need. A design without one leaves the active slot alone and
 *  puts the session default back in the design slot only if the slot still
 *  holds a previous design's ground untouched; a hand edit stays. */
export function withDesignGround(
  state: GroundSlotsState,
  own: GroundEdit | null,
  sessionDefault: GroundSlot,
): GroundSlotsState {
  const [first, ...rest] = state.slots;
  if (own) {
    return { slots: [{ ...first, ...own, fromDesign: true }, ...rest], active: first.id };
  }
  if (!first.fromDesign) return state;
  return { ...state, slots: [{ ...sessionDefault, id: first.id, fromDesign: false }, ...rest] };
}

/** An edit to the active slot, from the ground panel. */
export function editActive(
  state: GroundSlotsState,
  edit: GroundEdit | ((slot: GroundSlot) => GroundEdit),
): GroundSlotsState {
  return {
    ...state,
    slots: state.slots.map((s) =>
      s.id === state.active
        ? { ...s, ...(typeof edit === "function" ? edit(s) : edit), fromDesign: false }
        : s,
    ),
  };
}

export function activeGroundSlot(state: GroundSlotsState): GroundSlot {
  return state.slots.find((s) => s.id === state.active) ?? state.slots[0];
}

const METHOD_LABEL: Record<FiniteGroundMethod, string> = {
  fast: "refl-coef",
  sommerfeld: "Sommerfeld",
  mininec: "MININEC",
};

/** A slot's tab label: what ground it holds, whatever the active solver does
 *  with it (the panel says when a solver ignores the ground). */
export function groundSlotLabel(slot: GroundSlot, soilPresets: SoilPresetSchema[]): string {
  if (!slot.enabled) return "free space";
  if (slot.type === "pec") return "PEC";
  if (slot.type === "terrain") return `terrain · ${slot.terrainPreset}`;
  const soil = soilSummaryLabel(slot.soil, soilPresets);
  return soil ? `${METHOD_LABEL[slot.method]} · ${soil}` : METHOD_LABEL[slot.method];
}
