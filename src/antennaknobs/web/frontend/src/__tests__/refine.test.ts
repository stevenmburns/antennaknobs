// The pure half of adaptive refinement (issue #744): where extra samples
// go, decided from display-space curvature. Everything here is
// input-in/values-out — no fetch, no React, no canvas — so the criterion
// itself is pinned independently of the transport that carries it.
import { describe, it, expect } from "vitest";
import {
  DEVIATION_TOLERANCE,
  chordDeviations,
  cutDbiToFrac,
  cutDbiTop,
  cutProjection,
  maxChordDeviation,
  maxKinkRad,
  planRefinement,
  refineCutAngles,
  refineSweepFreqs,
  s11DbTop,
  sweepProjections,
  turnAngles,
  type DisplayPoint,
} from "../lib/refine";
import { mergeSweepPoints } from "../lib/sweep";
import type { SweepData } from "../lib/api";

const line = (n: number): DisplayPoint[] =>
  Array.from({ length: n }, (_, i) => ({ x: i / (n - 1), y: 0.5 }));

describe("turnAngles / maxKinkRad", () => {
  it("a straight polyline has no curvature anywhere", () => {
    expect(maxKinkRad(line(9))).toBe(0);
  });

  it("a right-angle corner turns by π/2 at the vertex only", () => {
    const pts = [
      { x: 0, y: 0 },
      { x: 0.5, y: 0 },
      { x: 0.5, y: 0.5 },
    ];
    const t = turnAngles(pts);
    expect(t[0]).toBe(0);
    expect(t[1]).toBeCloseTo(Math.PI / 2, 12);
    expect(t[2]).toBe(0);
  });

  it("a closed polyline wraps: a regular polygon turns equally at every vertex", () => {
    const n = 12;
    const poly = Array.from({ length: n }, (_, i) => ({
      x: Math.cos((2 * Math.PI * i) / n),
      y: Math.sin((2 * Math.PI * i) / n),
    }));
    const t = turnAngles(poly, true);
    for (const a of t) expect(a).toBeCloseTo((2 * Math.PI) / n, 12);
    // Open, the two ends are boundary vertices with no turn.
    const open = turnAngles(poly, false);
    expect(open[0]).toBe(0);
    expect(open[n - 1]).toBe(0);
  });

  it("a repeated point is not a corner", () => {
    const pts = [
      { x: 0, y: 0 },
      { x: 0.5, y: 0 },
      { x: 0.5, y: 0 },
      { x: 1, y: 0.5 },
    ];
    expect(turnAngles(pts)[1]).toBe(0);
  });
});

describe("chordDeviations / maxChordDeviation", () => {
  it("a straight polyline deviates nowhere", () => {
    expect(maxChordDeviation(line(9))).toBe(0);
  });

  it("measures the perpendicular miss of the chord across a vertex", () => {
    // Dropping the apex would draw the chord y=0; the apex is 0.25 above it.
    const pts = [
      { x: 0, y: 0 },
      { x: 0.5, y: 0.25 },
      { x: 1, y: 0 },
    ];
    expect(chordDeviations(pts)[1]).toBeCloseTo(0.25, 12);
    expect(chordDeviations(pts)[0]).toBe(0);
  });

  it("falls as O(h^2) on a smooth curve — the property that lets it terminate", () => {
    const arc = (n: number) =>
      Array.from({ length: n }, (_, i) => {
        const a = (Math.PI * i) / (n - 1);
        return { x: Math.cos(a), y: Math.sin(a) };
      });
    const coarse = maxChordDeviation(arc(9));
    const fine = maxChordDeviation(arc(17));
    expect(fine / coarse).toBeGreaterThan(0.15);
    expect(fine / coarse).toBeLessThan(0.35);
  });

  it("a spike whose neighbours coincide still reports its full miss", () => {
    const pts = [
      { x: 0, y: 0 },
      { x: 0.2, y: 0.4 },
      { x: 0, y: 0 },
    ];
    expect(chordDeviations(pts)[1]).toBeCloseTo(Math.hypot(0.2, 0.4), 12);
  });

  it("stays finite where the turn angle does not converge (a true spike)", () => {
    // A V with slope +-20: sampling it perfectly still turns ~174 deg at the
    // vertex, so a turn-angle criterion would refine forever. The chord
    // deviation of the same V halves with the sample spacing.
    const v = (h: number) => [
      { x: 0.5 - h, y: 20 * h },
      { x: 0.5, y: 0 },
      { x: 0.5 + h, y: 20 * h },
    ];
    expect(maxKinkRad(v(0.01))).toBeCloseTo(maxKinkRad(v(0.0001)), 3);
    expect(maxChordDeviation(v(0.0001))).toBeLessThan(
      maxChordDeviation(v(0.01)) / 50,
    );
  });
});

