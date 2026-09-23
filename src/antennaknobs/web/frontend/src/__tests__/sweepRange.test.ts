// AK#1682: ONE range — the measurement dial's travel IS the sweep range —
// seeded by a fixed precedence (lib/sweep.ts header):
//   1 session edit > 2 file > 3 design ui_params > 4 sweep_policy > 5 default.
//
// The precedence tests go through `planSweepFreqs`, the function that exists
// on origin/main too, so each one that asserts NEW behaviour fails there on
// its assertion rather than on an import. The helpers that are new with
// AK#1682 are reached through the module namespace for the same reason: on
// main they are undefined, and only the tests that call them fail.
import { describe, it, expect } from "vitest";
import * as sweep from "../lib/sweep";
import type { BandSpec, ExampleDescriptor } from "../lib/params";
import { entry } from "./backendFixtures";

function makeExample(overrides: Partial<ExampleDescriptor> = {}): ExampleDescriptor {
  return {
    name: "dipoles.test",
    label: "Test Dipole",
    multi_feed: false,
    param_schema: [],
    result_schema: [],
    bands: [],
    meas_freq_range_mhz: null,
    default_view: null,
    default_freq: null,
    default_design_freq: null,
    default_backend: null,
    requires_backends: null,
    has_design_freq: true,
    variants: ["default"],
    variant_values: {},
    sweep_policy: { anchor: "design_freq", lo_factor: 0.8, hi_factor: 1.25 },
    ...overrides,
  };
}

const BAND_20M: BandSpec = { key: "20m", label: "20m", freq_mhz: 14.175, min_mhz: 14.0, max_mhz: 14.35 };
const BAND_40M: BandSpec = { key: "40m", label: "40m", freq_mhz: 7.15, min_mhz: 7.0, max_mhz: 7.3 };

// What the adapter serves for a deck with `FR 0 15 0 0 14.0 0.025` (see
// tests/test_sweep_range_1682.py): the file's range, grid and spacing.
const FILE_DECK = makeExample({
  has_design_freq: false,
  meas_freq_range_mhz: [14.0, 14.35],
  sweep_range: { lo: 14.0, hi: 14.35, spacing: "lin", step: 0.025, source: "file" },
});
// A Python design's ui_params["sweep_range"], log-spaced at 20 per decade.
const PY_RANGE = makeExample({
  sweep_range: { lo: 3, hi: 30, spacing: "log", points_per_decade: 20, source: "design" },
});
// A band-locked design (the catalog's sterba / owa_yagi shape).
const BAND_LOCKED = makeExample({
  sweep_policy: { anchor: "design_freq", lo_factor: 0.8, hi_factor: 1.25, band_locked: true },
});
// No policy of its own: the adapter serves the default.
const PLAIN = makeExample();

function params(overrides: Partial<Parameters<typeof sweep.planSweepFreqs>[0]> = {}) {
  return {
    backend: entry("bspline"),
    groundEnabled: false,
    groundModel: "fast" as const,
    currentExample: PLAIN,
    currentVariant: "default",
    measLocked: true,
    measFreq: 14.175,
    designFreq: 14.175,
    measBandAnchor: 14.175,
    currentBands: [BAND_20M, BAND_40M],
    freqWindowCeiling: 60,
    ...overrides,
  };
}

const EDIT: sweep.SweepRange = { lo: 10, hi: 11, spacing: "lin", step: 0.1 };

function expectLinear(freqs: number[], lo: number, hi: number, step: number) {
  expect(freqs[0]).toBeCloseTo(lo, 9);
  expect(freqs[freqs.length - 1]).toBeCloseTo(hi, 9);
  for (let i = 1; i < freqs.length; i++) {
    expect(freqs[i] - freqs[i - 1]).toBeCloseTo(step, 9);
  }
}

