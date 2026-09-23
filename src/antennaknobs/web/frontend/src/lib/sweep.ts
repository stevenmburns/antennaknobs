import type { SweepData } from "./api";
import { tunedInt } from "./tuning";
import { backendSupportsGround, type BackendEntry } from "./backends";
import type { GroundModel } from "./ground";
import type { BandSpec, ExampleDescriptor, SweepRangeSpec } from "./params";

// Sweep frequency plan: the freq list `runSweep` requests.
//
// ONE RANGE (AK#1682). The measurement-freq dial's travel IS the sweep
// range: `resolveSweepRange` produces a single `SweepRange` that the dial
// (VfoPanel) travels and the sweep grids (`sweepGrid`), so the two cannot
// disagree. It is seeded by a fixed precedence, first match wins:
//
//   1. "session" — the user's edit from the dial's right-click menu. Lives
//      in DesignSession state only; nothing persists to settings.toml. A
//      design switch or a band pick clears it.
//   2. "file"    — a file design's own sweep: the `.nec` FR card, the `.ssn`
//      Generator sweep (`sweep_range` with source "file").
//   3. "design"  — a Python design's `ui_params["sweep_range"]`, else its
//      `meas_freq_range` (the dial span it has always declared).
//   4. "policy"  — the design's `sweep_policy` (band lock or factors).
//   5. "default" — ×0.8–×1.25 of the anchor, log-spaced.
//
// "↺ design range" in the menu clears level 1, which lands on 2–5.
//
// Levels 4–5 are relative to an anchor. It must be STABLE while the dial
// moves — a window that followed measFreq would move under the dial that
// travels it — so an unlocked dial anchors on the selected measurement band
// (`measBandAnchor`), not on measFreq itself. Locked, measFreq follows the
// design frequency, and the policy's `anchor` picks between the two exactly
// as before.
//
// Band-locked policy: when the active band contains the anchor, the range is
// that band's [min_mhz, max_mhz], so the trace stays inside the band the
// user is tuning instead of bleeding into adjacent ones. Falls through to
// the multiplicative window if the anchor sits outside every band.
//
// Density: a range may carry its own (`step` MHz for lin, `points` — the
// total count across [lo, hi] — for log); that grid is always solved, and
// refinement still adds points between its points. A range with no density
// gets the historical count (below).
//
// Log density is a plain point count, not points-per-decade (AK#1682
// follow-up): a band-locked range like 14.0-14.35 MHz is 0.011 decades, so
// 17 points used to read back as "≈1,500 points/decade" in the menu. A
// served `points_per_decade` (backward compatibility only — the wire format
// is now `points`) is converted on arrival in `specRange`.
// Sommerfeld ground stays at half resolution when refinement is off:
// momwire 0.7.0's C++ fill + grid cache made warm sweeps fast (~30 ms per
// point once the per-frequency grids are cached; measured 0.6 s for 21
// points at 2 threads), but the FIRST sweep after enabling it still fills
// one grid per point (measured 4.3 s for 21 points at 2 threads; 41 would be
// ~9 s) — half resolution halves that cold hit. Fast (reflection-
// coefficient) ground and momwire PEC ground are cheap enough for full
// resolution.

export type SweepSpacing = "lin" | "log";

/** The one range (AK#1682): the dial's travel and the sweep's span, in MHz,
 *  with an optional density — `step` (MHz between points) when lin,
 *  `points` (the total count across [lo, hi]) when log. No density = the
 *  app's default count. */
export type SweepRange = {
  lo: number;
  hi: number;
  spacing: SweepSpacing;
  step?: number;
  points?: number;
};

/** Which rung of the precedence produced the range (see the header). */
export type SweepRangeLevel = "session" | "file" | "design" | "policy" | "default";

export type ResolvedSweepRange = { range: SweepRange; level: SweepRangeLevel };

