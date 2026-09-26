// The Z-vs-parameter view's pure half (lib/paramSweep.ts): the ladder a spec
// asks for, which knobs sweep, and the chart's axis rules.
import { describe, it, expect } from "vitest";
import {
  autoRxDomain,
  clampPoints,
  DEFAULT_DENSITY_SPEC,
  defaultKnobSpec,
  DENSITY,
  DENSITY_LADDER,
  logTicks,
  nearestIndex,
  paramRichardson,
  paramValues,
  rxDomain,
  rxTicks,
  sweepableKnobs,
  validRxChoice,
  xDomain,
  xFraction,
  xTicks,
  formatOhm,
  formatParam,
} from "../lib/paramSweep";
import type { SchemaItem, SchemaParamSpec } from "../lib/params";

const knob = (over: Partial<SchemaParamSpec>): SchemaParamSpec => ({
  name: "length_factor",
  label: "length factor",
  default: 1,
  kind: "float",
  min: 0.8,
  max: 1.25,
  step: 0.001,
  precision: 3,
  unit: null,
  visible_when: null,
  ...over,
});

describe("the density ladder", () => {
  it("is the old switch's literal ladder by default (the CLI's too)", () => {
    expect(paramValues(DEFAULT_DENSITY_SPEC, true)).toEqual([8, 12, 17, 24, 34, 48, 68]);
    expect(DENSITY_LADDER).toEqual([8, 12, 17, 24, 34, 48, 68]);
  });

  it("is geometric and integer otherwise: Dan's 10…500 × 20 (SimNEC logStep)", () => {
    const v = paramValues({ param: DENSITY, lo: 10, hi: 500, points: 20, log: true }, true);
    // numpy: sorted({round(x) for x in geomspace(10, 500, 20)})
    expect(v).toEqual([
      10, 12, 15, 19, 23, 28, 34, 42, 52, 64, 78, 96, 118, 145, 179, 219, 270, 331, 407, 500,
    ]);
    expect(v.every(Number.isInteger)).toBe(true);
  });

  it("drops the duplicates rounding makes at a coarse end", () => {
    const v = paramValues({ param: DENSITY, lo: 1, hi: 4, points: 10, log: true }, true);
    expect(v).toEqual([1, 2, 3, 4]);
  });

  it("never goes below one segment", () => {
    const v = paramValues({ param: DENSITY, lo: 0, hi: 4, points: 5, log: false }, true);
    expect(v).toEqual([1, 2, 3, 4]);
  });
});

describe("a knob's ladder", () => {
  it("is linear from its min to its max by default", () => {
    const spec = defaultKnobSpec(knob({}), 0.97);
    expect(spec).toEqual({ param: "length_factor", lo: 0.8, hi: 1.25, points: 11, log: false });
    const v = paramValues(spec, false);
    expect(v).toHaveLength(11);
    expect(v[0]).toBe(0.8);
    expect(v[10]).toBe(1.25);
    expect(v[1]).toBeCloseTo(0.845, 12);
  });

  it("spans ±20 % of its value when the knob declares no range", () => {
    const spec = defaultKnobSpec(knob({ min: null, max: null }), 10);
    expect([spec.lo, spec.hi]).toEqual([8, 12]);
  });

  it("rounds an int knob and drops duplicates", () => {
    const spec = { param: "n_directors", lo: 0, hi: 3, points: 11, log: false };
    expect(paramValues(spec, true)).toEqual([0, 1, 2, 3]);
  });

  it("falls back to linear when a log ladder would cross zero", () => {
    const spec = { param: "x", lo: -1, hi: 1, points: 3, log: true };
    expect(paramValues(spec, false)).toEqual([-1, 0, 1]);
  });

  it("clamps the point count to 2…41", () => {
    expect(clampPoints(1)).toBe(2);
    expect(clampPoints(100)).toBe(41);
    expect(clampPoints(Number.NaN)).toBe(2);
    expect(paramValues({ param: "x", lo: 0, hi: 1, points: 500, log: false }, false)).toHaveLength(41);
  });
});

