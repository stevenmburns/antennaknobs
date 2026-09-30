// A pattern on the analysis chart (AK#1757, sweep-framework step 7 unit 3),
// React-free: what /analyses serves for one and how it parses, what a pick
// sets, the views the chart offers, and what its runners are asked for.
import { describe, it, expect } from "vitest";
import { analysisBlocked, parseAnalyses, type PatternWorkbench } from "../lib/analyses";
import {
  chartDwell,
  chartPatternView,
  chartRunInputs,
  chartView,
  chartViews,
  initialChart,
  pickedEdited,
  pickedName,
  pickFrequency,
  pickPattern,
  patternViewLabel,
  setChartView,
} from "../lib/analysisChart";
import type { SweepRange } from "../lib/sweep";
import { DEFAULT_AXES } from "../lib/sweepAxis";

const DESIGN: SweepRange = { lo: 28, hi: 29.7, spacing: "lin", step: 0.05 };
const SEED = { view: "Smith" as const, axes: DEFAULT_AXES, threshold: 2 };

const served = (views: unknown[]) => ({
  analyses: [
    {
      name: "height patterns",
      summary: "",
      code: "",
      problems: [],
      workbench: {
        runs: true,
        kind: "pattern",
        views,
        freq: 28.47,
        engines: null,
        grounds: ["finite-fast"],
        axes: ["states"],
        planes: null,
        designs: null,
        states: null,
        step: null,
        note: null,
      },
    },
  ],
});

const W: PatternWorkbench = {
  runs: true,
  kind: "pattern",
  views: [{ view: "Elevation", az: 0 }, { view: "Azimuth", el: 10 }, { view: "PatternTable" }],
  freq: 28.47,
  note: null,
};

const env = (resident = true) => ({
  resident,
  dwellDefaults: { frequency: true, knob: false },
  designRange: DESIGN,
  values: [1],
  label: "N",
});

describe("a served pattern", () => {
  it("parses its views, freq and crosses", () => {
    const [e] = parseAnalyses(served([{ view: "Elevation", az: 90 }, { view: "PatternTable" }]));
    const w = e.workbench as PatternWorkbench;
    expect(w.kind).toBe("pattern");
    expect(w.views).toEqual([{ view: "Elevation", az: 90 }, { view: "PatternTable" }]);
    expect(w.freq).toBe(28.47);
    expect(w.grounds).toEqual(["finite-fast"]);
    expect(analysisBlocked(w, new Set())).toBeNull();
  });

  it("drops a malformed view, and a pattern with none is no entry", () => {
    const [e] = parseAnalyses(served([{ view: "Azimuth", el: 10.5 }, { view: "Rx" }, { view: "Azimuth", el: 15 }]));
    expect((e.workbench as PatternWorkbench).views).toEqual([{ view: "Azimuth", el: 15 }]);
    expect(parseAnalyses(served([{ view: "Rx" }]))).toEqual([]);
  });
});

describe("a pattern on the chart", () => {
  it("a pick shows its first view and offers the analysis's views by name", () => {
    const c = pickPattern(initialChart(SEED), "height patterns", W);
    expect(c.kind).toBe("pattern");
    expect(pickedName(c)).toBe("height patterns");
    expect(pickedEdited(c)).toBe(false);
    expect(chartViews(c)).toEqual(["pattern:0", "pattern:1", "pattern:2"]);
    expect(chartView(c)).toBe("pattern:0");
    expect(chartPatternView(c)).toEqual({ view: "Elevation", az: 0 });
    expect(W.views.map(patternViewLabel)).toEqual(["Elevation @ 0° az", "Azimuth @ 10° el", "Table"]);
    const t = setChartView(c, "pattern:2");
    expect(chartPatternView(t)).toEqual({ view: "PatternTable" });
    // A view the pattern does not have is refused: the same chart back.
    expect(setChartView(c, "Smith")).toBe(c);
  });

  it("asks its pattern runners only, at its cut angles, following the knobs by default", () => {
    const c = pickPattern(initialChart(SEED), "height patterns", W);
    expect(chartDwell(c, env().dwellDefaults)).toBe(true);
    const run = chartRunInputs(c, env());
    expect(run.pattern).toEqual({ wanted: true, auto: true, elevAzDeg: 0, azElevDeg: 10 });
    expect(run.freq.wanted).toBe(false);
    expect(run.param.wanted).toBe(false);
    expect(chartRunInputs(c, env(false)).pattern.wanted).toBe(false);
    // Another kind's pick leaves the pattern's runners idle.
    const f = pickFrequency(c, "band SWR", {
      runs: true,
      kind: "frequency",
      range: null,
      level: "policy",
      points: null,
      views: ["Swr"],
      swr: { scale: null, threshold: null },
      note: null,
    }, DESIGN, SEED);
    expect(chartRunInputs(f, env()).pattern.wanted).toBe(false);
    expect(chartRunInputs(f, env()).freq.wanted).toBe(true);
  });

  it("a table-only pattern still solves, at the default cut angles", () => {
    const c = pickPattern(initialChart(SEED), "t", { ...W, views: [{ view: "PatternTable" }] });
    expect(chartRunInputs(c, env()).pattern).toEqual({
      wanted: true,
      auto: true,
      elevAzDeg: 0,
      azElevDeg: 15,
    });
  });
});
