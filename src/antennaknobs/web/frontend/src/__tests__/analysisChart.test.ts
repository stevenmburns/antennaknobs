// The analysis chart's state rules (lib/analysisChart.ts, AK#1757 step 5
// unit 2), React-free: the dwell switch's defaults, what a pick sets, which
// range a frequency chart sweeps, and what each runner is asked for.
import { describe, it, expect } from "vitest";
import type { FrequencyWorkbench } from "../lib/analyses";
import {
  chartDwell,
  chartFrequencyRange,
  chartRunInputs,
  editRange,
  initialChart,
  pickedName,
  pickFrequency,
  pickKnob,
} from "../lib/analysisChart";
import { DEFAULT_DENSITY_SPEC, type ParamSweepSpec } from "../lib/paramSweep";
import type { SweepRange } from "../lib/sweep";
import { DEFAULT_AXES, RHO } from "../lib/sweepAxis";

const DESIGN: SweepRange = { lo: 14, hi: 14.35, spacing: "lin", step: 0.025 };
const PREFS = { axes: DEFAULT_AXES, threshold: 2 };
const HEIGHT: ParamSweepSpec = { param: "base", lo: 2, hi: 20, points: 37, log: false };

const freq = (over: Partial<FrequencyWorkbench> = {}): FrequencyWorkbench => ({
  runs: true,
  kind: "frequency",
  range: { lo: 13.9, hi: 14.5, spacing: "lin", points: 25, source: "design" },
  level: "analysis",
  points: 25,
  views: ["Swr", "Smith"],
  swr: { scale: null, threshold: null },
  note: null,
  ...over,
});

const env = (resident = true) => ({ resident, designRange: DESIGN, values: [1, 2], label: "x" });

describe("the dwell switch", () => {
  it("defaults to today's behaviour: density and frequency on, a knob off", () => {
    const c = initialChart();
    expect(chartDwell(c)).toBe(true);
    expect(chartDwell(pickKnob(c, "height", HEIGHT))).toBe(false);
    expect(chartDwell(pickFrequency(c, "wide", freq(), DESIGN, PREFS))).toBe(true);
  });

  it("once flipped, holds across picks", () => {
    const off = { ...initialChart(), dwell: false };
    expect(chartDwell(pickFrequency(off, "wide", freq(), DESIGN, PREFS))).toBe(false);
    const on = { ...initialChart(), dwell: true };
    expect(chartDwell(pickKnob(on, "height", HEIGHT))).toBe(true);
  });

  it("is each runner's `auto`", () => {
    const off = { ...pickFrequency(initialChart(), "wide", freq(), DESIGN, PREFS), dwell: false };
    const r = chartRunInputs(off, env());
    expect(r.freq.auto).toBe(false);
    expect(r.param.req.auto).toBe(false);
  });
});

describe("a pick", () => {
  it("a frequency analysis: its range, first view, scale and threshold; the viewer's where it names none", () => {
    const c = pickFrequency(
      initialChart(),
      "wide",
      freq({ swr: { scale: "rho", threshold: 1.5 } }),
      DESIGN,
      PREFS,
    );
    expect(c.kind).toBe("frequency");
    expect(c.frequency!.view).toBe("Swr");
    expect(c.frequency!.axes.vswr).toEqual(RHO);
    expect(c.frequency!.axes.gamma).toEqual(DEFAULT_AXES.gamma);
    expect(c.frequency!.threshold).toBe(1.5);
    const r = chartFrequencyRange(c.frequency!, DESIGN);
    expect([r.lo, r.hi, r.spacing]).toEqual([13.9, 14.5, "lin"]);
    // 25 points: the analysis's own count replaces the range's step.
    expect(r.step).toBeCloseTo(0.025, 12);
    expect(pickedName(c)).toBe("wide");
    const plain = pickFrequency(initialChart(), "wide", freq(), DESIGN, PREFS);
    expect(plain.frequency!.axes).toBe(DEFAULT_AXES);
    expect(plain.frequency!.threshold).toBe(2);
  });

  it("the design's own range follows the design (null), and an edit wins over both", () => {
    const own = pickFrequency(
      initialChart(),
      "band",
      freq({ range: null, points: null }),
      DESIGN,
      PREFS,
    );
    expect(own.frequency!.analysisRange).toBeNull();
    const moved: SweepRange = { ...DESIGN, lo: 14.1 };
    expect(chartFrequencyRange(own.frequency!, moved)).toBe(moved);
    const edited = { ...own.frequency!, rangeEdit: editRange(DESIGN, 13, 15) };
    expect(chartFrequencyRange(edited, moved)).toEqual({ ...DESIGN, lo: 13, hi: 15 });
    expect(editRange(DESIGN, 15, 13)).toBeNull();
    expect(editRange(DESIGN, 0, 13)).toBeNull();
  });

  it("a knob analysis: named while the chart runs its spec, not after an edit", () => {
    const c = pickKnob(initialChart(), "height", HEIGHT);
    expect(c.kind).toBe("knob");
    expect(pickedName(c)).toBe("height");
    const edited = pickKnob(c, null, { ...HEIGHT, points: 5 });
    expect(pickedName(edited)).toBeNull();
    // A frequency pick after it keeps the knob spec for a later knob pick.
    const f = pickFrequency(c, "wide", freq(), DESIGN, PREFS);
    expect(f.knob.spec).toBe(HEIGHT);
    expect(pickedName(f)).toBe("wide");
  });
});

describe("what the runners are asked for", () => {
  it("a knob chart wants only its parameter runner, and nothing off screen", () => {
    const r = chartRunInputs(initialChart(), env());
    expect(r.param.wanted).toBe(true);
    expect(r.param.req).toEqual({ param: DEFAULT_DENSITY_SPEC.param, values: [1, 2], label: "x", auto: true });
    expect(r.freq.wanted).toBe(false);
    expect(chartRunInputs(initialChart(), env(false)).param.wanted).toBe(false);
  });

  it("a frequency chart wants only its frequency runner, refining the one view on screen", () => {
    const c = pickFrequency(initialChart(), "wide", freq(), DESIGN, PREFS);
    const r = chartRunInputs(c, env());
    expect(r.param.wanted).toBe(false);
    expect(r.freq.wanted).toBe(true);
    expect(r.freq.views).toEqual({ vswr: true, gamma: false, smith: false });
    expect(r.freq.range.lo).toBe(13.9);
    const smith = { ...c, frequency: { ...c.frequency!, view: "Smith" as const } };
    expect(chartRunInputs(smith, env()).freq.views).toEqual({ vswr: false, gamma: false, smith: true });
    expect(chartRunInputs(c, env(false)).freq.wanted).toBe(false);
  });
});
