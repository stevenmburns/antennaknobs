// The metric picker (AK#2327): an analysis declaring several MetricPlots
// draws one at a time, the first by default, and the choice holds across
// view switches and picks, rides the deep link, and draws without a second
// sweep (every metric is read off each point's one solve).
import { describe, expect, it } from "vitest";
import {
  chartMetric,
  chartMetricIndex,
  chartMetrics,
  chartRunInputs,
  chartView,
  initialChart,
  pickKnob,
  setChartMetric,
  setChartView,
} from "../lib/analysisChart";
import { metricLabel, metricNote, type MetricSpec } from "../lib/analyses";
import { linkSearch, parseDeepLink } from "../lib/deepLink";
import { projectMetric, type ParamSweepData, type ParamSweepSpec } from "../lib/paramSweep";

const metric = (name: string, unit: string): MetricSpec => ({
  name,
  unit,
  relativeTo: null,
  relativeUnit: unit,
  spec: { an: "FillMetric", quantity: name },
});
const COMPRESSION = metric("fill compression", "×");
const FILL = metric("fill time", "s");
const FACTOR = metric("factor time", "s");
const SHARE = metric("fill share", "%");
const ALL = [COMPRESSION, FILL, FACTOR, SHARE];

const SPEC: ParamSweepSpec = { param: "n_per_wire", lo: 8, hi: 68, points: 7, log: true };
const SEED = { design: "d", measFreq: 14, designRange: { lo: 13, hi: 15 } } as unknown as Parameters<
  typeof initialChart
>[0];

const picked = (metrics: MetricSpec[] = ALL) =>
  pickKnob(initialChart(SEED), "convergence", SPEC, ["Rx", "Table", "Smith", "Metric"], metrics[0], null, metrics);

describe("the chart's metric", () => {
  it("is the first by default", () => {
    const c = picked();
    expect(chartMetrics(c).map((m) => m.name)).toEqual(ALL.map((m) => m.name));
    expect(chartMetric(c)).toBe(COMPRESSION);
    expect(chartMetricIndex(c)).toBe(0);
  });
  it("is the one picked, across view switches", () => {
    let c = setChartMetric(picked(), "factor time");
    c = setChartView(setChartView(c, "Rx"), "Metric");
    expect(chartView(c)).toBe("Metric");
    expect(chartMetric(c)).toBe(FACTOR);
  });
  it("falls back to the first for a name the analysis does not declare", () => {
    expect(chartMetric(setChartMetric(picked(), "nonsense"))).toBe(COMPRESSION);
  });
  it("with one metric is just that one, as before", () => {
    const one = pickKnob(initialChart(SEED), "dx", SPEC, ["Metric"], FILL, null);
    expect(chartMetrics(one)).toEqual([FILL]);
    expect(chartMetric(setChartMetric(one, "anything"))).toBe(FILL);
  });
  it("sweeps every metric at once, so a pick needs no second sweep", () => {
    const env = {
      resident: true,
      dwellDefaults: { knob: false, frequency: true },
      designRange: { lo: 13, hi: 15 },
      values: [8, 12],
      label: "x",
    } as unknown as Parameters<typeof chartRunInputs>[1];
    const a = chartRunInputs(picked(), env).param.req;
    const b = chartRunInputs(setChartMetric(picked(), "fill share"), env).param.req;
    expect(a.metrics).toEqual(ALL.map((m) => m.spec));
    expect(a.metric).toBeUndefined();
    expect(b).toEqual(a);
    const one = chartRunInputs(pickKnob(initialChart(SEED), "dx", SPEC, ["Metric"], FILL, null), env).param.req;
    expect(one.metric).toEqual(FILL.spec);
    expect(one.metrics).toBeUndefined();
  });
});

describe("drawing one of several", () => {
  const data: ParamSweepData = {
    param: "n_per_wire",
    label: "x",
    values: [8, 12],
    z_re: [50, 51],
    z_im: [0, 1],
    z_re_extrap: null,
    z_im_extrap: null,
    metrics: [
      [null, null],
      [0.1, 0.2],
    ],
    metric_errors: ["fill reuse is off for this solve", null],
  };
  it("takes that metric's values and its own reason", () => {
    expect(projectMetric(data, 0)).toMatchObject({
      metric: [null, null],
      metric_error: "fill reuse is off for this solve",
    });
    const time = projectMetric(data, 1)!;
    expect(time.metric).toEqual([0.1, 0.2]);
    expect(time.metric_error).toBeUndefined();
  });
  it("leaves a one-metric sweep as it is", () => {
    const one: ParamSweepData = { ...data, metric: [1, 2] };
    delete one.metrics;
    delete one.metric_errors;
    expect(projectMetric(one, 0)).toBe(one);
  });
});

describe("its label and note", () => {
  it("is named by the metric, not 'Metric'", () => {
    expect(ALL.map(metricLabel)).toEqual(["Fill compression", "Fill time", "Factor time", "Fill share"]);
    expect(metricLabel(metric("DX gain", "dBi"))).toBe("DX gain");
  });
  it("names the metrics not drawn", () => {
    expect(metricNote(ALL, FILL)).toBe(
      "left out: the MetricPlot of 'fill compression', 'factor time', 'fill share' " +
        "(the chart draws the one picked beside its view; `antennaknobs analyze` draws each)",
    );
    expect(metricNote([FILL], FILL)).toBeNull();
  });
});

describe("the deep link", () => {
  it("reads metric= beside view=Metric", () => {
    const link = parseDeepLink("?design=dipoles.invvee&analysis=convergence&view=Metric&metric=fill%20time");
    expect(link?.metric).toBe("fill time");
    expect(parseDeepLink("?design=dipoles.invvee&analysis=convergence&view=Metric")?.metric).toBeUndefined();
  });
  it("writes it only where it is not the first, so existing links are unchanged", () => {
    const base = { design: "dipoles.invvee", variant: null, analysis: "convergence", view: "Metric" };
    expect(linkSearch("", { ...base, metric: "factor time" })).toBe(
      "?design=dipoles.invvee&analysis=convergence&view=Metric&metric=factor%20time",
    );
    expect(linkSearch("", { ...base, metric: null })).toBe("?design=dipoles.invvee&analysis=convergence&view=Metric");
    expect(linkSearch("", { ...base, view: "Rx", metric: "factor time" })).toBe(
      "?design=dipoles.invvee&analysis=convergence&view=Rx",
    );
  });
});
