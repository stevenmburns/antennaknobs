// A knob's family of patterns (AK#1935), React-free: when the knob chart
// offers it, what entering and leaving it sets, the step cross it becomes
// (labels as the CLI's `step_label`), the step-size rule and the cap.
// The session's half is patternFamily.session.test.tsx.
import { describe, it, expect } from "vitest";
import {
  chartDwell,
  chartFamily,
  chartRunInputs,
  chartView,
  chartViews,
  familyKnobList,
  familyListed,
  familyStep,
  formatG,
  initialChart,
  pickedName,
  pickKnob,
  setChartView,
  stepEdit,
} from "../lib/analysisChart";
import { crossPlan, CURVE_CAP, type CrossEnv } from "../lib/chartCells";
import { DEFAULT_DENSITY_SPEC, type ParamSweepSpec, paramValues } from "../lib/paramSweep";
import { DEFAULT_AXES } from "../lib/sweepAxis";

const SEED = { view: "Smith" as const, axes: DEFAULT_AXES, threshold: 2 };
const BASE: ParamSweepSpec = { param: "base", lo: 4, hi: 14, points: 11, log: false };
const DWELL = { frequency: true, knob: false };
const ENV = { resident: true, dwellDefaults: DWELL, designRange: { lo: 28, hi: 29.7, spacing: "lin" as const }, values: [], label: "Base" };

const knobChart = () => pickKnob(initialChart(SEED), null, BASE);
const PATTERNS = ["pattern:0", "pattern:1", "pattern:2"];

const env = (slots: string[]): CrossEnv => ({
  slots: slots.map((id) => ({ id, label: id, holds: () => false, refusal: null })),
  activeSlot: slots[0],
  grounds: [{ id: "X", label: "X", holds: () => false }],
  activeGround: "X",
});

describe("the knob chart's pattern views", () => {
  it("are offered on 'Sweep a knob', after the knob sweep's own", () => {
    expect(chartViews(knobChart())).toEqual(["Rx", "Smith", "Table", ...PATTERNS]);
  });

  it("are not offered on a picked knob analysis (its crosses would be dropped) nor on the density ladder", () => {
    expect(chartViews(pickKnob(initialChart(SEED), "height", BASE))).toEqual(["Rx", "Smith", "Table"]);
    expect(chartViews(pickKnob(initialChart(SEED), null, DEFAULT_DENSITY_SPEC))).toEqual(["Rx", "Smith", "Table"]);
  });
});

describe("entering a family", () => {
  it("turns the knob and range into a pattern chart, capped at the curve cap", () => {
    const f = setChartView(knobChart(), "pattern:1");
    expect(chartFamily(f)).toBe(true);
    expect(f.kind).toBe("pattern");
    expect(pickedName(f)).toBeNull();
    expect(chartView(f)).toBe("pattern:1");
    // 11 points in, 6 out: the cap, from the same ends.
    expect(f.knob.spec).toEqual({ ...BASE, points: CURVE_CAP });
    // The knob views stay one pick away.
    expect(chartViews(f)).toEqual(["Rx", "Smith", "Table", ...PATTERNS]);
  });

  it("runs the pattern runners at an.patterns()' cut angles, and waits for Run as the knob sweep does", () => {
    const f = setChartView(knobChart(), "pattern:0");
    const inputs = chartRunInputs(f, ENV);
    expect(inputs.pattern.wanted).toBe(true);
    expect(inputs.param.wanted).toBe(false);
    expect([inputs.pattern.elevAzDeg, inputs.pattern.azElevDeg]).toEqual([0, 10]);
    expect(chartDwell(f, DWELL)).toBe(false);
    expect(chartDwell(f, { frequency: false, knob: true })).toBe(true);
  });

  it("leaves to the knob sweep of the same knob and range", () => {
    const f = setChartView(knobChart(), "pattern:0");
    const back = setChartView(f, "Smith");
    expect(back.kind).toBe("knob");
    expect(chartView(back)).toBe("Smith");
    expect(back.knob.spec).toEqual(f.knob.spec);
    expect(chartFamily(back)).toBe(false);
  });
});

