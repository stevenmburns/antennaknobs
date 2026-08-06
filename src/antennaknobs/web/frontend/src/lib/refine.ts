import { reflectionCoefficient } from "./format";
import { gammaDbFromMag, vswrFromGammaMag } from "./math";
import type { SweepData } from "./api";
import { tunedFloat } from "./tuning";

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
 *  rect; a wildly non-square chart would want its own aspect factor.
 *
 *  `clamped` marks a vertex whose value was PINNED to the chart's domain
 *  edge (a VSWR above the axis ceiling, a cut sample at the radial floor).
 *  Its drawn position is exact — the chart really does put it on the edge —
 *  so subdividing around it cannot improve the picture: the corner where
 *  the curve enters the clamp is an artifact of clamping, not of sampling,
 *  and chasing it O(h) down to MIN_SEGMENT spends solves on a segment that
 *  redraws identically. The planner zeroes a clamped vertex's deviation in
 *  that projection; the crossing still gets ONE look via its unclamped
 *  neighbour's deviation, which is the visible part of the corner. */
export type DisplayPoint = { x: number; y: number; clamped?: boolean };

/** Display-space error, as a fraction of the plot extent, below which the
 *  drawn polyline is indistinguishable from the true curve. 0.003 is ~1 px
 *  at the 350 px charts this app draws — one stroke width.
 *
 *  This, not the turn angle, is what refinement drives on. A turn angle
 *  says "there is a corner here", but a corner is not automatically a
 *  SAMPLING artifact: a VSWR notch resolved to the last decimal still turns
 *  ~177° at the vertex, because the true curve genuinely spikes at that
 *  aspect ratio. Refining on turn angle therefore never terminates on the
 *  exact features that motivated it. The chord deviation instead measures
 *  how far the drawn line is from where the curve actually goes — it
 *  vanishes as O(h²) for any smooth stretch and as O(h) even across a cusp,
 *  so "the picture is right to within a pixel" is a reachable stopping
 *  condition. */
export const DEVIATION_TOLERANCE = tunedFloat(
  "antennaknobs.refineTolerance",
  0.003,
);

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

/** The worst display-space corner on a polyline, in radians. A diagnostic,
 *  not the refinement criterion — see DEVIATION_TOLERANCE for why. */
export function maxKinkRad(
  pts: readonly DisplayPoint[],
  closed = false,
): number {
  return turnAngles(pts, closed).reduce((a, b) => Math.max(a, b), 0);
}

/** Per-vertex chord deviation: the perpendicular distance from each vertex
 *  to the chord joining its two neighbours, in the same normalized display
 *  units as the points.
 *
 *  Read it as "how wrong the picture would be here at half this
 *  resolution": it is exactly the error the polyline would acquire if this
 *  vertex were dropped, which makes it a direct estimate of the error the
 *  polyline HAS between the samples it does carry. Boundary vertices of an
 *  open polyline have no chord (0); a closed one wraps. */
export function chordDeviations(
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
    const cx = next.x - prev.x;
    const cy = next.y - prev.y;
    const chord = Math.hypot(cx, cy);
    const ax = pts[i].x - prev.x;
    const ay = pts[i].y - prev.y;
    // Degenerate chord (the neighbours coincide — a doubling-back spike):
    // fall back to the distance from the vertex to that shared point, which
    // is what the drawn line would miss by.
    out[i] =
      chord === 0
        ? Math.hypot(ax, ay)
        : Math.abs(ax * cy - ay * cx) / chord;
  }
  return out;
}

/** The worst display-space error on a polyline, as a fraction of the plot
 *  extent. The acceptance measure: refinement is judged by whether this
 *  number falls below DEVIATION_TOLERANCE (or at least falls). */
export function maxChordDeviation(
  pts: readonly DisplayPoint[],
  closed = false,
): number {
  return chordDeviations(pts, closed).reduce((a, b) => Math.max(a, b), 0);
}