describe("planRefinement", () => {
  const t5 = [0, 1, 2, 3, 4];

  it("proposes nothing for a polyline that is already smooth", () => {
    expect(planRefinement(t5, [line(5)], { budget: 10 })).toEqual([]);
  });

  it("puts its points at the corner, not spread over the flat stretch", () => {
    // Flat, flat, sharp bend, flat: the kink lives at index 2.
    const pts: DisplayPoint[] = [
      { x: 0.0, y: 0.5 },
      { x: 0.25, y: 0.5 },
      { x: 0.5, y: 0.5 },
      { x: 0.75, y: 0.0 },
      { x: 1.0, y: 0.0 },
    ];
    const got = planRefinement(t5, [pts], { budget: 4 });
    expect(got.length).toBe(4);
    // Every point lands in the span the bend touches — the corner spans
    // vertices 2 and 3, so intervals [1,2], [2,3] and [3,4] all help.
    for (const v of got) expect(v).toBeGreaterThanOrEqual(1);
    // Nothing wasted on [0,1], which is flat at both ends.
    for (const v of got) expect(v).toBeGreaterThan(1);
  });

  it("respects the budget exactly when demand exceeds it", () => {
    const zig: DisplayPoint[] = Array.from({ length: 21 }, (_, i) => ({
      x: i / 20,
      y: i % 2 === 0 ? 0.2 : 0.8,
    }));
    const t = Array.from({ length: 21 }, (_, i) => i);
    for (const budget of [1, 3, 7, 20]) {
      expect(planRefinement(t, [zig], { budget }).length).toBe(budget);
    }
    expect(planRefinement(t, [zig], { budget: 0 })).toEqual([]);
  });

  it("is deterministic: the same input yields the identical plan", () => {
    const zig: DisplayPoint[] = Array.from({ length: 15 }, (_, i) => ({
      x: i / 14,
      y: 0.5 + 0.3 * Math.sin(i * 2.1),
    }));
    const t = Array.from({ length: 15 }, (_, i) => i);
    const a = planRefinement(t, [zig], { budget: 9 });
    expect(planRefinement(t, [zig], { budget: 9 })).toEqual(a);
    expect(a).toEqual([...a].sort((p, q) => p - q));
  });

  it("a discontinuity costs a bounded handful of points, not the budget", () => {
    // A step no amount of sampling removes. The per-split estimate
    // (deviation is O(h^2)) has to fall fast enough that the plan gives up
    // on it — otherwise one clamp edge on a VSWR trace eats every point.
    const step: DisplayPoint[] = [
      { x: 0, y: 0 },
      { x: 0.4, y: 0 },
      { x: 0.4, y: 1 },
      { x: 1, y: 1 },
    ];
    // The estimate falls 4x per split, so an interval is abandoned after
    // ~log4(dev/tolerance) levels — a bound independent of the budget.
    const got = planRefinement([0, 1, 2, 3], [step], { budget: 100 });
    expect(got.length).toBeGreaterThan(0);
    expect(got.length).toBeLessThan(60);
  });

  it("takes the union across projections: a bend in EITHER earns points", () => {
    const flat = line(5);
    const bent: DisplayPoint[] = [
      { x: 0.0, y: 0.5 },
      { x: 0.25, y: 0.5 },
      { x: 0.5, y: 0.5 },
      { x: 0.75, y: 0.0 },
      { x: 1.0, y: 0.0 },
    ];
    expect(planRefinement(t5, [flat], { budget: 4 })).toEqual([]);
    expect(planRefinement(t5, [flat, bent], { budget: 4 })).toEqual(
      planRefinement(t5, [bent], { budget: 4 }),
    );
  });

  it("ignores projections whose length does not match the parameter array", () => {
    expect(planRefinement(t5, [line(3)], { budget: 4 })).toEqual([]);
  });

  it("wraps the last-to-first interval when closed", () => {
    // 4 samples of a circle: every vertex turns 90°, so the worst interval
    // includes the wrap one, whose midpoint must be 315° — not 180°.
    const t = [0, 90, 180, 270];
    const pts = t.map((a) => ({
      x: Math.cos((a * Math.PI) / 180) * 0.5,
      y: Math.sin((a * Math.PI) / 180) * 0.5,
    }));
    const got = planRefinement(t, [pts], {
      budget: 4,
      closed: true,
      period: 360,
    });
    expect(got).toEqual([45, 135, 225, 315]);
  });

  it("refinement drives the drawn error under tolerance on a smooth curve", () => {
    // Sample a Lorentzian-shaped notch coarsely, then at the refined
    // parameter set, and compare how far each rendered polyline misses.
    const yOf = (f: number) => 1 - 1 / (1 + 400 * (f - 0.5) * (f - 0.5));
    const ptsOf = (fs: number[]) => fs.map((f) => ({ x: f, y: yOf(f) }));
    let fs = Array.from({ length: 21 }, (_, i) => i / 20);
    const before = maxChordDeviation(ptsOf(fs));
    expect(before).toBeGreaterThan(DEVIATION_TOLERANCE);
    for (let round = 0; round < 6; round++) {
      const added = planRefinement(fs, [ptsOf(fs)], { budget: 12 });
      if (added.length === 0) break;
      fs = [...fs, ...added].sort((a, b) => a - b);
    }
    expect(maxChordDeviation(ptsOf(fs))).toBeLessThan(DEVIATION_TOLERANCE);
    expect(fs.length).toBeLessThan(21 + 6 * 12);
  });
});

