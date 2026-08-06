import { reflectionCoefficient } from "./format";
import { gammaDbFromMag, vswrFromGammaMag } from "./math";
import type { SweepData } from "./api";

// Adaptive sampling refinement (issue #744).
//
// A fixed grid renders smooth physics as a kinked polyline wherever the
// curve bends faster than the grid — a sharp resonance on the freq sweep, a
// multi-lobed elevation cut's nulls. The planners below decide WHERE to put
// extra samples, and they decide it in DISPLAY space: the goal is "no
// visible corner", which is a property of the drawn polyline, not of the
// underlying data. Raw-data curvature would over-refine a physically steep
// but visually flat stretch (a VSWR excursion far above the chart's y
// ceiling) and under-refine a physically gentle but visually sharp one (a
// null grazing the polar origin, where the radial map compresses dB into
// almost no radius).
//
// Everything here is pure: parameter values in, parameter values out. The
// callers own the transport (a /sweep re-request, a /cuts re-request) and
// the dwell that decides refinement is allowed to run at all.

/** A polyline vertex in normalized display units. Both planners normalize
 *  so the PLOT EXTENT is 1 on each axis — the sweep charts map to [0,1]²,
 *  the polar cut to [-0.5, 0.5]² — which makes one tolerance and one
 *  minimum-segment constant meaningful for both. Assumes a square-ish plot
 *  rect; a wildly non-square chart would want its own aspect factor. */
export type DisplayPoint = { x: number; y: number };

/** Turn angle above which a vertex reads as a corner rather than a curve.
 *  0.12 rad ≈ 6.9°: at typical chart sizes (300–450 px) that is the point
 *  where a 1.3–1.5 px stroke stops looking like a smooth bend. */
export const KINK_TOLERANCE_RAD = 0.12;

/** Intervals shorter than this (in normalized display units) are never
 *  split again. Two reasons, both about not burning the budget on
 *  something no amount of sampling fixes: a genuine DISCONTINUITY (the
 *  below-horizon floor sentinel on a cut, a VSWR clamp at the chart
 *  ceiling) has a kink that survives every subdivision; and a sub-pixel
 *  segment cannot show a corner in the first place. 0.004 of the plot
 *  extent is ~1.5 px at 380 px. */
export const MIN_SEGMENT = 0.004;

/** Discrete curvature at each vertex of a display polyline: the turn angle
 *  between the incoming and outgoing segments, in radians. Boundary
 *  vertices of an open polyline have no turn (0); a closed one wraps.
 *  Degenerate (zero-length) segments contribute no turn — a repeated point
 *  is not a corner. */
export function turnAngles(
  pts: readonly DisplayPoint[],
  closed = false,
): number[] {
  const n = pts.length;
  const out = new Array<number>(n).fill(0);
  if (n < 3) return out;
  for (let i = 0; i < n; i++) {
    const prev = i === 0 ? (closed ? pts[n - 1] : null) : pts[i - 1];
    const next = i === n - 1 ? (closed ? pts[0] : null) : pts[i + 1];
    if (!prev || !next) continue;
    const ax = pts[i].x - prev.x;
    const ay = pts[i].y - prev.y;
    const bx = next.x - pts[i].x;
    const by = next.y - pts[i].y;
    const na = Math.hypot(ax, ay);
    const nb = Math.hypot(bx, by);
    if (na === 0 || nb === 0) continue;
    // atan2(|a×b|, a·b) — numerically stable at both 0 and π, unlike acos
    // of a dot product that rounds outside [-1, 1].
    out[i] = Math.atan2(Math.abs(ax * by - ay * bx), ax * bx + ay * by);
  }
  return out;
}

/** The worst display-space corner on a polyline, in radians. The acceptance
 *  measure for "no visible kink" — refinement is judged by whether this
 *  number falls. */
export function maxKinkRad(
  pts: readonly DisplayPoint[],
  closed = false,
): number {
  return turnAngles(pts, closed).reduce((a, b) => Math.max(a, b), 0);
}

type Interval = { a: number; b: number; kink: number; len: number };

// score = kink × length. The kink says how bad the corner at this
// interval's ends is; the length says how much of it THIS interval is
// responsible for. Between a long and a short interval flanking the same
// corner, splitting the long one removes most of the bend — the short one
// scores lower and is left alone.
function score(iv: Interval): number {
  return iv.kink * iv.len;
}

export type RefineOptions = {
  /** Hard cap on how many new parameter values this plan may contain. */
  budget: number;
  /** Wrap the last vertex back to the first (polar cuts). */
  closed?: boolean;
  /** Parameter-space period, required when `closed` (360 for degrees). */
  period?: number;
  tolerance?: number;
  minSegment?: number;
};