describe("which knobs sweep", () => {
  it("takes visible float/int knobs that set no frequency", () => {
    const schema: SchemaItem[] = [
      knob({}),
      knob({ name: "n", label: "n", kind: "int" }),
      knob({ name: "design_freq", linked_to_design_freq: true }),
      knob({ name: "freq" }),
      knob({ name: "f_band", link_meas_freq_to_param: "f_band" }),
      knob({ name: "mode", kind: "enum" }),
      knob({ name: "on", kind: "bool" }),
      { name: "bands", label: "bands", kind: "group", params: [] } as unknown as SchemaItem,
    ];
    expect(sweepableKnobs(schema).map((k) => k.name)).toEqual(["length_factor", "n"]);
  });
});

describe("Richardson", () => {
  it("is density-only, and null until three points are in", () => {
    const ns = [8, 12, 17];
    const re = ns.map((n) => 70 + 10 / n);
    expect(paramRichardson(DENSITY, ns.slice(0, 2), re, re).re).toBeNull();
    expect(paramRichardson(DENSITY, ns, re, re).re).toBeCloseTo(70, 9);
    expect(paramRichardson("length_factor", ns, re, re)).toEqual({ re: null, im: null });
  });
});

describe("the chart's axes", () => {
  it("Auto fits the trace with headroom, and never narrower than 0.02 Ω", () => {
    const d = autoRxDomain([72.0, 72.15]);
    expect(d.lo).toBeLessThan(72.0);
    expect(d.hi).toBeGreaterThan(72.15);
    expect(d.hi - d.lo).toBeCloseTo(0.15 * 1.16, 9);
    const flat = autoRxDomain([50, 50.001]);
    expect(flat.hi - flat.lo).toBeGreaterThanOrEqual(0.02);
    expect(autoRxDomain([])).toEqual({ lo: 0, hi: 1 });
  });

  it("a fixed range is the viewer's, and must be a real span", () => {
    expect(rxDomain({ kind: "fixed", lo: 70, hi: 73 }, [1, 2])).toEqual({ lo: 70, hi: 73 });
    expect(validRxChoice({ kind: "fixed", lo: 2, hi: 1 })).toBe(false);
    expect(validRxChoice({ kind: "fixed", lo: 1, hi: Number.NaN })).toBe(false);
    expect(validRxChoice({ kind: "auto" })).toBe(true);
  });

  it("y ticks sit on the step grid (no padded floor tick)", () => {
    const t = rxTicks({ lo: 71.97, hi: 72.16 });
    expect(t[0]).toBeGreaterThan(71.97);
    const step = t[1] - t[0];
    expect(Math.abs(t[0] / step - Math.round(t[0] / step))).toBeLessThan(1e-6);
  });

  it("a log x axis labels 1-2-5 per decade (10 20 50 100 200 500)", () => {
    expect(logTicks({ lo: 10, hi: 500 })).toEqual([10, 20, 50, 100, 200, 500]);
    expect(xTicks({ lo: 8, hi: 68 }, true)).toEqual([10, 20, 50]);
    // Linear, or a span log cannot draw: linear ticks.
    expect(xTicks({ lo: 0.8, hi: 1.25 }, false).length).toBeGreaterThan(2);
    expect(xTicks({ lo: -1, hi: 1 }, true)).toContain(0);
  });

  it("places values in log or linear x", () => {
    const d = xDomain([10, 1000]);
    expect(xFraction(d, true)(100)).toBeCloseTo(0.5, 12);
    expect(xFraction(d, false)(505)).toBeCloseTo(0.5, 12);
    // A single value gets a unit span around it.
    expect(xDomain([5])).toEqual({ lo: 4.5, hi: 5.5 });
  });

  it("hover lands on the nearest point", () => {
    const xs = [8, 12, 17, 24, 34, 48, 68];
    const f = xFraction(xDomain(xs), true);
    expect(nearestIndex(xs, f, 0)).toBe(0);
    expect(nearestIndex(xs, f, 1)).toBe(6);
    expect(nearestIndex(xs, f, f(23))).toBe(3);
    expect(nearestIndex([], f, 0.5)).toBe(-1);
  });

  it("formats values for the value boxes", () => {
    expect(formatParam(68)).toBe("68");
    expect(formatParam(0.84500000001)).toBe("0.845");
    expect(formatOhm(72.153)).toBe("72.15");
    expect(formatOhm(-0.4619)).toBe("−0.462");
    expect(formatOhm(125.06)).toBe("125.1");
  });
});
