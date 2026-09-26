// AK#1738: the sweep charts' range rules and the SWR bandwidth readout
// (lib/sweepAxis.ts), on synthetic curves whose answers are known.
import { describe, it, expect } from "vitest";
import {
  autoS11Floor,
  axisTicks,
  bandwidthReadout,
  primaryBand,
  s11DbForSwr,
  sanitizeChoice,
  sanitizeThreshold,
  sweepAxisDomain,
  swrBands,
  widenDomain,
} from "../lib/sweepAxis";

describe("S11 Auto: the shallowest nice floor that holds the dip with headroom", () => {
  it("S11: every Auto floor holds the threshold's line; a tight one deepens it", () => {
    // 5:1 is −3.5 dB and 20:1 −0.9 dB: above every floor (≤ −10), no change.
    expect(autoS11Floor([-3], 5)).toBe(-10);
    expect(autoS11Floor([-3], 20)).toBe(-10);
    // 1.1:1 is −26.4 dB: a −3 dB dip alone picks −10, the line needs −30.
    expect(autoS11Floor([-3], 1.1)).toBe(-30);
    expect(sweepAxisDomain("gamma", { kind: "auto" }, [-3], 0, 1.1)).toEqual({ lo: -30, hi: 0 });
  });

  it("S11: the dip clears the floor by 5 dB, mirrored onto the moving floor", () => {
    expect(autoS11Floor([-3, -1])).toBe(-10);
    expect(autoS11Floor([-5])).toBe(-10);
    expect(autoS11Floor([-5.1])).toBe(-20);
    expect(autoS11Floor([-25])).toBe(-30);
    expect(autoS11Floor([-26])).toBe(-40);
    expect(autoS11Floor([-80])).toBe(-60); // the deepest floor; below clamps
    expect(autoS11Floor([])).toBe(-30);
  });

  it("sweepAxisDomain: presets, custom ranges and the over-unity S11 top", () => {
    // VSWR has no Auto: one (an old profile's) draws as the 1–∞ scale.
    expect(sweepAxisDomain("vswr", { kind: "auto" }, [1.1])).toEqual({ lo: 0, hi: 1 });
    // A fixed range is the viewer's: the threshold does not move it.
    expect(sweepAxisDomain("vswr", { kind: "fixed", lo: 1, hi: 1.5 }, [1.1], 0, 3)).toEqual({ lo: 1, hi: 1.5 });
    expect(sweepAxisDomain("vswr", { kind: "fixed", lo: 1, hi: 3 }, [1.1])).toEqual({ lo: 1, hi: 3 });
    // A preset floor keeps the S11 top's growth for an over-unity port...
    expect(sweepAxisDomain("gamma", { kind: "fixed", lo: -20, hi: 0 }, [-3], 2)).toEqual({ lo: -20, hi: 2 });
    // ...a custom top is the viewer's, and a sample above it pegs.
    expect(sweepAxisDomain("gamma", { kind: "fixed", lo: -20, hi: -5 }, [-3], 2)).toEqual({ lo: -20, hi: -5 });
    expect(sweepAxisDomain("gamma", { kind: "auto" }, [-12], 0)).toEqual({ lo: -20, hi: 0 });
  });

  it("widenDomain is the union, so a held range never shrinks", () => {
    expect(widenDomain(null, { lo: 1, hi: 2 })).toEqual({ lo: 1, hi: 2 });
    expect(widenDomain({ lo: 1, hi: 5 }, { lo: 1, hi: 2 })).toEqual({ lo: 1, hi: 5 });
    expect(widenDomain({ lo: -20, hi: 0 }, { lo: -40, hi: 0 })).toEqual({ lo: -40, hi: 0 });
  });

  it("axisTicks: the old fixed scales' ticks, and readable ones for the new ranges", () => {
    expect(axisTicks({ lo: 1, hi: 10 })).toEqual([1, 2, 4, 6, 8, 10]);
    expect(axisTicks({ lo: -30, hi: 0 })).toEqual([-30, -20, -10, 0]);
    expect(axisTicks({ lo: 1, hi: 2 })).toEqual([1, 1.2, 1.4, 1.6, 1.8, 2]);
    expect(axisTicks({ lo: 1, hi: 3 })).toEqual([1, 1.5, 2, 2.5, 3]);
    expect(axisTicks({ lo: 1, hi: 100 })).toEqual([1, 20, 40, 60, 80, 100]);
  });
});