/** Plan the next round of sample points.
 *
 * `t` is the sorted parameter array actually sampled (freqs in MHz, angles
 * in degrees); `projections` are one display polyline per plot that
 * consumes this SAME data array, each index-aligned with `t`. The interval
 * score is the max across projections, because there is only one data array
 * to refine: picking a single projection would leave the others kinked. For
 * the freq sweep that union is VSWR ∪ S11-dB ∪ Smith, which is not
 * redundant — VSWR's steepest bend is off resonance where S11-dB is flat,
 * and the Smith locus bends where neither scalar projection does.
 *
 * Returns midpoints of the worst intervals, sorted ascending, never more
 * than `budget` of them. Within one round the newly inserted points cannot
 * be evaluated, so an interval that is split gets its children scored by
 * the smooth-curve estimate "turn angle is O(h)": halving the interval
 * halves the kink and the length, quartering the score. That keeps one
 * pathological interval from swallowing the whole budget while still
 * concentrating points where the curve actually bends. The true re-
 * evaluation happens across ROUNDS — the caller solves this plan, then asks
 * again with the densified data.
 */
export function planRefinement(
  t: readonly number[],
  projections: readonly (readonly DisplayPoint[])[],
  opts: RefineOptions,
): number[] {
  const budget = Math.max(0, Math.floor(opts.budget));
  if (budget === 0 || t.length < 3) return [];
  const closed = opts.closed ?? false;
  const tolerance = opts.tolerance ?? KINK_TOLERANCE_RAD;
  const minSegment = opts.minSegment ?? MIN_SEGMENT;
  const usable = projections.filter((p) => p.length === t.length);
  if (usable.length === 0) return [];

  const n = t.length;
  const turns = new Array<number>(n).fill(0);
  for (const p of usable) {
    const ta = turnAngles(p, closed);
    for (let i = 0; i < n; i++) turns[i] = Math.max(turns[i], ta[i]);
  }

  const nIv = closed ? n : n - 1;
  const period = opts.period ?? 0;
  const work: Interval[] = [];
  for (let j = 0; j < nIv; j++) {
    const k = (j + 1) % n;
    // The wrap interval's far endpoint lives one period up, so its midpoint
    // lands between the last and first sample instead of at the middle of
    // the whole range.
    const b = k === 0 ? t[0] + period : t[k];
    let len = 0;
    for (const p of usable) {
      len = Math.max(len, Math.hypot(p[k].x - p[j].x, p[k].y - p[j].y));
    }
    work.push({ a: t[j], b, kink: Math.max(turns[j], turns[k]), len });
  }

  const out: number[] = [];
  while (out.length < budget) {
    let best = -1;
    let bestScore = 0;
    for (let i = 0; i < work.length; i++) {
      const iv = work[i];
      if (iv.kink <= tolerance || iv.len <= minSegment) continue;
      const s = score(iv);
      // Strict > keeps ties on the lowest index: the plan must be
      // deterministic for the same input, regardless of iteration order.
      if (s > bestScore) {
        bestScore = s;
        best = i;
      }
    }
    if (best < 0) break; // every interval is smooth enough (or unsplittable)
    const iv = work[best];
    const mid = 0.5 * (iv.a + iv.b);
    out.push(period > 0 ? ((mid % period) + period) % period : mid);
    const child = { kink: iv.kink / 2, len: iv.len / 2 };
    work[best] = { a: iv.a, b: mid, ...child };
    work.push({ a: mid, b: iv.b, ...child });
  }
  return out.sort((x, y) => x - y);
}

// --- Freq sweep (SweepChart's linear-MHz x axis, SmithChart's Γ plane) ---

// SweepChart's y domains (components/charts/SweepChart.tsx DOMAIN). Kept
// here rather than imported so this module stays free of React/canvas
// imports; the values are the chart's published axis contract, and the
// vitest suite pins them against the chart.
const VSWR_DOMAIN = { lo: 1, hi: 10 };
const GAMMA_DB_DOMAIN = { lo: -30, hi: 0 };

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

/** The display polylines a sweep feeds: VSWR vs f, S11 dB vs f, and the
 *  Smith Γ locus. x for the two scalar charts is LINEAR in MHz over the
 *  swept span — that is what SweepChart's `xOf` does, whatever the freq
 *  PLAN's spacing was. Out-of-domain samples clamp exactly as the charts
 *  draw them (a VSWR of 40 sits pinned at the top edge), so refinement
 *  never chases curvature that is off screen. */
