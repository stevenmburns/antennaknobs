// The Z-vs-parameter view's pure half (docs/design/z-vs-param-view.md): which
// parameters sweep, the ladder a spec asks for, and the chart's axis rules.
// React-free, so the ladder and the axes are tested without a chart.

import { richardsonExtrap, feedwiseRichardson } from "./math";
import { axisTicks, formatTick, type AxisDomain } from "./sweepAxis";
import { isGroup, type SchemaItem, type SchemaParamSpec } from "./params";

/** The density parameter: the request's `n_per_wire` (segments per λ/4 at the
 *  design frequency), the same name on the wire as in the request. */
export const DENSITY = "n_per_wire";

/** The old convergence switch's ladder, and the CLI's NOMINAL_NSEGS_LADDER:
 *  the default density sweep, kept literal so the migrated trail and its Z*
 *  did not move. Any other density spec is a computed ladder. */
export const DENSITY_LADDER: readonly number[] = [8, 12, 17, 24, 34, 48, 68];

export const MIN_POINTS = 2;
/** The header's cap. A local server admits any count (its cost model caps
 *  only the hosted instance, at 500, and refuses there with a 413 the view
 *  shows), so this is a UI bound on one edit, not the server's: 201 covers a
 *  fine ladder over a decade or two without a typo queueing thousands of
 *  solves. */
export const MAX_POINTS = 201;
/** A knob's default point count (linear). */
export const KNOB_POINTS = 11;
/** A knob without its own min/max sweeps this fraction either side. */
export const KNOB_SPAN_FRACTION = 0.2;

/** What the view sweeps: a parameter and its ladder's shape. */
export type ParamSweepSpec = {
  param: string;
  lo: number;
  hi: number;
  points: number;
  /** Geometric spacing (a fixed ratio, SimNEC's logStep) instead of linear. */
  log: boolean;
};

/** What the runner sends: the parameter, its values, and how to name it. */
export type ParamSweepRequest = {
  param: string;
  values: number[];
  label: string;
};

/** One sweep's result, streamed point by point. `values` is the swept
 *  parameter at each point (a failed point is skipped, so it may be shorter
 *  than the request's). `z_*_extrap` is the Richardson estimate, density
 *  only, and null until three points are in. */
export type ParamSweepData = {
  param: string;
  label: string;
  values: number[];
  z_re: number[];
  z_im: number[];
  z_re_extrap: number | null;
  z_im_extrap: number | null;
  /** Multi-feed designs: per-point per-feed Z (outer index = point). */
  feeds_z_re?: number[][];
  feeds_z_im?: number[][];
  feeds_z_re_extrap?: (number | null)[];
  feeds_z_im_extrap?: (number | null)[];
  /** The closing record's advisories (the gap-fed density warning). */
  advisories?: { category: string; text: string }[];
  /** The server refused the sweep (a 413 over the hosted instance's point
   *  cap, a 403 poor-match withhold, a 422): its own words, shown in the
   *  view rather than the request being clamped quietly. */
  error?: string;
};

export const isDensity = (param: string) => param === DENSITY;

// Knobs that set a frequency are not swept: the measurement frequency stays
// fixed during a knob sweep, and moving either is a frequency sweep in
// disguise. The server refuses the same names.
const FREQUENCY_KNOBS = new Set(["freq", "design_freq"]);

/** The design's knobs the view can sweep: visible top-level float/int knobs
 *  that set no frequency. Groups (per-band knobs), enums and bools are phase 2
 *  or never. */
export function sweepableKnobs(schema: readonly SchemaItem[]): SchemaParamSpec[] {
  return schema.filter(
    (item): item is SchemaParamSpec =>
      !isGroup(item) &&
      (item.kind === "float" || item.kind === "int") &&
      !item.linked_to_design_freq &&
      !item.link_meas_freq_to_param &&
      !FREQUENCY_KNOBS.has(item.name),
  );
}

export const DEFAULT_DENSITY_SPEC: ParamSweepSpec = {
  param: DENSITY,
  lo: DENSITY_LADDER[0],
  hi: DENSITY_LADDER[DENSITY_LADDER.length - 1],
  points: DENSITY_LADDER.length,
  log: true,
};

/** A knob's default sweep: its own min…max (the slider's travel), else
 *  ±KNOB_SPAN_FRACTION of its value; KNOB_POINTS linear points. */
export function defaultKnobSpec(knob: SchemaParamSpec, current: number): ParamSweepSpec {
  const span = Math.abs(current) * KNOB_SPAN_FRACTION || 1;
  const lo = knob.min ?? current - span;
  const hi = knob.max ?? current + span;
  return { param: knob.name, lo, hi, points: KNOB_POINTS, log: false };
}