describe("sweep range precedence (AK#1682)", () => {
  it("level 2: a file design sweeps exactly its FR range, linear when the file is", () => {
    // NEW — on main the sweep ignores the file and runs ×0.8–×1.25 log.
    const freqs = sweep.planSweepFreqs(
      params({ currentExample: FILE_DECK, measLocked: false }),
    );
    expect(freqs).toHaveLength(15);
    expectLinear(freqs, 14.0, 14.35, 0.025);
  });

  it("level 2: the file's own grid is solved whether or not refinement is on", () => {
    // NEW — the entered grid is always solved; refinement only adds to it.
    for (const refineEnabled of [true, false]) {
      expect(
        sweep.planSweepFreqs(
          params({ currentExample: FILE_DECK, measLocked: false, refineEnabled }),
        ),
      ).toHaveLength(15);
    }
  });

  it("level 3: a design's ui_params.sweep_range is used, log at its density", () => {
    // NEW — on main a design has no way to set its sweep range.
    const freqs = sweep.planSweepFreqs(params({ currentExample: PY_RANGE }));
    expect(freqs).toHaveLength(21); // one decade at 20 per decade
    expect(freqs[0]).toBeCloseTo(3, 9);
    expect(freqs[freqs.length - 1]).toBeCloseTo(30, 9);
    const r = freqs[1] / freqs[0];
    for (let i = 1; i < freqs.length; i++) {
      expect(freqs[i] / freqs[i - 1]).toBeCloseTo(r, 9);
    }
    expect(r).toBeCloseTo(10 ** (1 / 20), 9);
  });

  it("level 3: a design's meas_freq_range (elt_whip) is now its sweep range too", () => {
    // NEW — on main it moved only the dial; the sweep ran 324.8–507.5.
    const elt = makeExample({ has_design_freq: false, meas_freq_range_mhz: [400, 412] });
    const freqs = sweep.planSweepFreqs(
      params({ currentExample: elt, measLocked: false, measFreq: 406, designFreq: 406, measBandAnchor: 406 }),
    );
    expect(freqs[0]).toBeCloseTo(400, 9);
    expect(freqs[freqs.length - 1]).toBeCloseTo(412, 9);
    expect(freqs).toHaveLength(17);
  });

  it("level 4: a sweep_policy design sweeps exactly what it swept before", () => {
    // UNCHANGED — passes on main too, by design.
    const freqs = sweep.planSweepFreqs(params({ currentExample: BAND_LOCKED }));
    expect(freqs).toHaveLength(17);
    expect(freqs[0]).toBeCloseTo(14.0, 9);
    expect(freqs[freqs.length - 1]).toBeCloseTo(14.35, 9);
    const r = freqs[1] / freqs[0];
    expect(r).toBeCloseTo((14.35 / 14.0) ** (1 / 16), 12);
  });

  it("level 5: a design with no policy gets ×0.8–×1.25 of the anchor, log", () => {
    // UNCHANGED — passes on main too.
    const freqs = sweep.planSweepFreqs(params({ designFreq: 14.1 }));
    expect(freqs).toHaveLength(17);
    expect(freqs[0]).toBeCloseTo(14.1 * 0.8, 9);
    expect(freqs[freqs.length - 1]).toBeCloseTo(14.1 * 1.25, 9);
  });

  it("an unlocked dial's window anchors on the selected band, not on the moving dial", () => {
    // NEW — on main the window followed measFreq, so it moved under the dial
    // that travels it. 7.29 is the dial dragged near the 40 m top edge.
    const freqs = sweep.planSweepFreqs(
      params({ measLocked: false, measFreq: 7.29, measBandAnchor: 7.15 }),
    );
    expect(freqs[0]).toBeCloseTo(7.15 * 0.8, 9);
    expect(freqs[freqs.length - 1]).toBeCloseTo(7.15 * 1.25, 9);
  });

  it("level 1: a session edit overrides every other level", () => {
    // NEW — main has no session range.
    for (const currentExample of [FILE_DECK, PY_RANGE, BAND_LOCKED, PLAIN]) {
      const freqs = sweep.planSweepFreqs(
        params({ currentExample, measLocked: false, sweepRangeEdit: EDIT }),
      );
      expect(freqs).toHaveLength(11);
      expectLinear(freqs, 10, 11, 0.1);
    }
  });

  it("↺ design range returns to whichever of levels 2–5 applies", () => {
    // NEW — resolveSweepRange / designSweepRange are AK#1682's.
    const cases: [ExampleDescriptor, sweep.SweepRangeLevel, number, number][] = [
      [FILE_DECK, "file", 14.0, 14.35],
      [PY_RANGE, "design", 3, 30],
      [BAND_LOCKED, "policy", 14.0, 14.35],
      [PLAIN, "default", 14.175 * 0.8, 14.175 * 1.25],
    ];
    for (const [currentExample, level, lo, hi] of cases) {
      const edited = sweep.resolveSweepRange(
        params({ currentExample, sweepRangeEdit: EDIT }),
      );
      expect(edited.level).toBe("session");
      // "↺ design range" clears the edit: the resolution lands on the level.
      const back = sweep.resolveSweepRange(
        params({ currentExample, sweepRangeEdit: null }),
      );
      expect(back.level).toBe(level);
      expect(back.range.lo).toBeCloseTo(lo, 9);
      expect(back.range.hi).toBeCloseTo(hi, 9);
      expect(sweep.designSweepRange(params({ currentExample, sweepRangeEdit: EDIT }))).toEqual(back);
    }
  });

  it("a custom measurement band replaces the file's absolute range, as it replaced the dial's", () => {
    const r = sweep.resolveSweepRange(
      params({
        currentExample: FILE_DECK,
        measLocked: false,
        measBandIsCustom: true,
        measBandAnchor: 300,
        freqWindowCeiling: 400,
      }),
    );
    expect(r.level).toBe("default");
    expect(r.range.lo).toBeCloseTo(240, 9);
    expect(r.range.hi).toBeCloseTo(375, 9);
  });
});