export function sweepProjections(
  sweep: SweepData,
  z0: number,
): DisplayPoint[][] {
  const f = sweep.freqs_mhz;
  const n = f.length;
  if (n < 3) return [];
  const span = f[n - 1] - f[0] || 1;
  const vswr: DisplayPoint[] = [];
  const gamma: DisplayPoint[] = [];
  const smith: DisplayPoint[] = [];
  for (let i = 0; i < n; i++) {
    const x = (f[i] - f[0]) / span;
    const g = reflectionCoefficient(sweep.z_re[i], sweep.z_im[i], z0);
    const v = vswrFromGammaMag(g.gMag);
    vswr.push({
      x,
      y: clamp01((v - VSWR_DOMAIN.lo) / (VSWR_DOMAIN.hi - VSWR_DOMAIN.lo)),
    });
    const db = gammaDbFromMag(g.gMag);
    gamma.push({
      x,
      y: clamp01(
        (db - GAMMA_DB_DOMAIN.lo) / (GAMMA_DB_DOMAIN.hi - GAMMA_DB_DOMAIN.lo),
      ),
    });
    // Γ plane on the unit disc → the [0,1]² box the chart's circle inscribes.
    smith.push({ x: (g.gRe + 1) / 2, y: (g.gIm + 1) / 2 });
  }
  return [vswr, gamma, smith];
}

/** Frequencies (MHz) to add to an existing sweep. Deduped against what is
 *  already sampled: a midpoint that collides with a point the previous
 *  round already inserted would buy nothing and cost a solve. */
export function refineSweepFreqs(
  sweep: SweepData,
  z0: number,
  budget: number,
): number[] {
  const planned = planRefinement(sweep.freqs_mhz, sweepProjections(sweep, z0), {
    budget,
  });
  // Relative tolerance: sweep spans run 1.8–54 MHz, so an absolute epsilon
  // would be meaningless at one end of that range.
  const span = sweep.freqs_mhz[sweep.freqs_mhz.length - 1] - sweep.freqs_mhz[0];
  const eps = Math.abs(span) * 1e-6;
  return planned.filter(
    (f) => !sweep.freqs_mhz.some((have) => Math.abs(have - f) <= eps),
  );
}

// --- Pattern cuts (FarFieldChart's polar projection) ---

/** Origin of FarFieldChart's radial axis, in dBi. */
export const CUT_DBI_FLOOR = -20;

/** FarFieldChart's radial map: absolute dBi → fraction of the plot radius,
 *  given the top of the (adaptive) radial scale. Exported so the chart and
 *  the refinement planner cannot drift apart about where a sample lands. */
export function cutDbiToFrac(dbiTop: number): (db: number) => number {
  const span = dbiTop - CUT_DBI_FLOOR;
  return (db: number) => clamp01((db - CUT_DBI_FLOOR) / span);
}

/** The top of the radial scale for a set of trace peaks: +10 dBi by
 *  default, expanded (with 1 dB headroom) to fit the highest lobe on
 *  screen. */
export function cutDbiTop(peaks: readonly number[]): number {
  const maxPeak = peaks
    .filter(Number.isFinite)
    .reduce((a, b) => Math.max(a, b), 10);
  return Math.max(10, Math.ceil(maxPeak + 1));
}

/** One cut's polyline in polar display units, normalized to a plot extent
 *  of 1 (radius 0.5) so the shared tolerance/min-segment constants mean the
 *  same thing here as on the sweep charts. `anglesDeg` is the explicit
 *  parameterisation when the cut is non-uniform; a uniform cut is at
 *  t = 2π·i/n, exactly as the chart draws it. */
export function cutProjection(
  dbi: readonly number[],
  anglesDeg: readonly number[] | undefined,
  dbiTop: number,
): DisplayPoint[] {
  const toFrac = cutDbiToFrac(dbiTop);
  const n = dbi.length;
  return Array.from({ length: n }, (_, i) => {
    const t = anglesDeg
      ? (anglesDeg[i] * Math.PI) / 180
      : (2 * Math.PI * i) / n;
    const frac = 0.5 * toFrac(dbi[i]);
    // Canvas flips y, but a reflection changes no turn ANGLE — the planner
    // only reads |turn|, so the sign convention here is free.
    return { x: Math.cos(t) * frac, y: Math.sin(t) * frac };
  });
}

/** The angles (degrees, ascending in [0, 360)) a cut should additionally be
 *  sampled at. Deduped against the angles already held. */
export function refineCutAngles(
  dbi: readonly number[],
  anglesDeg: readonly number[] | undefined,
  dbiTop: number,
  budget: number,
): number[] {
  const n = dbi.length;
  if (n < 3) return [];
  const t = anglesDeg
    ? Array.from(anglesDeg)
    : Array.from({ length: n }, (_, i) => (360 * i) / n);
  const planned = planRefinement(t, [cutProjection(dbi, anglesDeg, dbiTop)], {
    budget,
    closed: true,
    period: 360,
  });
  const eps = 1e-6;
  return planned.filter((a) => !t.some((have) => Math.abs(have - a) <= eps));
}
