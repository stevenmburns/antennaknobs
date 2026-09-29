// The analysis chart's state rules for step 5 unit 5 (AK#1757), React-free:
// R/X against frequency and the Table as chart views, and an analysis's
// explicit frequency list (what a pick sets, what the runner is asked for,
// and an edit of the ends turning the list into a range, the pick kept).
import { describe, expect, it } from "vitest";
import { type FrequencyWorkbench, frequencyPick, listRange, parseAnalyses } from "../lib/analyses";
import {
  type AnalysisChartState,
  chartFrequencyRange,
  chartRunInputs,
  chartView,
  editRange,
  initialChart as newChart,
  pickedEdited,
  pickedName,
  pickFrequency,
  pickKnob,
  setChartView,
} from "../lib/analysisChart";
import type { ParamSweepSpec } from "../lib/paramSweep";
import { sweepGrid, type SweepRange } from "../lib/sweep";
import { DEFAULT_AXES } from "../lib/sweepAxis";

const DESIGN: SweepRange = { lo: 14, hi: 14.35, spacing: "lin", step: 0.025 };
const PREFS = { axes: DEFAULT_AXES, threshold: 2 };
const LEN: ParamSweepSpec = { param: "len", lo: 0.9, hi: 1.1, points: 3, log: false };
const initialChart = (): AnalysisChartState => newChart({ view: "Smith", ...PREFS });
const env = {
  resident: true,
  dwellDefaults: { frequency: true, knob: false },
  designRange: DESIGN,
  values: [1, 2],
  label: "x",
};

const LISTED: FrequencyWorkbench = {
  runs: true,
  kind: "frequency",
  range: { lo: 14, hi: 14.3, spacing: "lin", points: 3, source: "design" },
  level: "analysis",
  points: null,
  freqs: [14.2, 14, 14.3],
  views: ["Swr"],
  swr: { scale: null, threshold: null },
  note: null,
};

describe("an explicit frequency list", () => {
  it("is parsed from /analyses, and a pick sweeps exactly its values, ascending, with no refinement", () => {
    const [a] = parseAnalyses({ analyses: [{ name: "listed", workbench: LISTED }] });
    expect((a.workbench as FrequencyWorkbench).freqs).toEqual([14.2, 14, 14.3]);
    const pick = frequencyPick(LISTED, DESIGN);
    expect(pick.range).toEqual({ lo: 14, hi: 14.3, spacing: "lin", freqs: [14, 14.2, 14.3], exact: true });
    expect(sweepGrid(pick.range!, 17).freqs).toEqual([14, 14.2, 14.3]);
    const c = pickFrequency(initialChart(), "listed", LISTED, DESIGN, PREFS);
    expect(chartRunInputs(c, env).freq.range).toEqual(listRange([14.2, 14, 14.3]));
  });

  it("an edit of from / to is a range over the new ends, as many points, and keeps the pick (edited)", () => {
    const c = pickFrequency(initialChart(), "listed", LISTED, DESIGN, PREFS);
    const range = chartFrequencyRange(c.frequency!, DESIGN);
    const next = editRange(range, 14.1, range.hi)!;
    expect(next).toEqual({ lo: 14.1, hi: 14.3, spacing: "lin", step: (14.3 - 14.1) / 2 });
    expect(next.freqs).toBeUndefined();
    expect(next.exact).toBeUndefined();
    const edited: AnalysisChartState = { ...c, frequency: { ...c.frequency!, rangeEdit: next } };
    expect(pickedName(edited)).toBe("listed");
    expect(pickedEdited(edited)).toBe(true);
    expect(pickedEdited(c)).toBe(false);
    expect(sweepGrid(chartFrequencyRange(edited.frequency!, DESIGN), 17).freqs).toHaveLength(3);
    // ↺ (the edit cleared) is the list again.
    const reset = { ...edited, frequency: { ...edited.frequency!, rangeEdit: null } };
    expect(chartFrequencyRange(reset.frequency!, DESIGN).freqs).toEqual([14, 14.2, 14.3]);
  });
});

describe("R/X against frequency and the Table", () => {
  it("R/X is a frequency view, judged for refinement on the Smith projection; the Table judges none", () => {
    const rx = setChartView(initialChart(), "Rx");
    expect(chartView(rx)).toBe("Rx");
    expect(chartRunInputs(rx, env).freq.views).toEqual({ vswr: false, gamma: false, smith: true });
    expect(chartRunInputs(rx, env).freq.wanted).toBe(true);
    const table = setChartView(initialChart(), "Table");
    expect(chartRunInputs(table, env).freq.views).toEqual({ vswr: false, gamma: false, smith: false });
    expect(chartRunInputs(table, env).freq.wanted).toBe(true);
  });

  it("a knob pick opens on its analysis's first view unless it lists the one on screen", () => {
    const c = pickKnob(initialChart(), "len table", LEN, ["Table"]);
    expect(chartView(c)).toBe("Table");
    expect(chartRunInputs(c, env).param.wanted).toBe(true);
    // Listed: the view on screen stays.
    const smith = setChartView(pickKnob(initialChart(), "a", LEN), "Smith");
    expect(chartView(pickKnob(smith, "b", LEN, ["Rx", "Smith"]))).toBe("Smith");
    // No views (the knob menu's "Sweep a knob"): the view on screen stays.
    expect(chartView(pickKnob(smith, null, LEN))).toBe("Smith");
  });
});
