// A held knob sweep in the workbench (AK#1757, sweep-framework step 6),
// React-free: how /analyses' hold is read, what a held pick sets on a chart
// (its views, its dwell switch, the hold riding on every curve's request),
// what makes a held curve stale, where it breaks, and its table.
import { describe, it, expect } from "vitest";
import { type HoldRun, parseAnalyses } from "../lib/analyses";
import {
  chartDwell,
  chartHold,
  chartRunInputs,
  chartView,
  chartViews,
  initialChart,
  pickKnob,
  setChartView,
} from "../lib/analysisChart";
import { chartTable } from "../lib/chartTable";
import { gapBetween, type ParamSweepSpec } from "../lib/paramSweep";
import { DEFAULT_AXES } from "../lib/sweepAxis";
import { paramSweepSignature } from "../components/session/useAnalysisRunners";

const SPEC = { an: "Hold", objective: "resonance", adjust: ["length_factor"], z0: null, warm_start: true };
const SERVED_HOLD = {
  objective: "resonance",
  knobs: ["length_factor"],
  bounds: { length_factor: [0.8, 1.25] },
  z0: null,
  warm_start: true,
  spec: SPEC,
};
const HOLD: HoldRun = {
  objective: "resonance",
  knobs: ["length_factor"],
  bounds: { length_factor: [0.8, 1.25] },
  z0: null,
  warmStart: true,
  spec: SPEC,
};
const ANGLE: ParamSweepSpec = { param: "angle_deg", lo: 0, hi: 60, points: 25, log: false };
const SEED = { view: "Smith" as const, axes: DEFAULT_AXES, threshold: 2 };
const DWELL = { frequency: true, knob: true };
const ENV = { resident: true, dwellDefaults: DWELL, designRange: { lo: 14, hi: 15, spacing: "lin" as const }, values: [0, 30, 60], label: "angle" };

const entry = (workbench: Record<string, unknown>) => ({
  analyses: [{ name: "resonance vs angle", summary: "", code: "", problems: [], workbench }],
});
const knobWb = (over: Record<string, unknown> = {}) => ({
  runs: true,
  kind: "knob",
  param: "angle_deg",
  values: [0, 30, 60],
  log: false,
  views: ["Rx", "Knobs"],
  note: null,
  hold: SERVED_HOLD,
  ...over,
});

describe("/analyses' hold", () => {
  it("is read with its knobs, bounds, Z0, warm start and opaque spec; Knobs is a view of it", () => {
    const [a] = parseAnalyses(entry(knobWb()));
    expect(a.workbench.runs && a.workbench.kind === "knob" && a.workbench.hold).toEqual(HOLD);
    expect(a.workbench.runs && a.workbench.kind === "knob" && a.workbench.views).toEqual(["Rx", "Knobs"]);
  });

  it("a knob analysis without one has no Knobs view, and a malformed hold drops the entry", () => {
    const [plain] = parseAnalyses(entry(knobWb({ hold: null })));
    expect(plain.workbench.runs && plain.workbench.kind === "knob" && plain.workbench.views).toEqual(["Rx"]);
    expect(plain.workbench.runs && plain.workbench.kind === "knob" && plain.workbench.hold).toBeUndefined();
    // A hold the page cannot read must not run as a plain sweep.
    expect(parseAnalyses(entry(knobWb({ hold: { objective: "resonance" } })))).toEqual([]);
  });
});

describe("a held pick on the chart", () => {
  const held = () => pickKnob(initialChart(SEED), "resonance vs angle", ANGLE, ["Rx", "Knobs"], null, HOLD);

  it("runs its hold on every curve's request, and offers the Knobs view", () => {
    const c = held();
    expect(chartHold(c)).toEqual(HOLD);
    expect(chartRunInputs(c, ENV).param.req.hold).toEqual(HOLD);
    expect(chartViews(c)).toEqual(["Rx", "Smith", "Table", "Knobs"]);
    expect(chartView(setChartView(c, "Knobs"))).toBe("Knobs");
  });

  it("runs on Run, never by itself, unless the viewer flips the chart's switch on", () => {
    const c = held();
    // The knob default here is ON (convergence_sweep): a held pick is still off.
    expect(chartDwell(c, DWELL)).toBe(false);
    expect(chartRunInputs(c, ENV).param.req.auto).toBe(false);
    expect(chartDwell({ ...c, dwell: true }, DWELL)).toBe(true);
  });

  it("leaves with its pick: another knob or 'Sweep a knob' runs plain, off the Knobs view", () => {
    const c = setChartView(held(), "Knobs");
    const other = pickKnob(c, null, { ...ANGLE, param: "base" });
    expect(chartHold(other)).toBeNull();
    expect(chartRunInputs(other, ENV).param.req.hold).toBeUndefined();
    expect(chartViews(other)).toEqual(["Rx", "Smith", "Table"]);
    expect(chartView(other)).toBe("Rx");
    // An edit of the picked range keeps the pick, and so the hold.
    const edited = { ...c, knob: { ...c.knob, spec: { ...ANGLE, points: 5 } } };
    expect(chartHold(edited)).toEqual(HOLD);
  });
});

describe("a held curve", () => {
  it("is not staled by a drag of its held knob (it starts from the defaults), but is by the hold", () => {
    const req = { geometry: "dipoles.invvee", length_factor: 0.97, base: 7 } as never;
    const sweep = { param: "angle_deg", values: [0, 30, 60], hold: HOLD };
    const dragged = { ...(req as object), length_factor: 1.0 } as never;
    expect(paramSweepSignature(dragged, sweep)).toBe(paramSweepSignature(req, sweep));
    const moved = { ...(req as object), base: 9 } as never;
    expect(paramSweepSignature(moved, sweep)).not.toBe(paramSweepSignature(req, sweep));
    // The plain sweep of the same knob is another curve, and keeps its old key.
    const plain = { param: "angle_deg", values: [0, 30, 60] };
    expect(paramSweepSignature(req, plain)).not.toBe(paramSweepSignature(req, sweep));
    expect(paramSweepSignature(dragged, plain)).not.toBe(paramSweepSignature(req, plain));
  });

  it("breaks only across a gap strictly between two drawn points", () => {
    const gaps = [{ value: 30, reason: "no root" }];
    expect(gapBetween(gaps, 20, 40)).toBe(true);
    expect(gapBetween(gaps, 40, 20)).toBe(true);
    expect(gapBetween(gaps, 0, 20)).toBe(false);
    expect(gapBetween(gaps, 30, 40)).toBe(false);
    expect(gapBetween(undefined, 0, 60)).toBe(false);
  });

  it("tables its held knobs beside R and X, and a gap as its reason, never a value", () => {
    const t = chartTable(
      "knob",
      "angle_deg",
      [
        {
          label: "",
          xs: [0, 60],
          re: [72.08, 60.5],
          im: [0.0001, -0.0002],
          held: { length_factor: [0.97051, 1.00563] },
          gaps: [{ value: 30, reason: "no resonance held (budget)" }],
        },
      ],
      50,
    );
    expect(t.groups[0].columns).toEqual(["R (Ω)", "X (Ω)", "length_factor"]);
    expect(t.rows).toEqual([
      ["0", "72.080", "+0.000", "0.97051"],
      ["30", "gap", "no resonance held (budget)", ""],
      ["60", "60.500", "-0.000", "1.00563"],
    ]);
  });
});