describe("the range menu's edits (AK#1682)", () => {
  const LOG: sweep.SweepRange = { lo: 10, hi: 100, spacing: "log" };

  it("the first edit materialises the density the grid was using", () => {
    // 17 default points over one decade = 16 per decade; moving lo keeps it.
    const next = sweep.editSweepRange(LOG, 17, { lo: 1 });
    expect(next).toEqual({ lo: 1, hi: 100, spacing: "log", pointsPerDecade: 16 });
    expect(sweep.sweepGrid(next!, 17).freqs).toHaveLength(33);
  });

  it("a spacing switch keeps the point count", () => {
    const lin = sweep.editSweepRange(LOG, 17, { spacing: "lin" })!;
    expect(lin).toEqual({ lo: 10, hi: 100, spacing: "lin", step: 90 / 16 });
    expect(sweep.sweepGrid(lin, 17).freqs).toHaveLength(17);
    const back = sweep.editSweepRange(lin, 17, { spacing: "log" })!;
    expect(back.pointsPerDecade).toBeCloseTo(16, 9);
    expect(back.step).toBeUndefined();
  });

  it("refuses an edit that is not a range", () => {
    expect(sweep.editSweepRange(LOG, 17, { lo: 200 })).toBeNull();
    expect(sweep.editSweepRange(LOG, 17, { lo: 0 })).toBeNull();
    expect(sweep.editSweepRange(EDIT, 11, { step: 0 })).toBeNull();
  });

  it("a step that does not divide the span still ends on hi", () => {
    const freqs = sweep.sweepGrid({ lo: 14, hi: 14.35, spacing: "lin", step: 0.1 }, 17).freqs;
    expect(freqs).toEqual([14, 14.1, 14.2, 14.3, 14.35].map((f) => expect.closeTo(f, 9)));
  });
});

describe("the hosted point cap (AK#1682)", () => {
  it("clamps a too-fine grid to MAX_SWEEP_POINTS and says so", () => {
    expect(sweep.MAX_SWEEP_POINTS).toBe(500);
    // 1 kHz over 1–30 MHz asks for 29 001 points.
    const fine: sweep.SweepRange = { lo: 1, hi: 30, spacing: "lin", step: 0.001 };
    const g = sweep.sweepGrid(fine, 17);
    expect(g.requested).toBe(29001);
    expect(g.clamped).toBe(true);
    expect(g.freqs).toHaveLength(500);
    expect(g.freqs[0]).toBe(1);
    expect(g.freqs[499]).toBe(30);
    // …and the sweep the session sends is the clamped one.
    const planned = sweep.planSweepFreqs(params({ sweepRangeEdit: fine }));
    expect(planned).toHaveLength(500);
  });

  it("leaves a grid at the cap alone", () => {
    const g = sweep.sweepGrid({ lo: 1, hi: 500, spacing: "lin", step: 1 }, 17);
    expect(g.clamped).toBe(false);
    expect(g.freqs).toHaveLength(500);
  });
});