export function sameSpec(a: ParamSweepSpec, b: ParamSweepSpec): boolean {
  return (
    a.param === b.param &&
    a.lo === b.lo &&
    a.hi === b.hi &&
    a.points === b.points &&
    a.log === b.log
  );
}

/** Why a points count is refused, or null when it is fine: a whole number
 *  in MIN_POINTS…MAX_POINTS. The header reverts a refused edit and shows
 *  this. */
export function pointsProblem(n: number): string | null {
  return Number.isInteger(n) && n >= MIN_POINTS && n <= MAX_POINTS
    ? null
    : `${MIN_POINTS}–${MAX_POINTS}`;
}

export const clampPoints = (n: number) =>
  Math.min(MAX_POINTS, Math.max(MIN_POINTS, Math.round(Number.isFinite(n) ? n : MIN_POINTS)));

/** The values a spec sweeps, ascending in the order the spec runs.
 *
 *  The default density spec is the literal DENSITY_LADDER. Otherwise linear
 *  or geometric from lo to hi (a geometric ladder needs both ends above
 *  zero, else it falls back to linear), and an integer parameter — density,
 *  or an `int` knob — rounded to integers with duplicates dropped, since
 *  rounding collides points at a coarse end (the CLI's gen_xs rule, so
 *  10…500 × 20 solves only whole counts). Density never goes below 1. */
export function paramValues(spec: ParamSweepSpec, integer: boolean): number[] {
  if (isDensity(spec.param) && sameSpec(spec, DEFAULT_DENSITY_SPEC)) {
    return [...DENSITY_LADDER];
  }
  const n = clampPoints(spec.points);
  const { lo, hi } = spec;
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [];
  const geometric = spec.log && lo > 0 && hi > 0;
  const raw: number[] = [];
  for (let i = 0; i < n; i++) {
    const t = n === 1 ? 0 : i / (n - 1);
    raw.push(geometric ? lo * (hi / lo) ** t : lo + (hi - lo) * t);
  }
  if (!integer) return raw.map((v) => Number(v.toPrecision(12)));
  const floor = isDensity(spec.param) ? 1 : -Infinity;
  const out: number[] = [];
  for (const v of raw) {
    const r = Math.max(floor, Math.round(v));
    if (!out.includes(r)) out.push(r);
  }
  return out;
}

/** Richardson Z* in 1/N — density sweeps only (a knob has no limit to
 *  extrapolate to). Null until three points are in. */
export function paramRichardson(
  param: string,
  values: readonly number[],
  zRe: readonly number[],
  zIm: readonly number[],
): { re: number | null; im: number | null } {
  if (!isDensity(param)) return { re: null, im: null };
  const inv = values.map((n) => 1 / n);
  return { re: richardsonExtrap(inv, [...zRe]), im: richardsonExtrap(inv, [...zIm]) };
}

export function paramFeedRichardson(
  param: string,
  values: readonly number[],
  feedsRe: number[][],
  feedsIm: number[][],
): { feedsRe: (number | null)[]; feedsIm: (number | null)[] } | null {
  if (!isDensity(param)) return null;
  return feedwiseRichardson(
    values.map((n) => 1 / n),
    feedsRe,
    feedsIm,
  );
}

// --- the chart's axes ---------------------------------------------------------

/** One y axis's range: Auto fits its own trace; fixed is the viewer's. */
export type RxAxisChoice = { kind: "auto" } | { kind: "fixed"; lo: number; hi: number };
export const RX_AUTO: RxAxisChoice = { kind: "auto" };

/** Auto's fit: the trace's min…max plus 8 % headroom each side, and never a
 *  span below 0.02 Ω — a converged trace that moves by milliohms would
 *  otherwise fill the axis with rounding noise. Empty: 0…1. */
export function autoRxDomain(values: readonly number[]): AxisDomain {
  const f = values.filter((v) => Number.isFinite(v));
  if (f.length === 0) return { lo: 0, hi: 1 };
  let lo = Math.min(...f);
  let hi = Math.max(...f);
  const minSpan = 0.02;
  if (hi - lo < minSpan) {
    const mid = (lo + hi) / 2;
    lo = mid - minSpan / 2;
    hi = mid + minSpan / 2;
  }
  const pad = 0.08 * (hi - lo);
  return { lo: lo - pad, hi: hi + pad };
}

