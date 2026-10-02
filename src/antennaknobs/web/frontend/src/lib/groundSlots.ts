// Ground slots (AK#1794): the A/B/C solver slots' twin. Each slot holds a
// whole ground (on/off, type, finite method, soil, terrain preset and knobs),
// one of them is active, and every solve and chart reads the active one. The
// pure state steps live here; useGroundConfig holds the state.
import { backendDisplayLabel, type BackendEntry, type BackendOpts } from "./backends";
import {
  resolveGroundModel,
  soilSummaryLabel,
  type FiniteGroundMethod,
  type GroundModel,
  type GroundType,
  type SoilParams,
  type SoilPresetSchema,
  type TerrainParams,
} from "./ground";
import { nextSlotId, slotBefore, slotRemovalRefusal, type SlotFamily } from "./slotFamily";

export type GroundSlotId = string;

/** The ground slots' names, in order (AK#1801): letters, so they read as
 *  their own family beside the A/B/C solver slots. Chunks of three, each
 *  read forwards, stepping back through the alphabet: X Y Z, then U V W,
 *  then R S T, ... down to F G H; the chunk after that would reach the
 *  solver slots' A–E. The twin of settings.py's GROUND_SLOT_IDS, pinned by
 *  tests/test_ground_slots_xyz_1801.py. */
export const GROUND_SLOT_IDS: readonly GroundSlotId[] = [..."XYZUVWRSTOPQLMNIJKFGH"];

/** The ground slots as a slot family (AK#1801): X, Y and Z are the stock
 *  set (settings.py's STOCK_GROUNDS), and the strip's + adds U, V, W, ... */
export const GROUND_SLOTS: SlotFamily = { ids: GROUND_SLOT_IDS, stock: 3, noun: "ground" };