describe("sweepProjections / refineSweepFreqs", () => {
  // A series-RLC-shaped resonance: R(f) flat, X(f) crossing zero steeply.
  function notchSweep(freqs: number[]): SweepData {
    return {
      freqs_mhz: freqs,
      z_re: freqs.map(() => 50),
      z_im: freqs.map((f) => 4000 * (f - 14.2)),
    };
  }

  it("maps x linearly in MHz across the swept span (SweepChart's xOf)", () => {
    const s = notchSweep([10, 12, 20]);
    const [vswr] = sweepProjections(s, 50);
    expect(vswr[0].x).toBeCloseTo(0, 12);
    expect(vswr[1].x).toBeCloseTo(0.2, 12);
    expect(vswr[2].x).toBeCloseTo(1, 12);
  });

  it("clamps to the charts' y domains so off-screen curvature is ignored", () => {
    const s = notchSweep([10, 14.2, 20]);
    const [vswr, gamma] = sweepProjections(s, 50);
    // A wildly reactive endpoint pins at the VSWR ceiling and at 0 dB S11.
    expect(vswr[0].y).toBe(1);
    expect(gamma[0].y).toBeCloseTo(1, 4);
    // Perfect match at the notch: VSWR 1 (bottom) and S11 below −30 (bottom).
    expect(vswr[1].y).toBe(0);
    expect(gamma[1].y).toBe(0);
  });

  it("s11DbTop: 0 for anything passive, ceil(max+1) once a sample crosses 0 dB", () => {
    expect(s11DbTop([-30, -4, -0.2])).toBe(0);
    expect(s11DbTop([])).toBe(0);
    expect(s11DbTop([-3, 0.6])).toBe(2); // ceil(1.6)
    expect(s11DbTop([1.28])).toBe(3); // ceil(2.28)
    expect(s11DbTop([NaN, Infinity, -1])).toBe(0); // garbage never grows the axis
  });

  it("an over-unity active port draws ABOVE the 0 dB line, unclamped, and refinable", () => {
    // Negative active resistance (a detuned driven-array element eating its
    // neighbours' power): |Γ| > 1, S11 ≈ +2.8 dB.
    const s: SweepData = {
      freqs_mhz: [10, 12, 14, 16, 18],
      z_re: [150, 80, -45, 80, 150],
      z_im: [100, 100, 100, 100, 100],
    };
    const [gamma] = sweepProjections(s, 50, {
      vswr: false,
      gamma: true,
      smith: false,
    });
    // The headroom (s11DbTop) means the over-unity sample sits INSIDE the
    // axis — below the top, above where 0 dB now maps — and is not
    // clamp-marked, so refinement resolves the crossing like any feature.
    expect(gamma[2].clamped).toBeUndefined();
    expect(gamma[2].y).toBeLessThan(1);
    expect(gamma[2].y).toBeGreaterThan(gamma[0].y);
    // On the Smith disc the same sample is OUTSIDE |Γ| = 1, which the chart
    // clips — marked clamped so the planner doesn't chase an invisible arc.
    const [smith] = sweepProjections(s, 50, {
      vswr: false,
      gamma: false,
      smith: true,
    });
    expect(smith[2].clamped).toBe(true);
    expect(smith[0].clamped).toBeUndefined();
  });

  it("adds points around the notch and skips the flat wings", () => {
    const freqs = Array.from({ length: 41 }, (_, i) => 13.5 + (i * 1.4) / 40);
    const got = refineSweepFreqs(notchSweep(freqs), 50, 12);
    expect(got.length).toBe(12);
    // Everything within a quarter of the span of the resonance at 14.2.
    for (const f of got) expect(Math.abs(f - 14.2)).toBeLessThan(0.35);
  });

  it("never re-proposes a frequency already sampled", () => {
    const freqs = Array.from({ length: 41 }, (_, i) => 13.5 + (i * 1.4) / 40);
    const s = notchSweep(freqs);
    const first = refineSweepFreqs(s, 50, 12);
    const merged = mergeSweepPoints(s, notchSweep(first));
    const second = refineSweepFreqs(merged, 50, 12);
    for (const f of second) expect(merged.freqs_mhz).not.toContain(f);
  });

  it("declines to plan for a sweep too short to have curvature", () => {
    expect(refineSweepFreqs(notchSweep([10, 11]), 50, 12)).toEqual([]);
  });

  // A constant-|Γ| phase rotation: VSWR and S11-dB are FLAT (both are
  // functions of |Γ| alone) while the Smith locus sweeps a wide arc — the
  // cleanest separator between "the scalar charts need points" and "only
  // the Smith chart does".
  function arcSweep(n = 41): SweepData {
    const freqs = Array.from({ length: n }, (_, i) => 10 + (i * 4) / (n - 1));
    const g = 0.6;
    return {
      freqs_mhz: freqs,
      // Γ = 0.6·e^{jθ}, θ swept non-uniformly so the arc has display-space
      // curvature variation worth refining. Z = z0(1+Γ)/(1−Γ).
      z_re: freqs.map((_f, i) => {
        const th = Math.PI * Math.pow(i / (n - 1), 2);
        const re = g * Math.cos(th);
        const im = g * Math.sin(th);
        const d = (1 - re) * (1 - re) + im * im;
        return (50 * (1 - re * re - im * im)) / d;
      }),
      z_im: freqs.map((_f, i) => {
        const th = Math.PI * Math.pow(i / (n - 1), 2);
        const re = g * Math.cos(th);
        const im = g * Math.sin(th);
        const d = (1 - re) * (1 - re) + im * im;
        return (50 * 2 * im) / d;
      }),
    };
  }

  it("residency filter: Smith-only curvature is skipped when Smith is not on screen (#763 follow-up era)", () => {
    const s = arcSweep();
    const withSmith = refineSweepFreqs(s, 50, 12, {
      vswr: true,
      gamma: true,
      smith: true,
    });
    const withoutSmith = refineSweepFreqs(s, 50, 12, {
      vswr: true,
      gamma: true,
      smith: false,
    });
    // The arc demands points for the Smith locus…
    expect(withSmith.length).toBeGreaterThan(0);
    // …and none at all once Smith is the only chart that would show them:
    // VSWR and S11 are constant for constant |Γ|.
    expect(withoutSmith).toEqual([]);
  });

  it("clamped vertices score zero: the corner where the curve meets the chart edge is not chased", () => {
    // A spike clipping through the VSWR ceiling: mid samples pinned at y=1.
    const freqs = Array.from({ length: 9 }, (_, i) => 14 + i * 0.05);
    const s: SweepData = {
      freqs_mhz: freqs,
      z_re: freqs.map(() => 50),
      // |X| huge in the middle third → VSWR far above 10, clamped flat.
      z_im: freqs.map((_, i) => (i >= 3 && i <= 5 ? 5000 : 100)),
    };
    const [vswr] = sweepProjections(s, 50);
    // The middle third really is clamped…
    expect(vswr[4].clamped).toBe(true);
    expect(vswr[4].y).toBe(1);
    // …and the planner assigns those vertices no deviation: only the VSWR
    // projection is offered, so any planned point must come from UNCLAMPED
    // vertices' deviations, never from sharpening the ceiling corner
    // between two clamped samples.
    const planned = planRefinement(freqs, [vswr], { budget: 8 });
    for (const f of planned) {
      // No midpoint may land strictly inside the clamped run (between
      // samples 3 and 5): both endpoints of those intervals are clamped
      // and their drawn segment is the ceiling regardless of the truth.
      expect(f < freqs[3] || f > freqs[5]).toBe(true);
    }
  });
});

