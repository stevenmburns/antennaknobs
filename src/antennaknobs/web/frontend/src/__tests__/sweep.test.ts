// Pins the pure sweep-frequency plan in src/lib/sweep.ts (issue #642 PR
// 5b-1), extracted verbatim from DesignSession's runSweep.
import { describe, it, expect } from "vitest";
import { planSweepFreqs } from "../lib/sweep";
import type { BandSpec, ExampleDescriptor } from "../lib/params";
import { backendEntry, entry } from "./backendFixtures";

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

const BAND_20M: BandSpec = { key: "20m", label: "20 m", freq_mhz: 14.15, min_mhz: 14.0, max_mhz: 14.35 };

// Base params for a "plain HF, not band-locked, plenty of ceiling" sweep;
// individual tests override just the fields under study.
function baseParams(overrides: Partial<Parameters<typeof planSweepFreqs>[0]> = {}) {
  return {
    backend: entry("bspline"),
    groundEnabled: false,
    groundModel: "fast" as const,
    currentExample: makeExample(),
    currentVariant: "default",
    measLocked: true,
    measFreq: 7.1,
    designFreq: 14.1,
    currentBands: [] as BandSpec[],
    freqWindowCeiling: 200,
    ...overrides,
  };
}

describe("planSweepFreqs", () => {
  it("uses 41 points when ground is off or the model isn't Sommerfeld", () => {
    expect(planSweepFreqs(baseParams())).toHaveLength(41);
    expect(
      planSweepFreqs(baseParams({ groundEnabled: true, groundModel: "fast" })),
    ).toHaveLength(41);
  });

  it("halves to 21 points for a ground-capable backend on Sommerfeld ground", () => {
    expect(
      planSweepFreqs(
        baseParams({ backend: entry("bspline"), groundEnabled: true, groundModel: "sommerfeld" }),
      ),
    ).toHaveLength(21);
  });

  it("stays at 41 points on Sommerfeld ground if the backend doesn't support ground", () => {
    // Every backend the server registers supports ground; a roster entry
    // carrying supports_ground: false exercises the branch (issue #628).
    const freqs = planSweepFreqs(
      baseParams({
        backend: backendEntry({ name: "future-solver", supports_ground: false }),
        groundEnabled: true,
        groundModel: "sommerfeld",
      }),
    );
    expect(freqs).toHaveLength(41);
  });

  it("anchors on designFreq when locked and the policy anchor is 'design_freq' (the default)", () => {
    const freqs = planSweepFreqs(
      baseParams({
        currentExample: makeExample({
          sweep_policy: { anchor: "design_freq", lo_factor: 0.8, hi_factor: 1.25 },
        }),
        measLocked: true,
        measFreq: 7.1,
        designFreq: 14.1,
      }),
    );
    expect(freqs[0]).toBeCloseTo(14.1 * 0.8, 9);
    expect(freqs[freqs.length - 1]).toBeCloseTo(14.1 * 1.25, 9);
  });

  it("anchors on measFreq when the policy declares anchor 'meas_freq', even while locked", () => {
    const freqs = planSweepFreqs(
      baseParams({
        currentExample: makeExample({
          sweep_policy: { anchor: "meas_freq", lo_factor: 0.8, hi_factor: 1.25 },
        }),
        measLocked: true,
        measFreq: 7.1,
        designFreq: 14.1,
      }),
    );
    expect(freqs[0]).toBeCloseTo(7.1 * 0.8, 9);
    expect(freqs[freqs.length - 1]).toBeCloseTo(7.1 * 1.25, 9);
  });

  it("anchors on measFreq when unlocked, overriding an anchor:'design_freq' policy", () => {
    const freqs = planSweepFreqs(
      baseParams({
        currentExample: makeExample({
          sweep_policy: { anchor: "design_freq", lo_factor: 0.8, hi_factor: 1.25 },
        }),
        measLocked: false,
        measFreq: 7.1,
        designFreq: 14.1,
      }),
    );
    expect(freqs[0]).toBeCloseTo(7.1 * 0.8, 9);
    expect(freqs[freqs.length - 1]).toBeCloseTo(7.1 * 1.25, 9);
  });

  it("prefers the active variant's sweep_policy over the design-level one", () => {
    const ex = makeExample({
      sweep_policy: { anchor: "design_freq", lo_factor: 0.8, hi_factor: 1.25 },
      variant_ui: {
        longwire: { sweep_policy: { anchor: "design_freq", lo_factor: 0.5, hi_factor: 2 } },
      },
    });
    const freqs = planSweepFreqs(
      baseParams({ currentExample: ex, currentVariant: "longwire", designFreq: 10 }),
    );
    expect(freqs[0]).toBeCloseTo(10 * 0.5, 9);
    expect(freqs[freqs.length - 1]).toBeCloseTo(10 * 2, 9);
  });

  it("snaps to the containing band's [min_mhz, max_mhz] when band_locked and the anchor is in-band", () => {
    const freqs = planSweepFreqs(
      baseParams({
        currentExample: makeExample({
          sweep_policy: { anchor: "design_freq", lo_factor: 0.8, hi_factor: 1.25, band_locked: true },
        }),
        designFreq: 14.1,
        currentBands: [BAND_20M],
      }),
    );
    expect(freqs[0]).toBeCloseTo(14.0, 9);
    expect(freqs[freqs.length - 1]).toBeCloseTo(14.35, 9);
  });

  it("falls through to the multiplicative window when band_locked but the anchor is outside every band", () => {
    const freqs = planSweepFreqs(
      baseParams({
        currentExample: makeExample({
          sweep_policy: { anchor: "design_freq", lo_factor: 0.8, hi_factor: 1.25, band_locked: true },
        }),
        designFreq: 50,
        currentBands: [BAND_20M],
        freqWindowCeiling: 200,
      }),
    );
    expect(freqs[0]).toBeCloseTo(50 * 0.8, 9);
    expect(freqs[freqs.length - 1]).toBeCloseTo(50 * 1.25, 9);
  });

  it("clamps the low end to a 0.5 MHz floor", () => {
    const freqs = planSweepFreqs(
      baseParams({
        currentExample: makeExample({
          sweep_policy: { anchor: "design_freq", lo_factor: 0.8, hi_factor: 1.25 },
        }),
        designFreq: 0.4, // 0.4 * 0.8 = 0.32, below the 0.5 floor
      }),
    );
    expect(freqs[0]).toBeCloseTo(0.5, 9);
  });

  it("clamps the high end to freqWindowCeiling", () => {
    const freqs = planSweepFreqs(
      baseParams({
        currentExample: makeExample({
          sweep_policy: { anchor: "design_freq", lo_factor: 0.8, hi_factor: 1.25 },
        }),
        designFreq: 100, // 100 * 1.25 = 125, above a 60 MHz ceiling
        freqWindowCeiling: 60,
      }),
    );
    expect(freqs[freqs.length - 1]).toBeCloseTo(60, 9);
  });

  it("log-spaces the interior points between fLo and fHi", () => {
    const freqs = planSweepFreqs(
      baseParams({
        currentExample: makeExample({
          sweep_policy: { anchor: "design_freq", lo_factor: 0.8, hi_factor: 1.25 },
        }),
        designFreq: 14.1,
      }),
    );
    const fLo = 14.1 * 0.8;
    const fHi = 14.1 * 1.25;
    expect(freqs[0]).toBeCloseTo(fLo, 9);
    expect(freqs[freqs.length - 1]).toBeCloseTo(fHi, 9);
    // Consecutive ratios are constant under log-spacing.
    const ratio = freqs[1] / freqs[0];
    for (let i = 1; i < freqs.length; i++) {
      expect(freqs[i] / freqs[i - 1]).toBeCloseTo(ratio, 9);
    }
    expect(ratio).toBeCloseTo(Math.pow(fHi / fLo, 1 / (freqs.length - 1)), 9);
  });
});
