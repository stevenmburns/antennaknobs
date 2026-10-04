// Startup settings (AK#1492): where the workbench starts, served on
// /capabilities as `ui_defaults` from the server's settings.toml. The server
// owns every default (antennaknobs/web/settings.py), and this file restates
// none of them (AK#1858): the frontend ships in the same wheel as its server,
// so a payload without them is a broken install, and the page says so
// (useCapabilities) rather than guessing. The key lists below are vocabulary,
// not defaults; tests/test_settings_toml_1492.py and its siblings hold each
// one equal to the server's table.
import type {
  FiniteGroundMethod,
  GroundType,
  SoilParams,
} from "./ground";
import type { Slot } from "./backends";
import { GROUND_SLOT_IDS } from "./groundSlots";
import type { Projection } from "./view";
import { apiFetch } from "./pin";

// The server's SWITCHES keys, in its order.
export const SWITCH_KEYS = [
  "live",
  "freq_sweep",
  "convergence_sweep",
  "pattern_renorm",
  "refine",
  "heatmap_currents",
  "current_waveforms",
  "wire_labels",
  "feed_labels",
] as const;

export type SwitchKey = (typeof SWITCH_KEYS)[number];

// The Antenna view's orientation on a design load (AK#1737). "auto" is the
// per-design guess the server sends as `default_view`; any other value wins
// over that guess at EVERY design load. The server's ORIENTATIONS table
// (antennaknobs/web/settings.py) is the one list; the save writes nothing
// for "auto".
export type Orientation = "auto" | "top" | "front" | "side" | "iso";

export const ORIENTATIONS: Orientation[] = ["auto", "top", "front", "side", "iso"];

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
// analysis it is), from settings.toml's [workbench.run_on_pick]. The kinds
// are the server's RUN_ON_PICK keys, in its order
// (tests/test_settings_run_on_pick.py); which of them run is the server's
// table alone. `map` is valid before the workbench draws a map
// (sweep-framework step 5).
export const RUN_ON_PICK_KINDS = [
  "frequency",
  "pattern",
  "knob",
  "held",
  "convergence",
  "map",
] as const;

export type RunOnPickKind = (typeof RUN_ON_PICK_KINDS)[number];

export type GroundDefaults = {
  enabled: boolean;
  type: GroundType;
  method: FiniteGroundMethod;
  /** null: start at the served soil default. */
  soil: SoilParams | null;
  /** null: start at the terrain panel's own first preset. */
  terrain_preset: string | null;
};

// A ground slot's starting ground (AK#1794): the twin of an A/B/C solver
// slot. Ids are the slot letters ("X", "Y", "Z", then "U", ...: lib/
// groundSlots.ts's GROUND_SLOT_IDS, AK#1801), the keys of the file's
// [grounds.X] tables, and the list is however long the server says.
export type GroundSlotDefaults = GroundDefaults & { id: string };

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
  /** Every ground slot, slot X first (AK#1794). */
  grounds: GroundSlotDefaults[];
  /** Whether a pick starts an analysis, per kind (AC6LA #179). */
  runOnPick: Record<RunOnPickKind, boolean>;
  problems: string[];
};

const GROUND_TYPES: GroundType[] = ["finite", "pec", "terrain"];
const METHODS: FiniteGroundMethod[] = ["fast", "sommerfeld", "mininec"];

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

const isStringList = (v: unknown): v is string[] =>
  Array.isArray(v) && v.every((x) => typeof x === "string");

/** A served table of booleans, every key present, or the first key that is
 *  missing or not a boolean. */
function readFlags<K extends string>(
  raw: unknown,
  keys: readonly K[],
): { flags: Record<K, boolean> } | { bad: string } {
  if (!isRecord(raw)) return { bad: "" };
  const flags = {} as Record<K, boolean>;
  for (const k of keys) {
    if (typeof raw[k] !== "boolean") return { bad: k };
    flags[k] = raw[k] as boolean;
  }
  return { flags };
}