type Interval = { a: number; b: number; dev: number; len: number };

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
 * to refine: picking a single projection would leave the others coarse. For
 * the freq sweep that union is VSWR ∪ S11-dB ∪ Smith, which is not
 * redundant — VSWR's steepest bend is off resonance where S11-dB has
 * clamped flat, and the Smith locus moves fastest where neither scalar
 * projection does.
 *
 * An interval's score is the chord deviation at its two endpoints: the
 * display-space error the drawn line already carries there. Intervals below
 * `tolerance` are left alone (the picture is right to within a pixel) and
 * so are intervals already shorter than `minSegment` (no subdivision can
 * change what is drawn, and a genuine discontinuity would otherwise eat the
 * whole budget).
 *
 * Returns midpoints of the worst intervals, sorted ascending, never more
 * than `budget` of them. Within one round the newly inserted points cannot
 * be evaluated, so a split interval's children are scored by the
 * smooth-curve estimate "deviation is O(h²)": halving the interval quarters
 * it. That keeps one interval from swallowing the whole budget while still
 * concentrating points where the picture is worst. Real re-evaluation
 * happens across ROUNDS — the caller solves this plan, then asks again with
 * the densified data.
 */
export function planRefinement(
  t: readonly number[],
  projections: readonly (readonly DisplayPoint[])[],
  opts: RefineOptions,
): number[] {
  const budget = Math.max(0, Math.floor(opts.budget));
  if (budget === 0 || t.length < 3) return [];
  const closed = opts.closed ?? false;
  const tolerance = opts.tolerance ?? DEVIATION_TOLERANCE;
  const minSegment = opts.minSegment ?? MIN_SEGMENT;
  const usable = projections.filter((p) => p.length === t.length);
  if (usable.length === 0) return [];

  const n = t.length;
  const devs = new Array<number>(n).fill(0);
  for (const p of usable) {
    const d = chordDeviations(p, closed);
    for (let i = 0; i < n; i++) {
      // A clamped vertex sits exactly where the chart draws it (on the
      // domain edge) — see DisplayPoint.clamped. Another projection where
      // the same sample is NOT clamped still scores it via the max below.
      if (!p[i].clamped) devs[i] = Math.max(devs[i], d[i]);
    }
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
    work.push({ a: t[j], b, dev: Math.max(devs[j], devs[k]), len });
  }

  const out: number[] = [];
  while (out.length < budget) {
    let best = -1;
    let bestScore = 0;
    for (let i = 0; i < work.length; i++) {
      const iv = work[i];
      if (iv.dev <= tolerance || iv.len <= minSegment) continue;
      // Strict > keeps ties on the lowest index: the plan must be
      // deterministic for the same input, regardless of iteration order.
      if (iv.dev > bestScore) {
        bestScore = iv.dev;
        best = i;
      }
    }
    if (best < 0) break; // every interval is accurate enough (or unsplittable)
    const iv = work[best];
    const mid = 0.5 * (iv.a + iv.b);
    out.push(period > 0 ? ((mid % period) + period) % period : mid);
    const child = { dev: iv.dev / 4, len: iv.len / 2 };
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

/** Top of the S11 axis for a set of dB samples: 0 for anything passive, and
 *  ceil(max + 1 dB headroom) when any sample crosses 0 dB. A driven-array
 *  port's ACTIVE reflection is not bounded by |Γ| ≤ 1 — mutual coupling can
 *  push more power into a detuned element than its own generator supplies
 *  (bowtiearray2x4 with length_otop pulled 10% reads +1.3 dB) — and
 *  clamping that onto the 0 dB line hid over-unity behind near-unity, the
 *  most interesting single fact a sweep can tell you about an array tuning.
 *  Exported for SweepChart, exactly as cutDbiTop is for FarFieldChart, so
 *  the chart and the refinement planner cannot disagree about the axis. The
 *  headroom also means no sample sits AT the adaptive top, so over-unity
 *  peaks are never clamp-marked and refinement resolves them like any other
 *  feature. */
export function s11DbTop(dbSamples: readonly number[]): number {
  let m = 0;
  for (const d of dbSamples) if (Number.isFinite(d) && d > m) m = d;
  return m > 0 ? Math.ceil(m + 1) : 0;
}

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

/** Which of the three sweep-consuming charts are actually on screen. All
 *  true is the pre-residency behavior; the planner refines only for the
 *  projections listed true, because polishing a chart nobody can see spends
 *  real solves for zero visible change (a view pinned LATER gets its own
 *  refinement pass — the dwell machinery re-plans, and the server's per-freq
 *  cache makes the shared points free). */
export type SweepProjectionSet = {
  vswr: boolean;
  gamma: boolean;
  smith: boolean;
};

export const ALL_SWEEP_PROJECTIONS: SweepProjectionSet = {
  vswr: true,
  gamma: true,
  smith: true,
};

/** The display polylines a sweep feeds: VSWR vs f, S11 dB vs f, and the
 *  Smith Γ locus — only those `include` lists, in that order. x for the two
 *  scalar charts is LINEAR in MHz over the swept span — that is what
 *  SweepChart's `xOf` does, whatever the freq PLAN's spacing was.
 *  Out-of-domain samples clamp exactly as the charts draw them (a VSWR of
 *  40 sits pinned at the top edge) and carry the `clamped` mark, so
 *  refinement neither chases curvature that is off screen nor sharpens the
 *  corner where the curve meets the edge. */
export function sweepProjections(
  sweep: SweepData,
  z0: number,
  include: SweepProjectionSet = ALL_SWEEP_PROJECTIONS,
): DisplayPoint[][] {
  const f = sweep.freqs_mhz;
  const n = f.length;
  if (n < 3) return [];
  const span = f[n - 1] - f[0] || 1;
  const vswr: DisplayPoint[] = [];
  const gamma: DisplayPoint[] = [];
  const smith: DisplayPoint[] = [];
  // y and its clamp mark in one place, so the two can never disagree.
  const edge = (x: number, raw: number): DisplayPoint => ({
    x,
    y: clamp01(raw),
    ...(raw <= 0 || raw >= 1 ? { clamped: true } : {}),
  });
  const gs = f.map((_, i) =>
    reflectionCoefficient(sweep.z_re[i], sweep.z_im[i], z0),
  );
  // The S11 axis top adapts to over-unity samples (see s11DbTop) — computed
  // over the whole sweep first, the same number SweepChart derives, so the
  // planner refines against the geometry actually drawn.
  const dbs = include.gamma ? gs.map((g) => gammaDbFromMag(g.gMag)) : [];
  const dbHi = s11DbTop(dbs);
  for (let i = 0; i < n; i++) {
    const x = (f[i] - f[0]) / span;
    const g = gs[i];
    if (include.vswr) {
      const v = vswrFromGammaMag(g.gMag);
      vswr.push(
        edge(x, (v - VSWR_DOMAIN.lo) / (VSWR_DOMAIN.hi - VSWR_DOMAIN.lo)),
      );
    }
    if (include.gamma) {
      gamma.push(
        edge(x, (dbs[i] - GAMMA_DB_DOMAIN.lo) / (dbHi - GAMMA_DB_DOMAIN.lo)),
      );
    }
    // Γ plane: the [0,1]² box the chart's circle inscribes, clamp-marked
    // outside it — |Γ| ≤ 1 for a passive port, but a driven-array port's
    // ACTIVE Γ can exceed 1 (see s11DbTop) and the chart clips the disc.
    if (include.smith) {
      const outside = g.gMag > 1;
      smith.push({
        x: (g.gRe + 1) / 2,
        y: (g.gIm + 1) / 2,
        ...(outside ? { clamped: true } : {}),
      });
    }
  }
  return [vswr, gamma, smith].filter((p) => p.length > 0);
}

/** Frequencies (MHz) to add to an existing sweep. Deduped against what is
 *  already sampled: a midpoint that collides with a point the previous
 *  round already inserted would buy nothing and cost a solve. */
export function refineSweepFreqs(
  sweep: SweepData,
  z0: number,
  budget: number,
  include: SweepProjectionSet = ALL_SWEEP_PROJECTIONS,
): number[] {
  const planned = planRefinement(
    sweep.freqs_mhz,
    sweepProjections(sweep, z0, include),
    { budget },
  );
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
  const span = dbiTop - CUT_DBI_FLOOR;
  return Array.from({ length: n }, (_, i) => {
    const t = anglesDeg
      ? (anglesDeg[i] * Math.PI) / 180
      : (2 * Math.PI * i) / n;
    const frac = 0.5 * toFrac(dbi[i]);
    // Radial-clamp mark (same contract as the sweep charts' domain edges):
    // a sample at/below the −20 dBi floor draws at the origin and one
    // at/above the adaptive top draws on the rim, wherever the true value
    // sits — the below-horizon floor sentinel is the common case, and
    // sharpening the corner where a null dives under the floor redraws
    // nothing.
    const raw = (dbi[i] - CUT_DBI_FLOOR) / span;
    // Canvas flips y, but a reflection changes no turn ANGLE — the planner
    // only reads |turn|, so the sign convention here is free.
    return {
      x: Math.cos(t) * frac,
      y: Math.sin(t) * frac,
      ...(raw <= 0 || raw >= 1 ? { clamped: true } : {}),
    };
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
