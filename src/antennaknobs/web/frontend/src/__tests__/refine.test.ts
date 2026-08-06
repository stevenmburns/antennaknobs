// The pure half of adaptive refinement (issue #744): where extra samples
// go, decided from display-space curvature. Everything here is
// input-in/values-out — no fetch, no React, no canvas — so the criterion
// itself is pinned independently of the transport that carries it.
import { describe, it, expect } from "vitest";
import {
  KINK_TOLERANCE_RAD,
  MIN_SEGMENT,
  cutDbiToFrac,
  cutDbiTop,
  cutProjection,
  maxKinkRad,
  planRefinement,
  refineCutAngles,
  refineSweepFreqs,
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

  it("never re-splits an interval already below the display floor", () => {
    // A right-angle corner whose left arm is already sub-pixel: interval
    // [1,2] carries the full 90° kink but is shorter than MIN_SEGMENT, so
    // splitting it can never change what is drawn.
    const step: DisplayPoint[] = [
      { x: 0, y: 0 },
      { x: 0.5, y: 0 },
      { x: 0.5 + MIN_SEGMENT / 4, y: 0 },
      { x: 0.5 + MIN_SEGMENT / 4, y: 1 },
    ];
    const got = planRefinement([0, 1, 2, 3], [step], { budget: 100 });
    // Terminates strictly inside the budget instead of grinding the corner
    // forever, and never touches the sub-pixel interval [1,2] itself.
    expect(got.length).toBeLessThan(100);
    for (const v of got) expect(v > 1 && v < 2).toBe(false);
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

  it("refinement provably lowers the worst kink on a smooth curve", () => {
    // Sample a Lorentzian-shaped notch coarsely, then at the refined
    // parameter set, and compare the rendered polylines' worst corner.
    const yOf = (f: number) => 1 - 1 / (1 + 400 * (f - 0.5) * (f - 0.5));
    const ptsOf = (fs: number[]) => fs.map((f) => ({ x: f, y: yOf(f) }));
    const coarse = Array.from({ length: 21 }, (_, i) => i / 20);
    const before = maxKinkRad(ptsOf(coarse));
    const added = planRefinement(coarse, [ptsOf(coarse)], { budget: 24 });
    const after = maxKinkRad(ptsOf([...coarse, ...added].sort((a, b) => a - b)));
    expect(before).toBeGreaterThan(KINK_TOLERANCE_RAD);
    expect(after).toBeLessThan(before);
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

  it("densifies a multi-lobed cut's nulls and lowers its worst corner", () => {
    // Six lobes over the circle, sampled at 24 points — the nulls are where
    // the polar trace corners.
    const n = 24;
    const dbiAt = (deg: number) =>
      10 + 20 * Math.log10(Math.abs(Math.cos((6 * deg * Math.PI) / 180)) + 1e-3);
    const base = Array.from({ length: n }, (_, i) => dbiAt((360 * i) / n));
    const top = cutDbiTop([Math.max(...base)]);
    const before = maxKinkRad(cutProjection(base, undefined, top), true);
    const added = refineCutAngles(base, undefined, top, 40);
    expect(added.length).toBeGreaterThan(0);
    for (const a of added) expect(a).toBeGreaterThanOrEqual(0);
    for (const a of added) expect(a).toBeLessThan(360);

    const angles = [
      ...Array.from({ length: n }, (_, i) => (360 * i) / n),
      ...added,
    ].sort((p, q) => p - q);
    const after = maxKinkRad(
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