/** Everything the range resolution reads. */
export type SweepRangeInputs = {
  currentExample: ExampleDescriptor | undefined;
  currentVariant: string;
  measLocked: boolean;
  measFreq: number;
  designFreq: number;
  currentBands: BandSpec[];
  freqWindowCeiling: number;
  /** The selected measurement band's snap frequency (designFreq before one
   *  is chosen) — the unlocked dial's stable anchor. Defaults to measFreq. */
  measBandAnchor?: number;
  /** The selected measurement band is a custom one (#1487): its window
   *  replaces the design's absolute range, as it replaced the file's dial
   *  span before AK#1682. */
  measBandIsCustom?: boolean;
  /** Level 1: the user's edit this session, or null. */
  sweepRangeEdit?: SweepRange | null;
};

/** The hosted instance refuses a sweep over this many points
 *  (`MAX_SWEEP_POINTS` in web/cost.py; tests/test_sweep_range_1682.py holds
 *  the two equal). A grid finer than this is clamped to it, and the range
 *  menu says so. */
export const MAX_SWEEP_POINTS = 500;

// A served density, whichever form it came in, as the state's own. The
// adapter (web/adapter.py) already converts a served `points_per_decade` to
// `points` before it reaches /examples, so that fallback is for a spec built
// some other way (a stale cache, a hand-built fixture) rather than the live
// wire format.
function specRange(spec: SweepRangeSpec): SweepRange {
  const { lo, hi, spacing } = spec;
  const out: SweepRange = { lo, hi, spacing };
  if (spacing === "lin") {
    if (spec.step && spec.step > 0) out.step = spec.step;
    else if (spec.points && spec.points >= 2) out.step = (hi - lo) / (spec.points - 1);
  } else if (spec.points && spec.points >= 2) {
    out.points = spec.points;
  } else if (spec.points_per_decade && spec.points_per_decade > 0) {
    out.points = Math.max(
      2,
      Math.round(spec.points_per_decade * Math.log10(hi / lo)) + 1,
    );
  }
  return out;
}

/** Levels 2–5: the range "↺ design range" returns to. */
export function designSweepRange(inp: SweepRangeInputs): ResolvedSweepRange {
  const {
    currentExample,
    currentVariant,
    measLocked,
    measFreq,
    designFreq,
    currentBands,
    freqWindowCeiling,
    measBandAnchor = measFreq,
    measBandIsCustom = false,
  } = inp;
  if (!measBandIsCustom) {
    const spec = currentExample?.sweep_range ?? null;
    if (spec && spec.hi > spec.lo) {
      return { range: specRange(spec), level: spec.source === "file" ? "file" : "design" };
    }
    const dial = currentExample?.meas_freq_range_mhz ?? null;
    if (dial && dial[1] > dial[0]) {
      return { range: { lo: dial[0], hi: dial[1], spacing: "log" }, level: "design" };
    }
  }
  const policy =
    currentExample?.variant_ui?.[currentVariant]?.sweep_policy ??
    currentExample?.sweep_policy;
  const measAnchor = measLocked ? measFreq : measBandAnchor;
  const anchor =
    !measLocked || policy?.anchor === "meas_freq" ? measAnchor : designFreq;
  const bandLocked = policy?.band_locked
    ? currentBands.find((b) => anchor >= b.min_mhz && anchor <= b.max_mhz)
    : undefined;
  if (bandLocked) {
    return {
      range: { lo: bandLocked.min_mhz, hi: bandLocked.max_mhz, spacing: "log" },
      level: "policy",
    };
  }
  const loF = policy?.lo_factor ?? 0.8;
  const hiF = policy?.hi_factor ?? 1.25;
  return {
    range: {
      lo: Math.max(0.5, anchor * loF),
      hi: Math.min(freqWindowCeiling, anchor * hiF),
      spacing: "log",
    },
    level: loF !== 0.8 || hiF !== 1.25 ? "policy" : "default",
  };
}

