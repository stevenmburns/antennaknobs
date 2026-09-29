// The analysis chart's state rules (lib/analysisChart.ts, AK#1757 step 5
// units 2 and 3), React-free: what a new chart is, the dwell switch's
// defaults, what a pick sets, the views per kind, which range a frequency
// chart sweeps, and what each runner is asked for.
import { describe, it, expect } from "vitest";
import type { FrequencyWorkbench } from "../lib/analyses";
import {
  type AnalysisChartState,
  chartDwell,
  chartForNewDesign,
  chartFrequencyRange,
  chartRunInputs,
  chartView,
  chartViews,
  editRange,
  initialChart as newChart,
  pickedName,
  pickFrequency,
  pickKnob,
  setChartView,
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

// settings.toml's built-in [switches]: freq_sweep on, convergence_sweep off.
const DWELL = { frequency: true, knob: false };
const SEED = { view: "Smith" as const, ...PREFS };
const initialChart = (): AnalysisChartState => newChart(SEED);
const env = (resident = true) => ({
  resident,
  dwellDefaults: DWELL,
  designRange: DESIGN,
  values: [1, 2],
  label: "x",
});
const DENSITY_CHART = pickKnob(initialChart(), null, DEFAULT_DENSITY_SPEC);

describe("a new chart (unit 3)", () => {
  it("is the design's own frequency sweep on the Smith chart, every frequency view offered", () => {
    const c = initialChart();
    expect(c.kind).toBe("frequency");
    expect(c.picked).toBeNull();
    expect(chartView(c)).toBe("Smith");
    expect(chartViews(c)).toEqual(["Smith", "Swr", "S11", "Rx", "Table"]);
    // Its range is the session's (the design's own, or the dial's edit).
    expect(chartFrequencyRange(c.frequency!, DESIGN)).toBe(DESIGN);
    const r = chartRunInputs(c, env());
    expect(r.freq.wanted).toBe(true);
    expect(r.freq.auto).toBe(true);
    expect(r.freq.views).toEqual({ vswr: false, gamma: false, smith: true });
    expect(r.param.wanted).toBe(false);
  });

  it("opens on the view a migrated pin named, with the viewer's scales", () => {
    const c = newChart({ view: "Swr", axes: { ...DEFAULT_AXES, vswr: RHO }, threshold: 1.5 });
    expect(chartView(c)).toBe("Swr");
    expect(chartViews(c)).toEqual(["Swr", "Smith", "S11", "Rx", "Table"]);
    expect(c.frequency!.axes.vswr).toEqual(RHO);
    expect(c.frequency!.threshold).toBe(1.5);
    expect(chartRunInputs(c, env()).freq.views).toEqual({ vswr: true, gamma: false, smith: false });
  });

  it("a design switch starts over but keeps the view, the scales and a flipped switch", () => {
    const flipped: AnalysisChartState = {
      ...setChartView(pickFrequency(initialChart(), "wide", freq(), DESIGN, PREFS), "S11"),
      dwell: false,
    };
    const next = chartForNewDesign(flipped, SEED);
    expect(next.picked).toBeNull();
    expect(next.frequency!.analysisRange).toBeNull();
    expect(chartView(next)).toBe("S11");
    expect(next.dwell).toBe(false);
    // A knob sweep on its Smith view comes back to the Smith chart; on R/X,
    // to the seed's view.
    const knobSmith = setChartView(pickKnob(initialChart(), "height", HEIGHT), "Smith");
    expect(chartView(chartForNewDesign(knobSmith, { ...SEED, view: "Swr" }))).toBe("Smith");
    const knobRx = pickKnob(initialChart(), "height", HEIGHT);
    expect(chartView(chartForNewDesign(knobRx, { ...SEED, view: "Swr" }))).toBe("Swr");
    expect(chartForNewDesign(knobRx, SEED).knob.spec).toBe(DEFAULT_DENSITY_SPEC);
  });
});

describe("the chart's views (unit 3)", () => {
  it("are honest per kind: R/X, Smith or Table for a knob sweep; SWR, S11, Smith, R/X or Table for a frequency one", () => {
    const knob = pickKnob(initialChart(), "height", HEIGHT);
    expect(chartViews(knob)).toEqual(["Rx", "Smith", "Table"]);
    expect(chartView(knob)).toBe("Rx");
    // A view the kind cannot draw is refused, the same chart back.
    expect(setChartView(knob, "Swr")).toBe(knob);
    // R/X against frequency draws since unit 5.
    expect(setChartView(initialChart(), "Rx").frequency!.view).toBe("Rx");
    // The knob sweep on the Smith chart: still its parameter runner only.
    const trail = setChartView(knob, "Smith");
    expect(chartView(trail)).toBe("Smith");
    const r = chartRunInputs(trail, env());
    expect(r.param.wanted).toBe(true);
    expect(r.freq.wanted).toBe(false);
  });

  it("a frequency pick leads with the analysis's own views, then the rest", () => {
    const c = pickFrequency(initialChart(), "wide", freq(), DESIGN, PREFS);
    expect(chartViews(c)).toEqual(["Swr", "Smith", "S11", "Rx", "Table"]);
    expect(chartView(c)).toBe("Swr");
  });
});

describe("the dwell switch", () => {
  it("defaults per kind from settings.toml: freq_sweep for frequency, convergence_sweep for knob and density", () => {
    const c = initialChart();
    expect(chartDwell(c, DWELL)).toBe(true);
    expect(chartDwell(c, { frequency: false, knob: false })).toBe(false);
    expect(chartDwell(pickKnob(c, "height", HEIGHT), DWELL)).toBe(false);
    expect(chartDwell(DENSITY_CHART, DWELL)).toBe(false);
    expect(chartDwell(DENSITY_CHART, { frequency: true, knob: true })).toBe(true);
    expect(chartDwell(pickFrequency(c, "wide", freq(), DESIGN, PREFS), DWELL)).toBe(true);
  });

  it("once flipped, holds across picks, whatever the defaults", () => {
    const off = { ...initialChart(), dwell: false };
    expect(chartDwell(pickFrequency(off, "wide", freq(), DESIGN, PREFS), DWELL)).toBe(false);
    const on = { ...initialChart(), dwell: true };
    expect(chartDwell(pickKnob(on, "height", HEIGHT), DWELL)).toBe(true);
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
    const r = chartRunInputs(DENSITY_CHART, env());
    expect(r.param.wanted).toBe(true);
    expect(r.param.req).toEqual({ param: DEFAULT_DENSITY_SPEC.param, values: [1, 2], label: "x", auto: false });
    expect(r.freq.wanted).toBe(false);
    expect(chartRunInputs(DENSITY_CHART, env(false)).param.wanted).toBe(false);
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
