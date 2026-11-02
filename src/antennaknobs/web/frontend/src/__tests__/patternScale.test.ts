import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULT_PATTERN_SCALE,
  getPatternScale,
  PATTERN_SCALE_KEY,
  setPatternScale,
} from "../lib/patternScale";
import {
  ARRL_DEPTH_DB,
  CUT_DBI_FLOOR,
  cutDbiToFrac,
  cutProjection,
  cutRingsDbi,
} from "../lib/refine";

// The polar pattern charts' ARRL radial scale (AC6LA, 2026-11-02):
// r = R_max * 0.89^(-dB/3), dB measured down from the top of the scale.

describe("the ARRL radial map", () => {
  const top = 10;
  const toFrac = cutDbiToFrac(top, "arrl");

  it("puts the top on the rim and each 3 dB down at 0.89 of the last", () => {
    expect(toFrac(top)).toBeCloseTo(1, 12);
    expect(toFrac(top - 3)).toBeCloseTo(0.89, 12);
    expect(toFrac(top - 6)).toBeCloseTo(0.89 ** 2, 12);
    expect(toFrac(top - 30)).toBeCloseTo(0.89 ** 10, 12);
  });

  it("matches the grid's own description: the first 3 dB step is about a tenth of the radius", () => {
    expect(1 - toFrac(top - 3)).toBeCloseTo(0.11, 12);
    // and each later 3 dB step is 89 % of the one before
    const step = (k: number) => toFrac(top - 3 * k) - toFrac(top - 3 * (k + 1));
    expect(step(1) / step(0)).toBeCloseTo(0.89, 12);
    expect(step(5) / step(4)).toBeCloseTo(0.89, 12);
  });

  it("has no floor: -100 dB is near the centre, not on it, and nothing leaves the rim", () => {
    expect(toFrac(top - ARRL_DEPTH_DB)).toBeCloseTo(0.89 ** (100 / 3), 12);
    expect(toFrac(top - ARRL_DEPTH_DB)).toBeLessThan(0.025);
    expect(toFrac(top + 5)).toBe(1);
  });

  it("leaves the linear map as it was", () => {
    const lin = cutDbiToFrac(top);
    expect(lin(CUT_DBI_FLOOR)).toBe(0);
    expect(lin(top)).toBe(1);
    expect(lin((top + CUT_DBI_FLOOR) / 2)).toBeCloseTo(0.5, 12);
    expect(cutDbiToFrac(top, "linear")(0)).toBe(lin(0));
  });
});

describe("the rings", () => {
  it("ARRL rings sit 0, 3, 6, 10, 20 and 30 dB down, labelled in dBi", () => {
    expect(cutRingsDbi(11, "arrl")).toEqual([11, 8, 5, 1, -9, -19]);
  });

  it("linear keeps its fixed dBi rings", () => {
    expect(cutRingsDbi(11)).toEqual([6, 0, -6, -12, -18]);
    expect(cutRingsDbi(11, "linear")).toEqual([6, 0, -6, -12, -18]);
  });
});

describe("the refinement projection follows the scale", () => {
  it("draws the same radius the chart does, and marks the rim and the centre as clamped", () => {
    const top = 10;
    const dbi = [top, top - 3, top - 200];
    const pts = cutProjection(dbi, [0, 90, 180], top, "arrl");
    // Display units: plot extent 1, so the rim is radius 0.5.
    expect(Math.hypot(pts[1].x, pts[1].y)).toBeCloseTo(0.5 * 0.89, 12);
    expect(pts[0].clamped).toBe(true);
    expect(pts[1].clamped).toBeUndefined();
    expect(pts[2].clamped).toBe(true);
  });
});

describe("the setting", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => {
    setPatternScale(DEFAULT_PATTERN_SCALE);
    localStorage.clear();
  });

  it("defaults to ARRL", () => {
    expect(DEFAULT_PATTERN_SCALE).toBe("arrl");
    expect(getPatternScale()).toBe("arrl");
  });

  it("stores only a choice that differs from the default", () => {
    setPatternScale("linear");
    expect(getPatternScale()).toBe("linear");
    expect(localStorage.getItem(PATTERN_SCALE_KEY)).toBe("linear");
    setPatternScale("arrl");
    expect(getPatternScale()).toBe("arrl");
    expect(localStorage.getItem(PATTERN_SCALE_KEY)).toBeNull();
  });
});