describe("the family's step cross", () => {
  it("is /analyses' step entry, labelled as the CLI's step_label", () => {
    const f = setChartView(knobChart(), "pattern:0");
    const values = paramValues(f.knob.spec, false);
    expect(familyListed(f, values)).toEqual({
      engines: null,
      grounds: null,
      axes: ["step"],
      step: {
        knob: "base",
        values: [4, 6, 8, 10, 12, 14],
        labels: ["base = 4", "base = 6", "base = 8", "base = 10", "base = 12", "base = 14"],
      },
    });
    expect(familyListed(knobChart(), values)).toBeNull();
  });

  it("is refused whole over the cap, as the CLI refuses it, when slots multiply it", () => {
    const f = setChartView(knobChart(), "pattern:0");
    const listed = familyListed(f, [4, 6, 8, 10])!;
    const one = crossPlan({ slots: null, grounds: null }, listed, env(["A", "B"]));
    expect(one.cells.map((c) => c.label)).toEqual(["base = 4", "base = 6", "base = 8", "base = 10"]);
    expect(one.cells.map((c) => c.step)).toEqual([4, 6, 8, 10].map((value) => ({ knob: "base", value })));
    const two = crossPlan({ slots: ["A", "B"], grounds: null }, listed, env(["A", "B"]));
    expect(two.cells).toEqual([]);
    expect(two.capRefusal).toBe("REFUSED: 4 values x 2 engines = 8 curves, over the cap of 6");
  });

  it("formats a value as Python's {:g}", () => {
    expect([14.175, 10, 0.3, 1e-5, 1234567, 28.85, -2.5, 0].map(formatG)).toEqual([
      "14.175",
      "10",
      "0.3",
      "1e-05",
      "1.23457e+06",
      "28.85",
      "-2.5",
      "0",
    ]);
  });
});

describe("the step size (Steve: 'starting and ending values and step size')", () => {
  it("is the range's step, and none on a log family", () => {
    expect(familyStep({ ...BASE, points: 6 })).toBe(2);
    expect(familyStep({ ...BASE, points: 6, log: true })).toBeNull();
  });

  it("sets the points, and moves `to` onto the last value when it does not divide the range", () => {
    const spec = { ...BASE, points: 6 };
    expect(stepEdit(spec, 2.5)).toEqual({ spec: { ...BASE, points: 5, hi: 14 }, problem: null });
    expect(stepEdit(spec, 3)).toEqual({ spec: { ...BASE, points: 4, hi: 13 }, problem: null });
    // Decimal steps that divide exactly reach `to` despite binary rounding.
    expect(stepEdit({ param: "x", lo: 0, hi: 0.3, points: 2, log: false }, 0.1).spec).toEqual({
      param: "x",
      lo: 0,
      hi: 0.3,
      points: 4,
      log: false,
    });
    // A falling range steps down.
    expect(stepEdit({ ...BASE, lo: 14, hi: 4 }, 5).spec).toEqual({ ...BASE, lo: 14, hi: 4, points: 3 });
  });

  it("is refused with fewer than two values or more than the cap", () => {
    expect(stepEdit(BASE, 1).problem).toBe("≥ 2 (6 values at most)");
    expect(stepEdit(BASE, 20).problem).toBe("at most 10");
    expect(stepEdit(BASE, 0).problem).toBe("a step above 0");
  });
});

describe("the family's knob list", () => {
  const K = [
    { name: "base", label: "Base" },
    { name: "nseg", label: "Segments", role: "density" },
    { name: "h", label: "Height", role: null },
  ];

  it("leaves a density-role knob out, names it as skipped, and adds the frequency", () => {
    const { knobs, skipped } = familyKnobList(K);
    expect(knobs.map((k) => k.name)).toEqual(["base", "h", "freq"]);
    expect(skipped).toEqual([{ name: "nseg", label: "Segments" }]);
  });
});