export function rxDomain(choice: RxAxisChoice, values: readonly number[]): AxisDomain {
  return choice.kind === "fixed" ? { lo: choice.lo, hi: choice.hi } : autoRxDomain(values);
}

export function validRxChoice(c: RxAxisChoice): boolean {
  return c.kind === "auto" || (Number.isFinite(c.lo) && Number.isFinite(c.hi) && c.hi > c.lo);
}

/** Tick values for a y axis: lib/sweepAxis's 1-2-2.5-5 steps, without the
 *  off-grid floor tick it adds (an auto range's padded edge, which would
 *  crowd the first real tick). */
export function rxTicks(d: AxisDomain): number[] {
  const t = axisTicks(d);
  if (t.length > 2) {
    const step = t[2] - t[1];
    const k = t[0] / step;
    if (Math.abs(k - Math.round(k)) > 1e-6) return t.slice(1);
  }
  return t;
}

/** The x range the chart draws: the swept values' span (a single point gets
 *  a unit span around it). */
export function xDomain(values: readonly number[]): AxisDomain {
  if (values.length === 0) return { lo: 0, hi: 1 };
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  if (hi > lo) return { lo, hi };
  return { lo: lo - 0.5, hi: hi + 0.5 };
}

/** Whether a log x axis is drawable: every value above zero. */
export const canLogX = (d: AxisDomain) => d.lo > 0 && d.hi > 0;

/** Parameter value → its x as a fraction of the plot width (unclamped). */
export function xFraction(d: AxisDomain, log: boolean): (v: number) => number {
  if (log && canLogX(d)) {
    const a = Math.log(d.lo);
    const b = Math.log(d.hi);
    return (v) => (Math.log(v) - a) / (b - a);
  }
  return (v) => (v - d.lo) / (d.hi - d.lo);
}

/** A log axis's ticks: 1-2-5 per decade inside the domain, plus its ends
 *  (10 20 50 100 200 500 over 10…500, as the CLI labels it). */
export function logTicks(d: AxisDomain): number[] {
  if (!canLogX(d)) return [];
  const out: number[] = [];
  for (let e = Math.floor(Math.log10(d.lo)); e <= Math.ceil(Math.log10(d.hi)); e++) {
    for (const m of [1, 2, 5]) {
      const v = Number((m * 10 ** e).toPrecision(12));
      if (v >= d.lo * (1 - 1e-9) && v <= d.hi * (1 + 1e-9)) out.push(v);
    }
  }
  return out;
}

export function xTicks(d: AxisDomain, log: boolean): number[] {
  if (log && canLogX(d)) {
    const t = logTicks(d);
    if (t.length >= 2) return t;
  }
  return axisTicks(d).filter((v) => v >= d.lo && v <= d.hi);
}

/** The index of the swept point nearest a pointer's x fraction, or -1. */
export function nearestIndex(
  values: readonly number[],
  frac: (v: number) => number,
  at: number,
): number {
  let best = -1;
  let bestD = Infinity;
  values.forEach((v, i) => {
    const d = Math.abs(frac(v) - at);
    if (d < bestD) {
      best = i;
      bestD = d;
    }
  });
  return best;
}

/** A parameter value as the chart prints it: integers bare, else 4
 *  significant digits. */
export function formatParam(v: number): string {
  if (Number.isInteger(v)) return String(v);
  return String(Number(v.toPrecision(4)));
}

/** An impedance component as the chart prints it: enough digits to see a
 *  converging trace move (72.15 against 72.09), no more. */
export function formatOhm(v: number): string {
  const a = Math.abs(v);
  const digits = a >= 1000 ? 0 : a >= 100 ? 1 : a >= 1 ? 2 : 3;
  return v.toFixed(digits).replace("-", "−");
}


/** A value box's y, moved clear of every box already placed that it would
 *  overlap: below it if that still fits above `bottom`, else above it (not
 *  above `top`). (The Z-vs-parameter chart's value boxes.) */
export function nudgeClear(
  y: number,
  b: { x: number; w: number; h: number },
  placed: readonly { x: number; y: number; w: number; h: number }[],
  top: number,
  bottom: number,
): number {
  const gap = 2;
  let out = y;
  for (let pass = 0; pass < placed.length + 1; pass++) {
    const hit = placed.find(
      (p) =>
        b.x < p.x + p.w && p.x < b.x + b.w && out < p.y + p.h + gap && p.y < out + b.h + gap,
    );
    if (!hit) return out;
    const below = hit.y + hit.h + gap;
    const above = hit.y - b.h - gap;
    out = below <= bottom ? below : Math.max(top, above);
  }
  return out;
}

export { formatTick };
