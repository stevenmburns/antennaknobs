// A metric analysis's other views (AK#1867, Dan AC6LA on M0AGP's DX-gain
// study): the Table tabulates the metric, the Metric view carries the R/X
// chart's current-value guide and pointer readout, a relative plot's
// reference says it is one, a listed ground names its model, and the
// padded y axis does not label its own floor over the tick above it.
//
// Every expectation here fails on the tree before AK#1867: the Table had
// R/X only, the Metric view no guide or readout, the legend the bare label,
// the ground the CLI's `finite:13,0.005`, and the y axis a "-10.3" on "-10".
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ViewPanel } from "../components/results/ViewPanel";
import type { ViewRenderProps } from "../components/results/viewRegistry";
import { MetricPlotChart } from "../components/charts/MetricPlotChart";
import { chartTable, tableCsv } from "../lib/chartTable";
import { type CrossEnv, crossPlan, groundSpecWords } from "../lib/chartCells";
import { metricCaption, metricColumns, type MetricSeries } from "../lib/metricPlot";
import { RX_AUTO } from "../lib/paramSweep";
import { axisTicks } from "../lib/sweepAxis";

HTMLCanvasElement.prototype.getContext =
  (() => null) as unknown as HTMLCanvasElement["getContext"];
vi.mock("../components/charts/FarFieldChart", () => ({ FarFieldChart: () => <canvas /> }));

const METRIC = { name: "DX gain", unit: "dBi", relativeTo: "vertical", relativeUnit: "dB", spec: {} };

// Two states as the M0AGP study has them: the inverted L swept over
// vert_ft, and the vertical, a FIXED reference solved once at 131.2.
const INVL = {
  param: "vert_ft",
  label: "vert_ft",
  values: [20, 40, 60],
  z_re: [10, 20, 30],
  z_im: [-5, 0, 5],
  metric: [-1.5, 0.25, null],
} as unknown as ViewRenderProps["paramSweep"];
const VERTICAL = {
  param: "vert_ft",
  label: "vert_ft",
  values: [131.2],
  z_re: [36],
  z_im: [1],
  metric: [2],
} as unknown as ViewRenderProps["paramSweep"];

const SERIES: MetricSeries[] = [
  { key: "invl", label: "inverted L", color: "#c00", xs: [20, 40, 60], ys: [-3.5, -1.75, null],
    fixed: false, level: null, stale: false, error: null },
  { key: "vert", label: "vertical (reference, 0 dB)", color: "#a60", xs: [], ys: [],
    fixed: true, level: 0, stale: false, error: null },
];

const zparam = (view: "Table" | "Metric", currentValue: number | null = null) => ({
  param: "vert_ft",
  label: "vert_ft",
  unit: "ft",
  total: 3,
  currentValue,
  xLog: false,
  rAxis: RX_AUTO,
  xAxis: RX_AUTO,
  z0: 50,
  view,
});

const PROPS: Omit<ViewRenderProps, "showWireLabels" | "showFeedNames" | "schematicSvg" | "schematicUnavailable"> = {
  size: 400,
  fill: true,
  result: null,
  liveZ: null,
  preview: null,
  paramSweep: null,
  measured: null,
  pattern: null,
  pinnedPatterns: [],
  measFreqMhz: 7.1,
  paramSweepRunning: false,
  azElevDeg: 0,
  elevAzDeg: 0,
  cameraProjection: "xy",
  showHeatmap: false,
  showEnvelope: false,
  multiFeed: false,
  fineNorm: null,
};

function mountChart(over: Partial<ViewRenderProps>) {
  return render(<ViewPanel view="zparam" {...PROPS} {...over} />).container;
}