function readGroundSlot(raw: unknown): GroundSlotDefaults | null {
  if (!isRecord(raw)) return null;
  const { id, enabled, type, method, soil, terrain_preset } = raw;
  if (typeof id !== "string" || !GROUND_SLOT_IDS.includes(id)) return null;
  if (typeof enabled !== "boolean") return null;
  if (!GROUND_TYPES.includes(type as GroundType)) return null;
  if (!METHODS.includes(method as FiniteGroundMethod)) return null;
  let soilParams: SoilParams | null = null;
  if (soil !== null) {
    if (!isRecord(soil) || typeof soil.eps_r !== "number" || typeof soil.sigma !== "number")
      return null;
    soilParams = { eps_r: soil.eps_r, sigma: soil.sigma };
  }
  const preset = typeof terrain_preset === "string" ? terrain_preset : null;
  if (preset === null && terrain_preset !== null) return null;
  return {
    id,
    enabled,
    type: type as GroundType,
    method: method as FiniteGroundMethod,
    soil: soilParams,
    terrain_preset: preset,
  };
}

export type UiDefaultsRead =
  | { defaults: UiDefaults; refusal: null }
  | { defaults: null; refusal: string };

const refuse = (what: string): UiDefaultsRead => ({ defaults: null, refusal: what });

/** The served `ui_defaults`, or the sentence naming what it lacks. Strict
 *  (AK#1858): the server resolves every field, so anything absent or
 *  ill-typed is a payload this page cannot start from, and no field falls
 *  back to a value of the page's own. */
export function readUiDefaults(raw: unknown): UiDefaultsRead {
  if (!isRecord(raw)) return refuse("the server sent no startup settings (ui_defaults)");
  const sw = readFlags(raw.switches, SWITCH_KEYS);
  if ("bad" in sw)
    return refuse(
      sw.bad
        ? `the server's startup settings give no value for the switch "${sw.bad}"`
        : "the server's startup settings carry no switches",
    );
  const switchesSet = raw.switches_set;
  if (!isStringList(switchesSet))
    return refuse("the server's startup settings do not say which switches the file set");
  const av = raw.antenna_view;
  if (!isRecord(av) || !ORIENTATIONS.includes(av.orientation as Orientation))
    return refuse("the server's startup settings give no Antenna view orientation");
  const wb = isRecord(raw.workbench) ? raw.workbench.run_on_pick : undefined;
  const rp = readFlags(wb, RUN_ON_PICK_KINDS);
  if ("bad" in rp)
    return refuse(
      rp.bad
        ? `the server's startup settings do not say whether picking a "${rp.bad}" analysis runs it`
        : "the server's startup settings carry no run-on-pick table",
    );
  if (!Array.isArray(raw.grounds) || raw.grounds.length === 0)
    return refuse("the server's startup settings carry no ground slots");
  const grounds: GroundSlotDefaults[] = [];
  for (const g of raw.grounds) {
    const slot = readGroundSlot(g);
    if (slot === null)
      return refuse(`the server's startup settings carry a ground slot this page cannot read (${JSON.stringify(g)})`);
    if (grounds.some((s) => s.id === slot.id))
      return refuse(`the server's startup settings name ground slot ${slot.id} twice`);
    grounds.push(slot);
  }
  const { exists, writable, problems } = raw;
  const path = typeof raw.path === "string" ? raw.path : null;
  if (path === null && raw.path !== null)
    return refuse("the server's startup settings give no settings-file path");
  if (typeof exists !== "boolean" || typeof writable !== "boolean")
    return refuse("the server's startup settings do not say whether the settings file exists or is writable");
  if (!isStringList(problems))
    return refuse("the server's startup settings carry no problems list");
  return {
    defaults: {
      path,
      exists,
      writable,
      switches: sw.flags,
      switchesSet: switchesSet.filter((k): k is SwitchKey =>
        (SWITCH_KEYS as readonly string[]).includes(k),
      ),
      orientation: av.orientation as Orientation,
      grounds,
      runOnPick: rp.flags,
      problems,
    },
    refusal: null,
  };
}

/** The served `ui_defaults`, or null when it is absent or incomplete (the
 *  sentence saying which is readUiDefaults'). */
export function parseUiDefaults(raw: unknown): UiDefaults | null {
  return readUiDefaults(raw).defaults;
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

/** A save's outcome. A success names the file it wrote: the reply is the
 *  re-read `ui_defaults`, but the session it came from already holds what it
 *  saved, so the path is all the page reads back. */
export type SaveOutcome =
  | { ok: true; path: string | null }
  | { ok: false; problems: string[] };

// POST /settings: writes the settings file on a local install. A refusal
// comes back with its problems (422) or the server's own sentence (403).
export async function saveSettings(body: SettingsSaveBody): Promise<SaveOutcome> {
  try {
    const r = await apiFetch("/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data: unknown = await r.json().catch(() => null);
    if (r.ok)
      return { ok: true, path: isRecord(data) && typeof data.path === "string" ? data.path : null };
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