describe("swrBands: the 2:1 bandwidth, interpolated between samples", () => {
  // A V of slope 20 SWR/MHz with its point at 7.1 MHz: below 2:1 exactly
  // from 7.05 to 7.15 — a 100 kHz band. Sampled every 30 kHz from 6.98, so
  // neither crossing is a sample (nearest samples: 7.04/7.07 and 7.13/7.16).
  const v = (f: number) => 1 + 20 * Math.abs(f - 7.1);
  const grid = (lo: number, step: number, n: number) =>
    Array.from({ length: n }, (_, i) => lo + i * step);

  it("finds the crossings on the drawn segments, not at the nearest samples", () => {
    const f = grid(6.98, 0.03, 9); // 6.98 … 7.22
    const bands = swrBands(f, f.map(v), 2);
    expect(bands).toHaveLength(1);
    expect(bands[0].lo).toBeCloseTo(7.05, 9);
    expect(bands[0].hi).toBeCloseTo(7.15, 9);
    expect(bands[0].openLo || bands[0].openHi).toBe(false);
    expect(bandwidthReadout(bands, 7.1, 2)).toBe("2:1 BW 100 kHz");
    // Snapping to the in-band samples would have said 7.07–7.13 = 60 kHz.
  });

  it("follows the threshold: 3:1 on the same V is 200 kHz", () => {
    const f = grid(6.98, 0.03, 9);
    const [b] = swrBands(f, f.map(v), 3);
    expect(b.hi - b.lo).toBeCloseTo(0.2, 9);
    expect(bandwidthReadout([b], 7.1, 3)).toBe("3:1 BW 200 kHz");
  });

  it("no crossing: nothing below the line reads 'none'", () => {
    const f = grid(6.98, 0.03, 9);
    const bands = swrBands(f, f.map((x) => 2 + v(x)), 2);
    expect(bands).toEqual([]);
    expect(primaryBand(bands, 7.1)).toBeNull();
    expect(bandwidthReadout(bands, 7.1, 2)).toBe("2:1 BW none");
  });

  it("a dip at the sweep's edge is an open band, read as a lower bound", () => {
    // The V's point sits at the sweep's first sample, 7.1: the curve starts
    // below 2:1 and crosses at 7.15. The band may extend below the sweep.
    const f = grid(7.1, 0.03, 5); // 7.10 … 7.22
    const bands = swrBands(f, f.map(v), 2);
    expect(bands).toEqual([
      { lo: 7.1, hi: expect.closeTo(7.15, 9), openLo: true, openHi: false },
    ]);
    expect(bandwidthReadout(bands, 7.12, 2)).toBe("2:1 BW ≥50 kHz");
  });

  it("the whole sweep below the line is open at both ends", () => {
    const f = grid(7.0, 0.05, 5);
    const bands = swrBands(f, f.map(() => 1.2), 2);
    expect(bands).toEqual([{ lo: 7.0, hi: 7.2, openLo: true, openHi: true }]);
  });

  it("two separate dips are two bands; the readout names the one at the operating frequency", () => {
    // Two V's: a narrow one at 7.05 (slope 40 → 50 kHz wide) and a wide one
    // at 7.25 (slope 10 → 200 kHz wide), with a peak between.
    const w = (f: number) =>
      Math.min(1 + 40 * Math.abs(f - 7.05), 1 + 10 * Math.abs(f - 7.25));
    const f = grid(6.99, 0.007, 60); // 6.99 … 7.403, no sample on a crossing
    const bands = swrBands(f, f.map(w), 2);
    expect(bands).toHaveLength(2);
    expect(bands[0].lo).toBeCloseTo(7.025, 9);
    expect(bands[0].hi).toBeCloseTo(7.075, 9);
    expect(bands[1].lo).toBeCloseTo(7.15, 9);
    expect(bands[1].hi).toBeCloseTo(7.35, 9);
    // At the narrow dip: that band, never the two summed.
    expect(bandwidthReadout(bands, 7.05, 2)).toBe("2:1 BW 50 kHz (1 of 2)");
    // At the wide one: that band.
    expect(bandwidthReadout(bands, 7.3, 2)).toBe("2:1 BW 200 kHz (1 of 2)");
    // Between them (the operating frequency in neither): the widest.
    expect(bandwidthReadout(bands, 7.1, 2)).toBe("2:1 BW 200 kHz (1 of 2)");
  });

  it("a sample exactly at the threshold is not below it", () => {
    const bands = swrBands([1, 2, 3], [2, 1.5, 2], 2);
    expect(bands).toEqual([{ lo: 1, hi: 3, openLo: false, openHi: false }]);
  });

  it("spans of a megahertz or more read in MHz", () => {
    const bands = swrBands([10, 11, 12, 13], [3, 1.5, 1.5, 3], 2);
    // Crossings at 10 + 1/1.5 and 12 + 0.5/1.5: 10.667 to 12.333.
    expect(bandwidthReadout(bands, 11.5, 2)).toBe("2:1 BW 1.667 MHz");
  });

  it("the S11 line matches the SWR threshold: 2:1 is −9.54 dB", () => {
    expect(s11DbForSwr(2)).toBeCloseTo(-9.542, 3);
    expect(s11DbForSwr(1.5)).toBeCloseTo(-13.979, 3);
  });
});

describe("stored choices are distrusted", () => {
  it("anything undrawable reads as the mode's default; the threshold falls back to 2", () => {
    expect(sanitizeChoice("vswr", { kind: "fixed", lo: 1, hi: 3 })).toEqual({ kind: "fixed", lo: 1, hi: 3 });
    // VSWR's default is the 1–∞ scale, S11's is Auto.
    expect(sanitizeChoice("vswr", { kind: "fixed", lo: 0.5, hi: 3 })).toEqual({ kind: "reciprocal" });
    expect(sanitizeChoice("gamma", { kind: "fixed", lo: -10, hi: -20 })).toEqual({ kind: "auto" });
    expect(sanitizeChoice("gamma", "garbage")).toEqual({ kind: "auto" });
    expect(sanitizeThreshold(3)).toBe(3);
    expect(sanitizeThreshold(0.5)).toBe(2);
    expect(sanitizeThreshold("x")).toBe(2);
  });
});
