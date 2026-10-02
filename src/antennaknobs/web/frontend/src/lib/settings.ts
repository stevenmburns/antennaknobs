// Startup settings (AK#1492): where the workbench starts, served on
// /capabilities as `ui_defaults` from the server's settings.toml. The server
// owns these defaults (antennaknobs/web/settings.py); the fallback below only
// covers a payload without `ui_defaults`, and
// tests/test_settings_toml_1492.py pins it to the server's table.
import type {
  FiniteGroundMethod,
  GroundType,
  SoilParams,
} from "./ground";
import type { Slot } from "./backends";
import { groundSlotId } from "./groundSlots";
import type { Projection } from "./view";

export type SwitchKey =
  | "live"
  | "freq_sweep"
  | "convergence_sweep"
  | "pattern_renorm"
  | "refine"
  | "heatmap_currents"
  | "current_waveforms"
  | "wire_labels"
  | "feed_labels";

export const BUILTIN_SWITCHES: Record<SwitchKey, boolean> = {
  live: true,
  freq_sweep: true,
  convergence_sweep: false,
  pattern_renorm: true,
  refine: true,
  heatmap_currents: true,
  current_waveforms: false,
  wire_labels: false,
  feed_labels: true,
};

// The Antenna view's orientation on a design load (AK#1737). "auto" is the
// per-design guess the server sends as `default_view`; any other value wins
// over that guess at EVERY design load. The server's ORIENTATIONS table
// (antennaknobs/web/settings.py) is the one list; the save writes nothing
// for "auto".
export type Orientation = "auto" | "top" | "front" | "side" | "iso";

export const ORIENTATIONS: Orientation[] = ["auto", "top", "front", "side", "iso"];

export const BUILTIN_ORIENTATION: Orientation = "auto";

// The camera each fixed orientation means (lib/view.ts PROJECTIONS: Top (xy),
// Front (xz), Side (yz), Iso).
export const ORIENTATION_PROJECTION: Record<
  Exclude<Orientation, "auto">,
  Projection
> = {
  top: "xy",
  front: "xz",
  side: "yz",
  iso: "iso",
};

// Does picking an analysis start it (AC6LA, QRZ 1003328 #179)? Per kind of
// analysis (lib/analysisChart.ts runOnPickKind; a study is the kind of
// analysis it is), from settings.toml's [workbench.run_on_pick]. The server's
// RUN_ON_PICK (antennaknobs/web/settings.py) is the one table, pinned here by
// tests/test_settings_run_on_pick.py. A frequency sweep and a pattern take
// seconds and start at once; the rest take minutes, so a pick only selects
// them and the chart waits for Run. `map` is valid before the workbench draws
// a map (sweep-framework step 5).
export type RunOnPickKind = "frequency" | "pattern" | "knob" | "held" | "convergence" | "map";

export const BUILTIN_RUN_ON_PICK: Record<RunOnPickKind, boolean> = {
  frequency: true,
  pattern: true,
  knob: false,
  held: false,
  convergence: false,
  map: false,
};

export const RUN_ON_PICK_KINDS = Object.keys(BUILTIN_RUN_ON_PICK) as RunOnPickKind[];

export type GroundDefaults = {
  enabled: boolean;
  type: GroundType;
  method: FiniteGroundMethod;
  /** null: start at the served soil default. */
  soil: SoilParams | null;
  /** null: start at the terrain panel's own first preset. */
  terrain_preset: string | null;
};

// Sommerfeld since AK#1856 (the server's GROUND_BUILTIN, and the CLI's
// default ground too).
export const BUILTIN_GROUND: GroundDefaults = {
  enabled: true,
  type: "finite",
  method: "sommerfeld",
  soil: null,
  terrain_preset: null,
};