/** The range in force: the session edit when there is one, else the
 *  design's (levels 2–5). */
export function resolveSweepRange(inp: SweepRangeInputs): ResolvedSweepRange {
  const edit = inp.sweepRangeEdit;
  if (edit && edit.hi > edit.lo && edit.lo > 0) {
    return { range: edit, level: "session" };
  }
  return designSweepRange(inp);
}

/** The point count a range with no density of its own gets. */
export function defaultSweepPoints(params: {
  backend: BackendEntry;
  groundEnabled: boolean;
  groundModel: GroundModel;
  /** Adaptive resolution is on for this session (the default): the base
   *  grid's job is then DETECTION, not resolution — it only has to land
   *  samples in a feature's tails for the refinement planner to dig in —
   *  so it starts lean and lets refinement spend points where the curve
   *  actually bends. 17 log-spaced (~6% spacing) keeps every plausible
   *  resonance signature within reach of at least one sample; much below
   *  15 the straddled-feature blindspot (a notch no sample touches at
   *  all) becomes a real risk. With refinement OFF the base grid IS the
   *  final rendering, so the historical 41 (21 on Sommerfeld ground)
   *  stays — the toggle must mean "today's behavior", not "coarser". */
  refineEnabled?: boolean;
}): number {
  const { backend, groundEnabled, groundModel, refineEnabled = true } = params;
  const slowGround =
    backendSupportsGround(backend) &&
    groundEnabled &&
    groundModel === "sommerfeld";
  return refineEnabled ? SWEEP_BASE_N : slowGround ? 21 : 41;
}

export type SweepGrid = {
  freqs: number[];
  /** Points the range's own density asks for, before the cap. */
  requested: number;
  /** The grid was clamped to `MAX_SWEEP_POINTS`. */
  clamped: boolean;
};

function linspace(lo: number, hi: number, n: number): number[] {
  if (n < 2) return [lo];
  return Array.from({ length: n }, (_, i) =>
    i === n - 1 ? hi : lo + (i / (n - 1)) * (hi - lo),
  );
}

function logspace(lo: number, hi: number, n: number): number[] {
  if (n < 2) return [lo];
  return Array.from({ length: n }, (_, i) =>
    Math.exp(Math.log(lo) + (i / (n - 1)) * (Math.log(hi) - Math.log(lo))),
  );
}

/** How many points `range` asks for (its own density, else `defaultN`). */
export function sweepPointCount(range: SweepRange, defaultN: number): number {
  const { lo, hi, spacing, step, points } = range;
  if (hi === lo) return 1;
  // An inverted derived window (a ceiling below the anchor's low factor)
  // keeps the historical default grid; only a real range has a density.
  if (!(hi > lo)) return defaultN;
  if (spacing === "lin" && step && step > 0) {
    const n = Math.floor((hi - lo) / step + 1e-9) + 1;
    // A step that does not divide the span still ends at hi: the sweep must
    // reach the dial's end stop.
    return lo + (n - 1) * step < hi - (hi - lo) * 1e-9 ? n + 1 : n;
  }
  if (spacing === "log" && points && points >= 2) {
    return points;
  }
  return defaultN;
}

/** The frequencies `range` sweeps: its own grid when it has a density
 *  (a lin step lands on lo, lo + step, … and closes on hi; a log density is
 *  evenly log-spaced from lo to hi), else `defaultN` points at its spacing.
 *  Clamped to `cap` points. */