describe("cut projection / refineCutAngles", () => {
  it("the radial map matches FarFieldChart's: −20 dBi at the origin, clamped", () => {
    const toFrac = cutDbiToFrac(10);
    expect(toFrac(-20)).toBe(0);
    expect(toFrac(10)).toBe(1);
    expect(toFrac(-5)).toBeCloseTo(0.5, 12);
    expect(toFrac(-999)).toBe(0); // below-horizon floor sentinel
    expect(toFrac(40)).toBe(1);
  });

  it("the radial top expands to fit the highest lobe, with 1 dB headroom", () => {
    // Nothing above the +10 dBi default ⇒ the chart's 1 dB headroom still
    // applies, exactly as FarFieldChart computes it.
    expect(cutDbiTop([2, 5])).toBe(11);
    expect(cutDbiTop([15.2])).toBe(17);
    expect(cutDbiTop([Infinity, 3])).toBe(11);
  });

  it("uniform cuts sit at t = 2π·i/n; explicit angles override that", () => {
    const dbi = [10, 10, 10, 10];
    const uniform = cutProjection(dbi, undefined, 10);
    expect(uniform[1].x).toBeCloseTo(0, 12);
    expect(uniform[1].y).toBeCloseTo(0.5, 12);
    const explicit = cutProjection(dbi, [0, 180, 270, 315], 10);
    expect(explicit[1].x).toBeCloseTo(-0.5, 12);
    expect(explicit[1].y).toBeCloseTo(0, 12);
  });

  it("densifies a multi-lobed cut's nulls and lowers its drawn error", () => {
    // Six lobes over the circle, sampled at 24 points — the nulls are where
    // the polar trace corners.
    const n = 24;
    const dbiAt = (deg: number) =>
      10 + 20 * Math.log10(Math.abs(Math.cos((6 * deg * Math.PI) / 180)) + 1e-3);
    const base = Array.from({ length: n }, (_, i) => dbiAt((360 * i) / n));
    const top = cutDbiTop([Math.max(...base)]);
    const before = maxChordDeviation(cutProjection(base, undefined, top), true);
    const added = refineCutAngles(base, undefined, top, 40);
    expect(added.length).toBeGreaterThan(0);
    for (const a of added) expect(a).toBeGreaterThanOrEqual(0);
    for (const a of added) expect(a).toBeLessThan(360);

    const angles = [
      ...Array.from({ length: n }, (_, i) => (360 * i) / n),
      ...added,
    ].sort((p, q) => p - q);
    const after = maxChordDeviation(
      cutProjection(angles.map(dbiAt), angles, top),
      true,
    );
    expect(after).toBeLessThan(before);
  });

  it("respects the budget and never re-proposes a held angle", () => {
    const n = 24;
    const base = Array.from({ length: n }, (_, i) =>
      10 + 20 * Math.log10(Math.abs(Math.cos((6 * ((360 * i) / n) * Math.PI) / 180)) + 1e-3),
    );
    const got = refineCutAngles(base, undefined, 10, 6);
    expect(got.length).toBeLessThanOrEqual(6);
    for (const a of got) expect(a % 15).not.toBe(0);
  });
});

