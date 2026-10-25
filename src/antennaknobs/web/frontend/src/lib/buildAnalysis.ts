// The map and hold builders (AK#2045): an analysis built in the GUI, as the
// data `analyses.to_data` writes (`{an: "Analysis", ...}`), which POST /keep
// turns into its Python (`expr`, the bare `an.to_code`), and which the tab
// then lists by sending that text back with every /analyses (`built`). The
// server reads it with the same reader a shared link's analyses go through
// (`analyses_text.read`, never run) and checks it the same way, so a built
// analysis is listed, picked, run, copied and kept exactly as a design's own.
//
// And what Copy link writes of the listed analyses: their expressions as one
// list (`analysesText`, what `analyses_text.write` prints), packed as a deck
// is, under the per-part cap a link carries.
//
// React-free, so the specs and the bounds are tested alone.

import { MAX_SHARE_CHARS } from "./decks";
import type { SchemaParamSpec } from "./params";

/** One swept axis: the knob, its ends (`lo` may be above `hi`: a sweep runs
 *  either way, as the doublet's high-R branch runs 33 down to 3.5), its
 *  count and spacing. */
export type BuildAxis = { knob: string; lo: number; hi: number; points: number; log: boolean };

/** A two-knob map: |Γ| over the grid, X = 0 drawn as its contour (where the
 *  design is resonant), as the catalog's resonance maps draw it. */
export type MapBuild = { kind: "map"; name: string; x: BuildAxis; y: BuildAxis };

/** A knob sweep held at a target: at every point the held knobs are
 *  re-solved by the workbench's optimizer (an.Hold), resonance on one knob
 *  or a Z0 match on two, and the chart draws R/X and the held knobs. */
export type HoldBuild = {
  kind: "hold";
  name: string;
  sweep: BuildAxis;
  objective: HoldObjective;
  adjust: string[];
  /** The ranges the user set in each knob's Optimize menu (its KnobOpt
   *  optMin/optMax), by knob, when set: a held knob searches its own
   *  (`holdRange`), and the hold carries it as `an.Hold.bounds`. */
  ranges?: Readonly<Record<string, { min: number; max: number }>>;
};

export type Build = MapBuild | HoldBuild;

/** The targets a hold can hold (`web.optimize.OBJECTIVES` less `swr`, which
 *  is a minimisation the hold refuses), and how many knobs each adjusts. */
export const HOLD_TARGETS = [
  { objective: "resonance", knobs: 1, label: "resonance (X = 0)" },
  { objective: "match_z0", knobs: 2, label: "match Z0 (R = Z0 and X = 0)" },
] as const;
export type HoldObjective = (typeof HOLD_TARGETS)[number]["objective"];

/** The fewest and most points per axis the builder takes: a sweep needs two
 *  ends, and the server bounds the rest (a map's hosted point cap). */
export const BUILD_MIN_POINTS = 2;
export const BUILD_MAX_POINTS = 401;

/** The analysis names this many characters long at most. */
export const BUILD_NAME_CHARS = 80;

const fmt = (v: number) => String(Number(v.toPrecision(6)));

/** The range a held knob searches: the one the user set in its Optimize
 *  menu (`opt`) when there is one, else the knob's own, real range (never
 *  an automatic one, `auto_range`, which `hold.free_of` does not take);
 *  null when it has neither. */
export function holdRange(
  k: SchemaParamSpec,
  opt?: { min: number; max: number } | null,
): { lo: number; hi: number; from: "optimize" | "own" } | null {
  if (opt && Number.isFinite(opt.min) && Number.isFinite(opt.max) && opt.min < opt.max) {
    return { lo: opt.min, hi: opt.max, from: "optimize" };
  }
  if (ownRange(k)) return { lo: k.min!, hi: k.max!, from: "own" };
  return null;
}

const ownRange = (k: SchemaParamSpec) =>
  k.min !== null && k.max !== null && k.auto_range !== true && k.min < k.max;

/** The words for a held knob's range, as the builder shows it. */
export function holdRangeText(k: SchemaParamSpec, opt?: { min: number; max: number } | null): string {
  const r = holdRange(k, opt);
  if (!r) return `${k.label}: no range yet`;
  const unit = k.unit ? ` ${k.unit}` : "";
  const where = r.from === "optimize" ? "its Optimize menu's range" : "its own range";
  return `${k.label} searched over ${fmt(r.lo)} to ${fmt(r.hi)}${unit} (${where})`;
}

/** Why `b` cannot be built on this design's knobs (`knobs`, the sweepable
 *  ones), in words the builder shows; null when it can. */