export function sweepGrid(
  range: SweepRange,
  defaultN: number,
  cap: number = MAX_SWEEP_POINTS,
): SweepGrid {
  const { lo, hi, spacing, step } = range;
  const requested = sweepPointCount(range, defaultN);
  if (requested > cap) {
    return {
      freqs: spacing === "lin" ? linspace(lo, hi, cap) : logspace(lo, hi, cap),
      requested,
      clamped: true,
    };
  }
  if (spacing === "lin" && step && step > 0 && hi > lo) {
    const freqs = Array.from({ length: requested }, (_, i) =>
      Math.min(hi, lo + i * step),
    );
    freqs[freqs.length - 1] = hi;
    return { freqs, requested, clamped: false };
  }
  return {
    freqs:
      spacing === "lin"
        ? linspace(lo, hi, requested)
        : logspace(lo, hi, requested),
    requested,
    clamped: false,
  };
}

/** The density the menu shows for `range` — its own, or the one its
 *  `n`-point default grid works out to. Log's `points` is `n` itself when
 *  the range has none of its own: no ppd/log10 conversion needed, since the
 *  field IS the point count now. */
export function effectiveDensity(
  range: SweepRange,
  n: number,
): { step: number; points: number } {
  const { lo, hi } = range;
  const gaps = Math.max(1, n - 1);
  return {
    step: range.step ?? (hi - lo) / gaps,
    points: range.points ?? n,
  };
}

/** Apply one menu edit to the range in force, or null when the result is
 *  not a range (lo ≥ hi, a non-positive density, a log `points` below 2).
 *  The first edit materialises the density the grid was using, so changing
 *  lo alone keeps the spacing the user was looking at; a spacing switch
 *  keeps the point count exactly — log's density IS the point count, so no
 *  ppd/log10 round trip is needed to preserve it. */
export function editSweepRange(
  current: SweepRange,
  n: number,
  patch: Partial<SweepRange>,
): SweepRange | null {
  const d = effectiveDensity(current, n);
  const base: SweepRange =
    current.spacing === "lin"
      ? { lo: current.lo, hi: current.hi, spacing: "lin", step: d.step }
      : { lo: current.lo, hi: current.hi, spacing: "log", points: d.points };
  const next: SweepRange = { ...base, ...patch };
  if (patch.spacing && patch.spacing !== current.spacing) {
    const gaps = Math.max(1, n - 1);
    delete next.step;
    delete next.points;
    if (patch.spacing === "lin") next.step = (next.hi - next.lo) / gaps;
    else next.points = n;
  }
  if (next.spacing === "lin") delete next.points;
  else delete next.step;
  if (next.points !== undefined) next.points = Math.round(next.points);
  const ok =
    Number.isFinite(next.lo) &&
    Number.isFinite(next.hi) &&
    next.lo > 0 &&
    next.hi > next.lo &&
    (next.spacing === "lin"
      ? next.step !== undefined && next.step > 0
      : next.points !== undefined && next.points >= 2);
  return ok ? next : null;
}

export function planSweepFreqs(
  params: SweepRangeInputs & {
    backend: BackendEntry;
    groundEnabled: boolean;
    groundModel: GroundModel;
    refineEnabled?: boolean;
  },
): number[] {
  return sweepGrid(resolveSweepRange(params).range, defaultSweepPoints(params))
    .freqs;
}

// The lean base grid used when refinement will polish the curve (see
// defaultSweepPoints). Overridable without a rebuild (lib/tuning.ts) for the
// design that manages to straddle a feature at ~6% spacing.
const SWEEP_BASE_N = tunedInt("antennaknobs.sweepBaseN", 17, 101);

// Point budget for adaptive sweep refinement (issue #744), summed across
// rounds. 17 planned + 48 refined = 65 points, an order of magnitude under
// the hosted MAX_SWEEP_POINTS=500 cap (web/cost.py) and — thanks to the
// server's per-freq Z cache — nearly free to re-request on a later dwell.
// Overridable without a rebuild (lib/tuning.ts).
export const SWEEP_REFINE_BUDGET = tunedInt(
  "antennaknobs.sweepRefineBudget",
  48,
  400,
);
// Per round, so one round's plan (which cannot re-evaluate its own inserted
// points) never commits the whole budget on an estimate.
export const SWEEP_REFINE_ROUND_BUDGET = 12;

