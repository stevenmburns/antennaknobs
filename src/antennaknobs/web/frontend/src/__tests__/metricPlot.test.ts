// A MetricPlot in the workbench (AK#1828, sweep-framework step 8 unit 2):
// what /analyses serves of it (lib/analyses.ts parseMetric), the chart's
// Metric view and the metric its knob sweep asks for (lib/analysisChart.ts),
// and the curves it draws, each less its reference (lib/metricPlot.ts), by
// the CLI's own pairing rule (`analysis_run.references`).
import { describe, expect, it } from "vitest";
import { parseAnalyses } from "../lib/analyses";
import {
  chartMetric,
  chartRunInputs,
  chartView,
  chartViews,
  initialChart,
  pickKnob,
  setChartView,
} from "../lib/analysisChart";
import { type MetricCell, metricReferences, metricSeries } from "../lib/metricPlot";
import type { ParamSweepData, ParamSweepSpec } from "../lib/paramSweep";
import { DEFAULT_AXES } from "../lib/sweepAxis";

const SPEC = { an: "ElevationWindow", name: "DX gain", lo: 2, hi: 10, step: 0.1 };
const METRIC = {
  name: "DX gain",
  unit: "dBi",
  relativeTo: "ref",
  relativeUnit: "dB",
  spec: SPEC,
};
const BASE: ParamSweepSpec = { param: "base", lo: 5, hi: 12, points: 2, log: false };
const seed = { view: "Smith" as const, axes: DEFAULT_AXES, threshold: 2 };

const served = (metric: unknown) =>
  parseAnalyses({
    analyses: [
      {
        name: "dx",
        summary: "",
        code: "",
        problems: [],
        workbench: {
          runs: true,
          kind: "knob",
          param: "base",
          values: [5, 12],
          log: false,
          views: ["Metric", "Rx"],
          metric,
          states: [
            { name: "as built", label: "as built", knobs: {}, design: null, refused: null,
              param: "base", values: [5, 12], reference: false, fixed: false },
            { name: "ref", label: "ref", knobs: { base: 7 }, design: null, refused: null,
              param: "base", values: [7], reference: true, fixed: true },
          ],
          note: null,
        },
      },
    ],
  })[0];

describe("what /analyses serves of a MetricPlot", () => {
  it("parses the metric and the reference cells", () => {
    const e = served({
      name: "DX gain",
      unit: "dBi",
      relative_to: "ref",
      relative_unit: "dB",
      spec: SPEC,
    });
    expect(e.workbench.runs && e.workbench.kind === "knob" && e.workbench.metric).toEqual(METRIC);
    const w = e.workbench;
    if (!w.runs || w.kind !== "knob") throw new Error("not a knob analysis");
    expect(w.views).toEqual(["Metric", "Rx"]);
    expect(w.states?.map((s) => [s.name, !!s.reference, !!s.fixed, s.values])).toEqual([
      ["as built", false, false, [5, 12]],
      ["ref", true, true, [7]],
    ]);
  });

  it("drops a Metric view that has no metric to draw", () => {
    const w = served(null).workbench;
    if (!w.runs || w.kind !== "knob") throw new Error("not a knob analysis");
    expect(w.views).toEqual(["Rx"]);
    expect(w.metric).toBeUndefined();
  });
});

describe("the chart's Metric view", () => {
  it("is offered while the analysis with the metric is picked, and asks for it", () => {
    const c = pickKnob(initialChart(seed), "dx", BASE, ["Metric", "Rx"], METRIC);
    expect(chartMetric(c)).toEqual(METRIC);
    expect(chartViews(c)).toEqual(["Rx", "Smith", "Table", "Metric"]);
    expect(chartView(c)).toBe("Metric");
    const inputs = chartRunInputs(c, {
      resident: true,
      dwellDefaults: { frequency: true, knob: false },
      designRange: { lo: 14, hi: 14.35, spacing: "lin" },
      values: [5, 12],
      label: "base",
    });
    expect(inputs.param.req.metric).toEqual(SPEC);
  });

  it("goes with the pick: another knob sweep has no metric and opens on R / X", () => {
    const c = pickKnob(initialChart(seed), "dx", BASE, ["Metric"], METRIC);
    const other = pickKnob(c, null, { ...BASE, param: "length_factor" });
    expect(chartMetric(other)).toBeNull();
    expect(chartViews(other)).not.toContain("Metric");
    expect(chartView(other)).toBe("Rx");
    expect(setChartView(other, "Metric")).toBe(other);
    const inputs = chartRunInputs(other, {
      resident: true,
      dwellDefaults: { frequency: true, knob: false },
      designRange: { lo: 14, hi: 14.35, spacing: "lin" },
      values: [1, 2],
      label: "length_factor",
    });
    expect(inputs.param.req.metric).toBeUndefined();
  });
});

const cell = (key: string, over: Partial<MetricCell> = {}): MetricCell => ({
  key,
  label: key,
  color: "#000",
  reference: false,
  fixed: false,
  slot: "A",
  ground: "1",
  ...over,
});
const sweep = (values: number[], metric: (number | null)[]): ParamSweepData => ({
  param: "base",
  label: "base",
  values,
  z_re: values.map(() => 50),
  z_im: values.map(() => 0),
  z_re_extrap: null,
  z_im_extrap: null,
  metric,
});

describe("the curves a metric plot draws", () => {
  it("subtracts a fixed reference's one value at every x, and draws it flat at 0", () => {
    const cells = [cell("as built"), cell("ref", { reference: true, fixed: true })];
    const data = [sweep([5, 9, 12], [-3, 1.5, 4]), sweep([7], [0.5])];
    const [a, ref] = metricSeries(cells, data, true);
    expect(a.ys).toEqual([-3.5, 1, 3.5]);
    expect(ref).toMatchObject({ fixed: true, level: 0, xs: [] });
    // Absolute: the values themselves, the fixed one at its own level.
    const [abs, refAbs] = metricSeries(cells, data, false);
    expect(abs.ys).toEqual([-3, 1.5, 4]);
    expect(refAbs.level).toBe(0.5);
  });

  it("pairs each curve with the reference on its own slot when several are named", () => {
    const cells = [
      cell("L, A", { slot: "A" }),
      cell("L, B", { slot: "B" }),
      cell("V, A", { slot: "A", reference: true }),
      cell("V, B", { slot: "B", reference: true }),
    ];
    expect(metricReferences(cells)).toEqual([2, 3, 2, 3]);
    const data = [
      sweep([1, 2], [1, 2]),
      sweep([1, 2], [10, 20]),
      sweep([1, 2], [0.5, 0.5]),
      sweep([1, 2], [5, 5]),
    ];
    const s = metricSeries(cells, data, true);
    expect(s.map((x) => x.ys)).toEqual([[0.5, 1.5], [5, 15], [0, 0], [0, 0]]);
  });

  it("takes a difference only at the same x, never interpolated", () => {
    const cells = [cell("a"), cell("r", { reference: true })];
    const data = [sweep([1, 2, 3], [1, 2, 3]), sweep([1, 3], [0, 1])];
    expect(metricSeries(cells, data, true)[0].ys).toEqual([1, null, 2]);
  });

  it("names no reference when none matches the curve", () => {
    const cells = [cell("a", { slot: "C" }), cell("r1", { reference: true }), cell("r2", { reference: true, slot: "B" })];
    expect(metricReferences(cells)).toEqual([null, 1, 2]);
    expect(metricSeries(cells, [sweep([1], [1]), sweep([1], [0]), sweep([1], [0])], true)[0].ys).toEqual([
      null,
    ]);
  });
});