export function buildProblem(b: Build, knobs: readonly SchemaParamSpec[]): string | null {
  const name = b.name.trim();
  if (!name) return "Give the analysis a name";
  if (name.length > BUILD_NAME_CHARS) return `The name is over ${BUILD_NAME_CHARS} characters`;
  const axes = b.kind === "map" ? [b.x, b.y] : [b.sweep];
  for (const a of axes) {
    const k = knobs.find((s) => s.name === a.knob);
    if (!k) return `This design has no knob "${a.knob}" to sweep`;
    if (!Number.isFinite(a.lo) || !Number.isFinite(a.hi)) return `${k.label}: the ends are numbers`;
    if (a.lo === a.hi) return `${k.label}: the two ends are the same`;
    if (a.log && (a.lo <= 0 || a.hi <= 0)) return `${k.label}: a log sweep needs both ends above zero`;
    if (!Number.isInteger(a.points) || a.points < BUILD_MIN_POINTS || a.points > BUILD_MAX_POINTS) {
      return `${k.label}: points is a whole number from ${BUILD_MIN_POINTS} to ${BUILD_MAX_POINTS}`;
    }
  }
  if (b.kind === "map") {
    if (b.x.knob === b.y.knob) return "A map sweeps two different knobs";
    return null;
  }
  const target = HOLD_TARGETS.find((t) => t.objective === b.objective);
  if (!target) return `No hold target "${b.objective}"`;
  if (b.adjust.length !== target.knobs) {
    return `Holding ${target.label} adjusts ${target.knobs === 1 ? "one knob" : `${target.knobs} knobs`}`;
  }
  if (new Set(b.adjust).size !== b.adjust.length) return "Hold each knob once";
  for (const h of b.adjust) {
    const k = knobs.find((s) => s.name === h);
    if (!k) return `This design has no knob "${h}" to hold`;
    if (h === b.sweep.knob) return `${k.label} is the swept knob: a knob is swept or held, not both`;
    // The hold searches the Optimize menu's range, else the knob's own
    // (`hold.free_of`, which takes the first as `an.Hold.bounds`).
    const r = holdRange(k, b.ranges?.[h]);
    if (!r) {
      return `${k.label} has no range for the hold to search: set one in its Optimize menu (right-click the knob)`;
    }
    if (r.from === "optimize" && ownRange(k) && (r.lo < k.min! || r.hi > k.max!)) {
      return `${k.label}: its Optimize range ${fmt(r.lo)} to ${fmt(r.hi)} reaches outside its own ${fmt(k.min!)} to ${fmt(k.max!)}; a hold searches within it`;
    }
  }
  return null;
}

function sweepData(a: BuildAxis) {
  return { an: "Sweep", knob: a.knob, lo: a.lo, hi: a.hi, points: a.points, ...(a.log ? { spacing: "log" } : {}) };
}

/** `b` as the data `analyses.from_data` reads (what /keep's `spec` takes). */
export function buildData(b: Build): Record<string, unknown> {
  if (b.kind === "map") {
    return {
      an: "Analysis",
      name: b.name.trim(),
      sweep: [sweepData(b.x), sweepData(b.y)],
      views: [{ an: "Map" }],
      references: { an: "Ref", x: [0] },
    };
  }
  // The Optimize menu's ranges, as `an.Hold.bounds` (an.Knob each): what
  // lets a deck's SY knob, which has no range of its own, be held.
  const bounds = b.adjust.flatMap((h) => {
    const r = b.ranges?.[h];
    return r ? [{ an: "Knob", name: h, min: r.min, max: r.max }] : [];
  });
  return {
    an: "Analysis",
    name: b.name.trim(),
    sweep: sweepData(b.sweep),
    views: [{ an: "Rx" }, { an: "Knobs" }],
    hold: {
      an: "Hold",
      objective: b.objective,
      adjust: [...b.adjust],
      ...(bounds.length ? { bounds } : {}),
    },
  };
}

/** A starting name for `b`, by its knobs' labels (`label`), not already one
 *  of `taken`'s (a number after it when it is). */
export function defaultBuildName(b: Build, label: (knob: string) => string, taken: ReadonlySet<string>): string {
  const base =
    b.kind === "map"
      ? `map ${label(b.x.knob)} × ${label(b.y.knob)}`
      : `${label(b.sweep.knob)} ${fmt(b.sweep.lo)} to ${fmt(b.sweep.hi)}, ${b.adjust.map(label).join(" and ")} held at ${b.objective === "resonance" ? "resonance" : "Z0"}`;
  return uniqueName(base, taken);
}

/** `name`, or `name (2)`, `name (3)`, … : the first not in `taken`. */
export function uniqueName(name: string, taken: ReadonlySet<string>): string {
  if (!taken.has(name)) return name;
  for (let i = 2; ; i++) {
    const n = `${name} (${i})`;
    if (!taken.has(n)) return n;
  }
}

/** The analyses a link carries, as one list of their expressions (what
 *  `analyses_text.write` prints; `read` reads it back). */
export function analysesText(exprs: readonly string[]): string {
  const body = exprs.map((e) => `    ${e.replace(/\n/g, "\n    ")},\n`).join("");
  return `[\n${body}]\n`;
}

/** Why a link cannot carry its parts, by part, or null: the deck and its
 *  analyses are each capped at MAX_SHARE_CHARS packed (`decks.shareable`),
 *  and the knobs at their own bound. A refused link is never written. */
export function linkPartsProblem(parts: { deck?: number | null; analyses?: number | null; knobs?: string | null }): string | null {
  if (parts.deck != null && parts.deck > MAX_SHARE_CHARS) {
    return `The deck is ${parts.deck} characters packed, over the ${MAX_SHARE_CHARS} a link carries: open the file in the other browser instead`;
  }
  if (parts.analyses != null && parts.analyses > MAX_SHARE_CHARS) {
    return `The analyses are ${parts.analyses} characters packed, over the ${MAX_SHARE_CHARS} a link carries: copy a link to fewer of them`;
  }
  return parts.knobs ?? null;
}