/** Merge refinement points into an accumulated sweep, re-sorted by
 *  frequency for display.
 *
 * Every row array is permuted by the SAME ordering — the per-feed Z rows
 * (bowtie arrays) are index-aligned with `freqs_mhz` by SweepData's
 * contract, and a chart that reads `feeds_z_re[i]` next to `freqs_mhz[i]`
 * would otherwise plot one feed's impedance at another frequency's x. A
 * frequency already present wins over the incoming duplicate: the existing
 * value came from the same cached solve, so preferring it keeps the merge
 * idempotent.
 */
export function mergeSweepPoints(base: SweepData, extra: SweepData): SweepData {
  const eps =
    Math.abs(
      (base.freqs_mhz[base.freqs_mhz.length - 1] ?? 0) -
        (base.freqs_mhz[0] ?? 0),
    ) * 1e-9;
  type Row = { from: "base" | "extra"; i: number };
  const rows: Row[] = base.freqs_mhz.map((_, i) => ({ from: "base", i }));
  for (let i = 0; i < extra.freqs_mhz.length; i++) {
    const f = extra.freqs_mhz[i];
    if (base.freqs_mhz.some((have) => Math.abs(have - f) <= eps)) continue;
    rows.push({ from: "extra", i });
  }
  const freqAt = (r: Row) =>
    (r.from === "base" ? base : extra).freqs_mhz[r.i];
  rows.sort((a, b) => freqAt(a) - freqAt(b));
  // Per-feed rows survive the merge only when every contributing row has
  // one. A half-populated feeds array would be worse than none: the chart
  // indexes it positionally, so a hole reads as another feed's impedance.
  const pick = (
    get: (s: SweepData) => number[][] | undefined,
  ): number[][] | undefined => {
    const got = rows.map((r) => get(r.from === "base" ? base : extra)?.[r.i]);
    return got.length > 0 && got.every((row) => Array.isArray(row))
      ? (got as number[][])
      : undefined;
  };
  const feedsRe = pick((s) => s.feeds_z_re);
  const feedsIm = pick((s) => s.feeds_z_im);
  return {
    freqs_mhz: rows.map(freqAt),
    z_re: rows.map((r) => (r.from === "base" ? base : extra).z_re[r.i]),
    z_im: rows.map((r) => (r.from === "base" ? base : extra).z_im[r.i]),
    ...(feedsRe ? { feeds_z_re: feedsRe } : {}),
    ...(feedsIm ? { feeds_z_im: feedsIm } : {}),
  };
}

/** How far the sweep in flight has got (AK#1682), for the charts' status
 *  line. Counts are points RECEIVED, never points requested — a point is
 *  counted when its NDJSON record lands, so a stream that dies part way
 *  stops the count where the curve stops.
 *
 *  The two phases are kept distinct because they promise different things.
 *  A base sweep asks for a known grid, so `received / planned` is an honest
 *  fraction. A refinement pass has no fixed size: the planner decides round
 *  by round and may conclude long before the budget, so the budget is shown
 *  as the ceiling it is ("≤"), never as a denominator to be reached. */
export type SweepProgress =
  | { phase: "base"; received: number; planned: number }
  | { phase: "refine"; received: number; budget: number };

/** The status line the charts print for `p` — "sweeping 12/17",
 *  "refining +8 (≤48)". */
export function sweepProgressLabel(p: SweepProgress): string {
  return p.phase === "base"
    ? `sweeping ${p.received}/${p.planned}`
    : `refining +${p.received} (≤${p.budget})`;
}

/** The fraction a progress bar may honestly fill: the base grid only. A
 *  refinement pass has no known end (see SweepProgress), so it gets none. */
export function sweepProgressFraction(p: SweepProgress): number | null {
  if (p.phase !== "base" || p.planned <= 0) return null;
  return Math.min(1, p.received / p.planned);
}