describe("the Table view of a metric analysis", () => {
  it("tabulates the metric and its difference from the reference beside R and X", () => {
    mountChart({
      zparam: zparam("Table"),
      paramSweep: INVL,
      chartCurves: [{ key: "vert", color: "#a60", paramSweep: VERTICAL }],
      chartCellLabels: ["inverted L", "vertical (reference, 0 dB)"],
      chartMetric: { metric: METRIC, series: SERIES },
    });
    const table = screen.getByRole("table", { name: "Analysis table" });
    const heads = [...table.querySelectorAll("thead tr:last-child th")].map((th) => th.textContent);
    expect(heads).toEqual([
      "vert_ft",
      "R (Ω)", "X (Ω)", "DX gain (dBi)", "DX gain vs vertical (dB)",
      "R (Ω)", "X (Ω)", "DX gain (dBi)", "DX gain vs vertical (dB)",
    ]);
    const rows = [...table.querySelectorAll("tbody tr")].map((tr) =>
      [...tr.children].map((c) => c.textContent),
    );
    expect(rows).toEqual([
      ["20", "10.000", "-5.000", "-1.500", "-3.500", "", "", "", ""],
      ["40", "20.000", "+0.000", "0.250", "-1.750", "", "", "", ""],
      // No metric read at 60: the CLI's dash, not a blank or a zero.
      ["60", "30.000", "+5.000", "—", "—", "", "", "", ""],
      // The reference's own row: its one solve, its metric, 0 against itself.
      ["131.2", "", "", "", "", "36.000", "+1.000", "2.000", "0.000"],
    ]);
  });

  it("puts the metric in the CSV and the copy too", () => {
    const t = chartTable(
      "knob",
      "vert_ft",
      [{ label: "inverted L", xs: [20], re: [10], im: [-5], metric: [-1.5], relative: [-3.5] }],
      50,
      metricColumns(METRIC),
    );
    expect(tableCsv(t)).toBe(
      "vert_ft,inverted L R (Ω),inverted L X (Ω),inverted L DX gain (dBi),inverted L DX gain vs vertical (dB)\n" +
        "20,10.000,-5.000,-1.500,-3.500\n",
    );
  });

  it("leaves a knob sweep without a metric as it was", () => {
    const t = chartTable("knob", "vert_ft", [{ label: "", xs: [20], re: [10], im: [-5] }], 50);
    expect(t.groups[0].columns).toEqual(["R (Ω)", "X (Ω)"]);
  });
});

describe("the Metric view's current value and pointer", () => {
  it("draws the R/X chart's dashed guide at the live knob value", () => {
    const el = mountChart({ zparam: zparam("Metric", 40), chartMetric: { metric: METRIC, series: SERIES } });
    const plot = el.querySelector(".metric-plot")!;
    expect(plot.getAttribute("data-guide")).toBe("40");
    expect(plot.getAttribute("data-guide-label")).toBe("vert_ft = 40 (now)");
    expect(el.querySelector(".metric-plot-guide line")).not.toBeNull();
    // Outside the swept span there is nothing to mark.
    const off = mountChart({ zparam: zparam("Metric", 131.2), chartMetric: { metric: METRIC, series: SERIES } });
    expect(off.querySelector(".metric-plot")!.getAttribute("data-guide")).toBe("");
  });

  it("follows the pointer down and across the plot, snapped to the nearest swept x", () => {
    render(
      <MetricPlotChart metric={METRIC} series={SERIES} xLabel="vert_ft (ft)" name="vert_ft"
        currentValue={40} size={400} running={false} />,
    );
    const svg = screen.getByRole("img");
    const plot = svg.parentElement!;
    // Drawn at half its size: the pointer's px are scaled back to the svg's.
    svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 200, height: 200 }) as DOMRect;
    // jsdom has no PointerEvent: a MouseEvent of the pointer type carries
    // the coordinates React reads (ZParamChart.test.tsx's way).
    const at = (type: "pointerdown" | "pointermove", clientX: number) =>
      fireEvent(svg, new MouseEvent(type, { clientX, clientY: 100, bubbles: true }));
    // The plot spans svg x = 52 … 386 for 20 … 60 ft: 40 ft sits at 219,
    // drawn at 109.5.
    at("pointerdown", 107);
    expect(plot.getAttribute("data-hover")).toBe("40");
    // Every curve's value there, a fixed reference its level.
    expect(plot.getAttribute("data-hover-values")).toBe("−1.75;0.00");
    // A drag across follows: 190 is svg x 380, nearest 60 ft.
    at("pointermove", 190);
    expect(plot.getAttribute("data-hover")).toBe("60");
    expect(plot.getAttribute("data-hover-values")).toBe("—;0.00");
    expect(screen.getByText("vert_ft = 60")).toBeTruthy();
    // Off the plot's sides, nothing.
    at("pointermove", 2);
    expect(plot.getAttribute("data-hover")).toBe("");
    at("pointermove", 110);
    expect(plot.getAttribute("data-hover")).toBe("40");
    fireEvent.pointerLeave(svg);
    expect(plot.getAttribute("data-hover")).toBe("");
  });

  it("does not label the padded floor of its y axis", () => {
    // A range padded below -10: the floor is no value of its own.
    expect(axisTicks({ lo: -10.3, hi: 2.3 }, 5, false)).toEqual([-10, -5, 0]);
    // The default keeps it (VSWR 1 is always labelled).
    expect(axisTicks({ lo: -10.3, hi: 2.3 })[0]).toBe(-10.3);
    const deep: MetricSeries[] = [
      { ...SERIES[0], xs: [20, 40], ys: [-9.6, 1.6] },
    ];
    const el = render(
      <MetricPlotChart metric={METRIC} series={deep} xLabel="vert_ft (ft)" name="vert_ft"
        currentValue={null} size={400} running={false} />,
    ).container;
    const yTicks = [...el.querySelectorAll(".metric-plot-ticks text[text-anchor='end']")].map((t) => t.textContent);
    expect(yTicks).toEqual(["-10", "-5", "0"]);
  });
});