export type GroundSlot = {
  /** "X", "Y", "Z", ...: the key of the settings file's [grounds.X] table. */
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

/** The design slot: the first, "X" in the stock set. */
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

/** An edit to slot `id`, from that slot's ⚙ settings (AK#1801): the slot
 *  being edited need not be the active one, as the solver gear edits a named
 *  solver slot. An edit makes the slot the user's own (`fromDesign` off). */
export function editSlot(
  state: GroundSlotsState,
  id: GroundSlotId,
  edit: GroundEdit | ((slot: GroundSlot) => GroundEdit),
): GroundSlotsState {
  return {
    ...state,
    slots: state.slots.map((s) =>
      s.id === id
        ? { ...s, ...(typeof edit === "function" ? edit(s) : edit), fromDesign: false }
        : s,
    ),
  };
}

/** An edit to the active slot. */
export function editActive(
  state: GroundSlotsState,
  edit: GroundEdit | ((slot: GroundSlot) => GroundEdit),
): GroundSlotsState {
  return editSlot(state, state.active, edit);
}

/** The strip's + (AK#1801): the next slot, a copy of the ACTIVE one (the
 *  natural start for "the same ground, one change"), made active. A copy of
 *  a design's ground is the user's own: a later design leaves it alone. */
export function addGroundSlot(state: GroundSlotsState): GroundSlotsState {
  const id = nextSlotId(GROUND_SLOTS, state.slots.map((s) => s.id));
  if (id === null) return state;
  const from = activeGroundSlot(state);
  const copy: GroundSlot = {
    ...from,
    id,
    soil: from.soil ? { ...from.soil } : null,
    terrainParams: { ...from.terrainParams },
    fromDesign: false,
  };
  return { slots: [...state.slots, copy], active: id };
}

/** Why ground slot `id` cannot be removed, or null when it can. */
export function groundSlotRemovalRefusal(state: GroundSlotsState, id: GroundSlotId): string | null {
  return slotRemovalRefusal(GROUND_SLOTS, state.slots.map((s) => s.id), id);
}

/** A slot's remove (AK#1801): the last slot past the stock set only. When it
 *  was the active one, the slot before it becomes active. */
export function removeGroundSlot(state: GroundSlotsState, id: GroundSlotId): GroundSlotsState {
  if (groundSlotRemovalRefusal(state, id) !== null) return state;
  return {
    slots: state.slots.filter((s) => s.id !== id),
    active: state.active === id ? slotBefore(GROUND_SLOTS, id) : state.active,
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

// `ground_model_applied`'s words for each method as the request spells it,
// and the display words for what a solve can run instead (AK#1854).
const REQUESTED_APPLIED: Record<FiniteGroundMethod, string> = {
  fast: "refl-coef",
  sommerfeld: "sommerfeld",
  mininec: "mininec",
};
const APPLIED_LABEL: Record<string, string> = {
  sommerfeld: "Sommerfeld",
  "refl-coef": "refl-coef",
  mininec: "MININEC",
  "pec-image": "PEC image",
  free: "free space",
};

/** Why `backend` refuses `slot`'s ground, in the server's words, else null
 *  (AK#1856): NEC-5 on a refl-coef slot. Read off the roster's served
 *  `ground_refusals`, keyed by the `ground_model` the request would carry,
 *  so it follows the solve's own rule; a server predating it answers null
 *  and the solve's own error says so instead. */
export function groundRefusal(slot: GroundSlot, backend: BackendEntry): string | null {
  if (!slot.enabled) return null;
  return backend.ground_refusals?.[resolveGroundModel(slot.type, backend, slot.method)] ?? null;
}

/** The way out of a refused pair (AK#1856): the first slot holding a finite
 *  Sommerfeld ground that `backend` does not refuse, else null (the caller
 *  then sets the active slot's method to Sommerfeld). */
export function sommerfeldSlotFor(
  slots: readonly GroundSlot[],
  backend: BackendEntry,
): GroundSlotId | null {
  const s = slots.find(
    (g) =>
      g.enabled &&
      g.type === "finite" &&
      g.method === "sommerfeld" &&
      groundRefusal(g, backend) === null,
  );
  return s ? s.id : null;
}

/** What `backend` actually solves for `slot` when that differs from what the
 *  slot holds, in display words (a momwire solver without the refl-coef
 *  model: "PEC image"), else null. Read off the roster's served
 *  `ground_applied` (AK#1854), so it follows the solve's own rule; a server
 *  predating it, or a method the backend refuses, answers null. */
export function appliedGroundChange(slot: GroundSlot, backend: BackendEntry): string | null {
  if (!slot.enabled || slot.type !== "finite") return null;
  const applied = backend.ground_applied?.[slot.method];
  if (!applied || applied === REQUESTED_APPLIED[slot.method]) return null;
  return APPLIED_LABEL[applied] ?? applied;
}

/** The mark a refused ground carries on its tab and in the pair line. */
export const REFUSED_MARK = "⊘";

/** A slot's tab label: what ground it holds and, under the active solver,
 *  what that solver makes of it: refused (AK#1856), "refl-coef ⊘ · average"
 *  under NEC-5, which has no reflection-coefficient model; or run as
 *  something else (AK#1854), "refl-coef → PEC image" under a momwire solver
 *  without it. Without `backend` it is what the slot holds. */
export function groundSlotLabel(
  slot: GroundSlot,
  soilPresets: SoilPresetSchema[],
  backend?: BackendEntry,
): string {
  if (!slot.enabled) return "free space";
  if (slot.type === "pec") return "PEC";
  if (slot.type === "terrain") return `terrain · ${slot.terrainPreset}`;
  const soil = soilSummaryLabel(slot.soil, soilPresets);
  const refused = backend ? groundRefusal(slot, backend) : null;
  const changed = backend && !refused ? appliedGroundChange(slot, backend) : null;
  const method = refused
    ? `${METHOD_LABEL[slot.method]} ${REFUSED_MARK}`
    : changed
      ? `${METHOD_LABEL[slot.method]} → ${changed}`
      : METHOD_LABEL[slot.method];
  return soil ? `${method} · ${soil}` : method;
}

/** A chart's note when one ground slot is solved as DIFFERENT ground models
 *  across its curves' engines (AK#1854), else null: an engine cross on a
 *  refl-coef slot with a momwire solver that lacks the model draws that
 *  curve over the PEC image beside the others over refl-coef, and without
 *  this the legend names one ground for both. A pair the backend refuses
 *  (AK#1856) draws nothing and is the legend's refused cell, not this. `cells`
 *  are the curves drawn, by solver slot and ground slot. */
export function mixedGroundNote(
  cells: readonly { slot: string | null; ground: string | null }[],
  backendOf: (slot: string) => BackendEntry | undefined,
  groundOf: (id: string) => GroundSlot | undefined,
): string | null {
  const byGround = new Map<string, Map<string, string[]>>();
  for (const c of cells) {
    if (c.slot === null || c.ground === null) continue;
    const g = groundOf(c.ground);
    const b = backendOf(c.slot);
    if (!g || !b || !g.enabled || g.type !== "finite") continue;
    if (groundRefusal(g, b) !== null) continue;
    const applied = appliedGroundChange(g, b) ?? METHOD_LABEL[g.method];
    const models = byGround.get(g.id) ?? new Map<string, string[]>();
    const engines = models.get(applied) ?? [];
    if (!engines.includes(b.label)) engines.push(b.label);
    models.set(applied, engines);
    byGround.set(g.id, models);
  }
  const lines = [...byGround]
    .filter(([, models]) => models.size > 1)
    .map(
      ([id, models]) =>
        `Ground ${id} is solved as ` +
        [...models].map(([m, engines]) => `${m} on ${engines.join(", ")}`).join(" but as ") +
        ": those curves differ in ground model, not only in engine.",
    );
  return lines.length > 0 ? lines.join(" ") : null;
}

/** The one line naming the pair every solve and chart runs on (AK#1854):
 *  the active solver slot and the active ground slot, which are chosen
 *  independently — the two strips are not paired by position. A pair the
 *  solver refuses (AK#1856) reads "refused:", since nothing solves on it. */
export function solvePairLabel(
  solverSlot: string,
  backend: BackendEntry,
  opts: BackendOpts,
  ground: GroundSlot,
  soilPresets: SoilPresetSchema[],
): string {
  const verb = groundRefusal(ground, backend) ? "refused:" : "solving on";
  return (
    `${verb} ${solverSlot} (${backendDisplayLabel(backend, opts)}) × ` +
    `${ground.id} (${groundSlotLabel(ground, soilPresets, backend)})`
  );
}

/** What a slot's ground puts on a solve request, on `backend`: the wire
 *  `ground_model` (resolveGroundModel), and the soil only where a finite
 *  model applies AND it differs from the served default, so a default-soil
 *  request stays byte-identical to a pre-#1173 one. The session's request
 *  for its active slot and an analysis chart's cell for any slot (AK#1757
 *  step 5 unit 4) both read it, so the two cannot drift. */
export type GroundRequest = {
  enabled: boolean;
  model: GroundModel;
  terrainPreset: string;
  terrainParams: TerrainParams;
  soil: SoilParams | undefined;
};

export function groundRequest(
  slot: GroundSlot,
  backend: BackendEntry,
  servedDefault: SoilParams | null,
): GroundRequest {
  const model = resolveGroundModel(slot.type, backend, slot.method);
  const soilApplies = model === "fast" || model === "sommerfeld" || model === "mininec";
  const soil =
    soilApplies &&
    slot.soil &&
    servedDefault &&
    (slot.soil.eps_r !== servedDefault.eps_r || slot.soil.sigma !== servedDefault.sigma)
      ? slot.soil
      : undefined;
  return {
    enabled: slot.enabled,
    model,
    terrainPreset: slot.terrainPreset,
    terrainParams: slot.terrainParams,
    soil,
  };
}
