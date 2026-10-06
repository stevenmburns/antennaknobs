// The analysis chart's map kind (docs/design/sweep-framework-map.md, unit 3):
// what a pick sets, the dwell default, the run inputs, edits and ↺.
import { describe, expect, it } from "vitest";
import type { MapWorkbench } from "../lib/analyses";
import {
  type AnalysisChartState,
  chartDwell,
  chartRunInputs,
  chartView,
  chartViews,
  editMapAxis,
  initialChart,
  pickedEdited,
  pickedName,
  pickMap,
  restoreMapAxes,
  runOnPickKind,
} from "../lib/analysisChart";
import type { SweepRange } from "../lib/sweep";
import { DEFAULT_AXES } from "../lib/sweepAxis";
import { mapCostLine, mapOverLimit } from "../components/results/MapChartControls";
import { mapAxesKeep } from "../lib/keep";

const LF = Array.from({ length: 33 }, (_, i) => Number((0.9 + 0.005 * i).toPrecision(12)));
const ANG = Array.from({ length: 25 }, (_, j) => 2.5 * j);
const TUNING: MapWorkbench = {
  runs: true,
  kind: "map",
  x: { param: "length_factor", values: LF, log: false, lo: 0.9, hi: 1.06, points: 33, spacing: "lin" },
  y: { param: "angle_deg", values: ANG, log: false, lo: 0, hi: 60, points: 25, spacing: "lin" },
  refs: { r: [50, 75], x: [0], swr: null },
  views: ["Map"],
  limit: null,
  note: null,
};
const DESIGN: SweepRange = { lo: 28, hi: 29, spacing: "lin" };
const fresh = (): AnalysisChartState =>
  initialChart({ view: "Smith", axes: DEFAULT_AXES, threshold: 2 });
const env = { resident: true, dwellDefaults: { frequency: true, knob: true }, designRange: DESIGN, values: [], label: "" };
const NOT_INT = { x: false, y: false };

describe("picking a map", () => {
  const c = pickMap(fresh(), "tuning map", TUNING, NOT_INT);

  it("shows the map, named, on its one view", () => {
    expect(c.kind).toBe("map");
    expect(pickedName(c)).toBe("tuning map");
    expect(chartViews(c)).toEqual(["Map"]);
    expect(chartView(c)).toBe("Map");
    expect(c.map!.quantity).toBe("rho");
    expect(c.map!.refs).toEqual(TUNING.refs);
  });

  it("waits for Run by default, whatever the knob sweep's dwell default", () => {
    expect(chartDwell(c, env.dwellDefaults)).toBe(false);
    expect(chartDwell({ ...c, dwell: true }, env.dwellDefaults)).toBe(true);
    expect(runOnPickKind(TUNING)).toBe("map");
  });

  it("asks /map for exactly the served grid, its first cell only", () => {
    const r = chartRunInputs(c, env);
    expect(r.map.wanted).toBe(true);
    expect(r.map.auto).toBe(false);
    expect(r.map.x).toEqual({ param: "length_factor", values: LF });
    expect(r.map.y).toEqual({ param: "angle_deg", values: ANG });
    expect(r.param.wanted).toBe(false);
    expect(r.freq.wanted).toBe(false);
    expect(r.pattern.wanted).toBe(false);
    expect(chartRunInputs(c, { ...env, resident: false }).map.wanted).toBe(false);
  });

  it("an axis edit is still the pick, edited; ↺ restores it", () => {
    const e = editMapAxis(c, "y", { ...c.map!.y, points: 5 });
    expect(pickedName(e)).toBe("tuning map");
    expect(pickedEdited(e)).toBe(true);
    expect(chartRunInputs(e, env).map.y.values).toEqual([0, 15, 30, 45, 60]);
    const back = restoreMapAxes(e);
    expect(pickedEdited(back)).toBe(false);
    expect(chartRunInputs(back, env).map.y.values).toEqual(ANG);
  });

  it("keeps the viewer's colouring across a pick", () => {
    const q = { ...c, map: { ...c.map!, quantity: "reciprocal" as const } };
    expect(pickMap(q, "tuning map", TUNING, NOT_INT).map!.quantity).toBe("reciprocal");
  });
});

describe("the cost line", () => {
  it("counts solves and times them at the live solve's pace", () => {
    expect(mapCostLine(825, 7.5)).toBe("825 solves · ~6 s");
    expect(mapCostLine(121, 1190)).toBe("121 solves · ~2 min");
    expect(mapCostLine(121, 2)).toBe("121 solves · <1 s");
    expect(mapCostLine(825, null)).toBe("825 solves");
  });
  it("over the hosted cap, Run says why", () => {
    expect(mapOverLimit(825, { points: 1000 })).toBeNull();
    expect(mapOverLimit(1089, { points: 1000 })).toBe(
      "1089 points is over the live limit of 1000: reduce the points on x or y",
    );
    expect(mapOverLimit(5000, null)).toBeNull();
  });
});

describe("copy as analysis of an edited map", () => {
  it("each edited axis as a range, never as values; an unedited one not at all", () => {
    const c = pickMap(fresh(), "tuning map", TUNING, NOT_INT);
    const e = editMapAxis(c, "y", { ...c.map!.y, lo: 10, hi: 50, points: 9 });
    expect(
      mapAxesKeep({ x: e.map!.x, y: e.map!.y, edited: { x: false, y: true } }),
    ).toEqual({ y: { lo: 10, hi: 50, points: 9, spacing: "lin" } });
    expect(mapAxesKeep({ x: c.map!.x, y: c.map!.y, edited: { x: false, y: false } })).toBeNull();
  });
});