// A ground slot's starting ground (AK#1794): the twin of an A/B/C solver
// slot. Ids are the slot letters ("X", "Y", "Z", then "U", ...: lib/
// groundSlots.ts's GROUND_SLOT_IDS, AK#1801), the keys of the file's
// [grounds.X] tables, and the list is however long the server says.
export type GroundSlotDefaults = GroundDefaults & { id: string };

// The stock set, for a payload without `grounds`: the server's STOCK_GROUNDS
// (antennaknobs/web/settings.py), pinned by tests/test_ground_slots_1794.py.
// Slot Z's soil is null, the served default, which is the stock's "average".
// X is Sommerfeld and Z refl-coef since AK#1856 (it was the other way round).
export const BUILTIN_GROUND_SLOTS: GroundSlotDefaults[] = [
  { id: "X", ...BUILTIN_GROUND },
  { id: "Y", ...BUILTIN_GROUND, enabled: false },
  { id: "Z", ...BUILTIN_GROUND, method: "fast" },
];

export type UiDefaults = {
  /** The settings file's path, or null on the hosted instance. */
  path: string | null;
  exists: boolean;
  /** Whether "Save as my defaults" may write it (never on the hosted app). */
  writable: boolean;
  switches: Record<SwitchKey, boolean>;
  /** The switches the file itself set, as opposed to built-in defaults. */
  switchesSet: SwitchKey[];
  /** The Antenna view's orientation on a design load (AK#1737). */
  orientation: Orientation;
  /** Ground slot X, as a server before AK#1794 served it. */
  ground: GroundDefaults;
  /** Every ground slot, slot X first (AK#1794). Slot X is `ground`. */
  grounds: GroundSlotDefaults[];
  /** Whether a pick starts an analysis, per kind (AC6LA #179). */
  runOnPick: Record<RunOnPickKind, boolean>;
  problems: string[];
};

export const BUILTIN_UI_DEFAULTS: UiDefaults = {
  path: null,
  exists: false,
  writable: false,
  switches: BUILTIN_SWITCHES,
  switchesSet: [],
  orientation: BUILTIN_ORIENTATION,
  ground: BUILTIN_GROUND,
  grounds: BUILTIN_GROUND_SLOTS,
  runOnPick: BUILTIN_RUN_ON_PICK,
  problems: [],
};

const SWITCH_KEYS = Object.keys(BUILTIN_SWITCHES) as SwitchKey[];
const GROUND_TYPES: GroundType[] = ["finite", "pec", "terrain"];
const METHODS: FiniteGroundMethod[] = ["fast", "sommerfeld", "mininec"];

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function parseGround(raw: unknown): GroundDefaults {
  const g = isRecord(raw) ? raw : {};
  const soil =
    isRecord(g.soil) &&
    typeof g.soil.eps_r === "number" &&
    typeof g.soil.sigma === "number"
      ? { eps_r: g.soil.eps_r, sigma: g.soil.sigma }
      : null;
  return {
    enabled: typeof g.enabled === "boolean" ? g.enabled : BUILTIN_GROUND.enabled,
    type: GROUND_TYPES.includes(g.type as GroundType)
      ? (g.type as GroundType)
      : BUILTIN_GROUND.type,
    method: METHODS.includes(g.method as FiniteGroundMethod)
      ? (g.method as FiniteGroundMethod)
      : BUILTIN_GROUND.method,
    soil,
    terrain_preset:
      typeof g.terrain_preset === "string" ? g.terrain_preset : null,
  };
}