describe("mergeSweepPoints", () => {
  const base: SweepData = {
    freqs_mhz: [10, 12, 14],
    z_re: [1, 2, 3],
    z_im: [-1, -2, -3],
  };

  it("re-sorts by frequency and keeps every row array index-aligned", () => {
    const extra: SweepData = {
      freqs_mhz: [13, 11],
      z_re: [30, 10],
      z_im: [-30, -10],
    };
    const m = mergeSweepPoints(base, extra);
    expect(m.freqs_mhz).toEqual([10, 11, 12, 13, 14]);
    expect(m.z_re).toEqual([1, 10, 2, 30, 3]);
    expect(m.z_im).toEqual([-1, -10, -2, -30, -3]);
    expect(m.feeds_z_re).toBeUndefined();
  });

  it("permutes the per-feed rows by the same ordering", () => {
    const bf: SweepData = {
      ...base,
      feeds_z_re: [[1, 101], [2, 102], [3, 103]],
      feeds_z_im: [[-1, -101], [-2, -102], [-3, -103]],
    };
    const extra: SweepData = {
      freqs_mhz: [13, 11],
      z_re: [30, 10],
      z_im: [-30, -10],
      feeds_z_re: [[30, 130], [10, 110]],
      feeds_z_im: [[-30, -130], [-10, -110]],
    };
    const m = mergeSweepPoints(bf, extra);
    expect(m.freqs_mhz).toEqual([10, 11, 12, 13, 14]);
    // Row i of every array describes freqs_mhz[i] — the invariant a chart
    // reading feeds_z_re[i] alongside freqs_mhz[i] depends on.
    expect(m.feeds_z_re).toEqual([
      [1, 101],
      [10, 110],
      [2, 102],
      [30, 130],
      [3, 103],
    ]);
    expect(m.feeds_z_im![3]).toEqual([-30, -130]);
  });

  it("drops per-feed rows rather than emit a half-populated array", () => {
    const bf: SweepData = {
      ...base,
      feeds_z_re: [[1], [2], [3]],
      feeds_z_im: [[-1], [-2], [-3]],
    };
    const m = mergeSweepPoints(bf, {
      freqs_mhz: [11],
      z_re: [10],
      z_im: [-10],
    });
    expect(m.freqs_mhz).toEqual([10, 11, 12, 14]);
    expect(m.feeds_z_re).toBeUndefined();
    expect(m.feeds_z_im).toBeUndefined();
  });

  it("is idempotent: an already-merged frequency keeps the held value", () => {
    const m1 = mergeSweepPoints(base, {
      freqs_mhz: [11],
      z_re: [10],
      z_im: [-10],
    });
    const m2 = mergeSweepPoints(m1, {
      freqs_mhz: [11],
      z_re: [999],
      z_im: [999],
    });
    expect(m2).toEqual(m1);
  });
});