describe("the legend's captions", () => {
  it("names a relative plot's reference, and nothing else", () => {
    expect(metricCaption("vertical", METRIC, true)).toBe("vertical (reference, 0 dB)");
    expect(metricCaption("inverted L", METRIC, false)).toBe("inverted L");
    expect(metricCaption("vertical", { ...METRIC, relativeTo: null }, true)).toBe("vertical");
    expect(metricCaption("vertical", null, true)).toBe("vertical");
  });

  it("names a listed ground's model as the ground tabs do", () => {
    const presets = [{ name: "average", label: "average", eps_r: 13, sigma: 0.005, tooltip: "" }];
    expect(groundSpecWords("finite:13,0.005", presets)).toBe("Sommerfeld · average");
    expect(groundSpecWords("finite", presets)).toBe("Sommerfeld · average");
    expect(groundSpecWords("finite-fast:13,0.005", presets)).toBe("refl-coef · average");
    expect(groundSpecWords("finite-fast:5,0.001", presets)).toBe("refl-coef · εr 5, σ 0.001 S/m");
    expect(groundSpecWords("mininec:13,0.005", presets)).toBe("MININEC · average");
    expect(groundSpecWords("free")).toBe("free space");
    expect(groundSpecWords("pec")).toBe("PEC");
    expect(groundSpecWords("finite:x")).toBe("finite:x");

    const env: CrossEnv = {
      slots: [{ id: "A", label: "A: NEC-5", holds: (s) => s === "nec5", refusal: null }],
      activeSlot: "A",
      grounds: [{ id: "X", label: "X: Sommerfeld · average", holds: (s) => s === "finite:13,0.005" }],
      activeGround: "X",
      soilPresets: presets,
    };
    const listed = { engines: ["nec5"], grounds: ["finite:13,0.005", "finite-fast:13,0.005"] };
    const plan = crossPlan({ slots: ["A"], grounds: ["X"] }, listed, env);
    expect(plan.cells.map((c) => [c.label, c.refused])).toEqual([
      ["nec5, Sommerfeld · average", null],
      // A listed ground no slot holds: named in the same words, its reason
      // in the spec the analysis wrote.
      ["nec5, refl-coef · average", "not drawn: no ground slot holds finite-fast:13,0.005. Add one with + to include it."],
    ]);
    // A listed cell's served label (`an.Cell.label`) carries the spec as a
    // part of its own: the same words there, the state's label kept.
    const cell = {
      label: "dipoles.invvee, low, nec5, finite:13,0.005",
      state: { name: "low", design: "dipoles.invvee", variant: null, knobs: {}, label: "dipoles.invvee, low" },
      engine: "nec5",
      ground: "finite:13,0.005",
      plane: null,
      refused: null,
      param: "vert_ft",
      values: [20],
    };
    const cells = crossPlan({ slots: null, grounds: null }, { engines: null, grounds: null, cells: [cell] }, env);
    expect(cells.cells.map((c) => c.label)).toEqual(["dipoles.invvee, low, nec5, Sommerfeld · average"]);
  });
});