// Tolerant by design: the server has already validated the file, so anything
// malformed here is a server this frontend predates, and each field falls
// back to its built-in value on its own.
export function parseUiDefaults(raw: unknown): UiDefaults {
  if (!isRecord(raw)) return BUILTIN_UI_DEFAULTS;
  const sw = isRecord(raw.switches) ? raw.switches : {};
  const switches = { ...BUILTIN_SWITCHES };
  for (const k of SWITCH_KEYS) {
    if (typeof sw[k] === "boolean") switches[k] = sw[k] as boolean;
  }
  const set = Array.isArray(raw.switches_set)
    ? (raw.switches_set.filter((k) =>
        SWITCH_KEYS.includes(k as SwitchKey),
      ) as SwitchKey[])
    : [];
  const av = isRecord(raw.antenna_view) ? raw.antenna_view : {};
  const orientation = ORIENTATIONS.includes(av.orientation as Orientation)
    ? (av.orientation as Orientation)
    : BUILTIN_ORIENTATION;
  const ground = parseGround(raw.ground);
  const wb = isRecord(raw.workbench) && isRecord(raw.workbench.run_on_pick) ? raw.workbench.run_on_pick : {};
  const runOnPick = { ...BUILTIN_RUN_ON_PICK };
  for (const k of RUN_ON_PICK_KINDS) {
    if (typeof wb[k] === "boolean") runOnPick[k] = wb[k] as boolean;
  }
  // A server before AK#1794 serves `ground` alone: it is slot X, and the
  // other slots are the stock set. One before AK#1801 numbers the slots,
  // which read as their letters (groundSlotId).
  const served = Array.isArray(raw.grounds)
    ? raw.grounds.flatMap((g) => {
        const id = isRecord(g) && typeof g.id === "string" ? groundSlotId(g.id) : null;
        return id !== null && isRecord(g) ? [{ id, ...parseGround(g) }] : [];
      })
    : [];
  const grounds: GroundSlotDefaults[] =
    served.length > 0
      ? served
      : [{ ...ground, id: BUILTIN_GROUND_SLOTS[0].id }, ...BUILTIN_GROUND_SLOTS.slice(1)];
  return {
    path: typeof raw.path === "string" ? raw.path : null,
    exists: raw.exists === true,
    writable: raw.writable === true,
    switches,
    switchesSet: set,
    orientation,
    ground,
    grounds,
    runOnPick,
    problems: Array.isArray(raw.problems)
      ? raw.problems.filter((p): p is string => typeof p === "string")
      : [],
  };
}

export type GroundSaveEntry = {
  enabled: boolean;
  type: GroundType;
  method: FiniteGroundMethod;
  eps_r?: number;
  sigma?: number;
  terrain_preset?: string;
};

export type SettingsSaveBody = {
  switches: Record<SwitchKey, boolean>;
  antenna_view: { orientation: Orientation };
  /** The older spelling of ground slot X; the page posts `grounds`. The
   *  server refuses a body carrying both. */
  ground?: GroundSaveEntry;
  /** Every ground slot by id (AK#1794), written as [grounds.X]. */
  grounds?: Record<string, GroundSaveEntry>;
  slots: Record<
    Slot,
    { backend: string; n_per_wire: number; model: Record<string, unknown> }
  >;
  /** Every kind's run-on-pick (AC6LA #179); the server writes only those
   *  that differ from its defaults. */
  workbench?: { run_on_pick: Record<RunOnPickKind, boolean> };
};

export type SaveOutcome =
  | { ok: true; uiDefaults: UiDefaults }
  | { ok: false; problems: string[] };

// POST /settings: writes the settings file on a local install. A refusal
// comes back with its problems (422) or the server's own sentence (403).
export async function saveSettings(body: SettingsSaveBody): Promise<SaveOutcome> {
  try {
    const r = await fetch("/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data: unknown = await r.json().catch(() => null);
    if (r.ok) return { ok: true, uiDefaults: parseUiDefaults(data) };
    const detail = isRecord(data) ? data.detail : null;
    if (isRecord(detail) && Array.isArray(detail.problems)) {
      return {
        ok: false,
        problems: detail.problems.filter((p): p is string => typeof p === "string"),
      };
    }
    return {
      ok: false,
      problems: [typeof detail === "string" ? detail : `HTTP ${r.status}`],
    };
  } catch (e: unknown) {
    return { ok: false, problems: [String((e as Error)?.message ?? e)] };
  }
}
