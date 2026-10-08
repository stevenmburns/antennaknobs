// A pattern family's cut angle (AK#1950), React-free: what the angle box
// accepts, how it lands on the family's view, that it survives a detour to
// R / X, and how a link carries it. Dan AC6LA (QRZ 1005128 #61): the family
// offered only "Elevation @ 0° az" and "Azimuth @ 10° el". The session's
// half is familyCut.session.test.tsx; the keep's Python half is
// tests/test_family_cut_angle_1950.py.
//
// Mutation notes (run by hand, 2026-10-07; each reverted after):
//   - linkSearch never writing `cut`: "a cut off the view's own rides as
//     cut=" fails (no cut= in the link);
//   - parseDeepLink never reading `cut` (always null): the same test fails
//     on its read-back ("a malformed cut is reported" still passes: the
//     raw text is reported either way);
//   - chartLinkCut returning the angle even at the view's own: "an old link
//     still means what it meant" fails (the link grows cut=0);
//   - setChartView rebuilding the family from FAMILY_PATTERN_VIEWS (as before
//     AK#1950): "the cut survives a detour to R / X" fails;
//   - cutAt not wrapping the bearing: "a bearing wraps" fails.
import { describe, it, expect } from "vitest";
import {
  chartLinkCut,
  chartPatternView,
  chartRunInputs,
  cutAngleProblem,
  FAMILY_PATTERN_VIEWS,
  initialChart,
  pickKnob,
  setChartCut,
  setChartView,
} from "../lib/analysisChart";
import { linkSearch, parseDeepLink } from "../lib/deepLink";
import type { ParamSweepSpec } from "../lib/paramSweep";
import { DEFAULT_AXES } from "../lib/sweepAxis";

const SEED = { view: "Smith" as const, axes: DEFAULT_AXES, threshold: 2 };
const BASE: ParamSweepSpec = { param: "base", lo: 4, hi: 14, points: 11, log: false };
const DWELL = { frequency: true, knob: false };
const ENV = {
  resident: true,
  dwellDefaults: DWELL,
  designRange: { lo: 28, hi: 29.7, spacing: "lin" as const },
  values: [],
  label: "Base",
};

const knobChart = () => pickKnob(initialChart(SEED), null, BASE);
const family = (view: "pattern:0" | "pattern:1" | "pattern:2") => setChartView(knobChart(), view);

describe("a family's cut angle on the chart (AK#1950)", () => {
  it("lands on the view on screen, and the run inputs carry it", () => {
    const el = setChartCut(family("pattern:0"), 35);
    expect(chartPatternView(el)).toEqual({ view: "Elevation", az: 35 });
    expect(chartRunInputs(el, ENV).pattern.elevAzDeg).toBe(35);
    const az = setChartCut(family("pattern:1"), 22);
    expect(chartPatternView(az)).toEqual({ view: "Azimuth", el: 22 });
    expect(chartRunInputs(az, ENV).pattern.azElevDeg).toBe(22);
    // The other cut keeps its own angle.
    expect(az.pattern?.views[0]).toEqual({ view: "Elevation", az: 0 });
    // The shared list is never edited in place.
    expect(FAMILY_PATTERN_VIEWS[1]).toEqual({ view: "Azimuth", el: 10 });
  });

  it("a bearing wraps onto 0–359; an elevation is 1–89; whole degrees only", () => {
    expect(chartPatternView(setChartCut(family("pattern:0"), 370))).toEqual({ view: "Elevation", az: 10 });
    expect(chartPatternView(setChartCut(family("pattern:0"), -10))).toEqual({ view: "Elevation", az: 350 });
    const az = { view: "Azimuth", el: 10 } as const;
    expect(cutAngleProblem(az, 0)).toBe("1–89");
    expect(cutAngleProblem(az, 90)).toBe("1–89");
    expect(cutAngleProblem(az, 89)).toBeNull();
    expect(cutAngleProblem({ view: "Elevation", az: 0 }, 12.5)).toBe("whole degrees");
    // A refused angle, the table, or a chart that is no family: the same chart.
    const c = family("pattern:1");
    expect(setChartCut(c, 0)).toBe(c);
    const table = family("pattern:2");
    expect(setChartCut(table, 30)).toBe(table);
    const knob = knobChart();
    expect(setChartCut(knob, 30)).toBe(knob);
  });

  it("the cut survives a detour to R / X and back", () => {
    const cut = setChartCut(family("pattern:0"), 35);
    const back = setChartView(setChartView(cut, "Rx"), "pattern:0");
    expect(chartPatternView(back)).toEqual({ view: "Elevation", az: 35 });
  });
});

describe("a family's cut angle in a link (AK#1950)", () => {
  const base = { design: "dipoles.invvee", variant: null, analysis: null };
  const fam = { param: "base", lo: 4, hi: 14, points: 6, log: false };

  it("a cut off the view's own rides as cut=, and reads back", () => {
    const c = setChartCut(family("pattern:0"), 35);
    expect(chartLinkCut(c)).toBe(35);
    const search = linkSearch("", { ...base, family: fam, view: "pattern:0", cut: chartLinkCut(c) });
    expect(search).toBe("?design=dipoles.invvee&family=base:4:14:6&view=pattern:0&cut=35");
    expect(parseDeepLink(search)).toMatchObject({ family: fam, view: "pattern:0", cut: 35 });
    expect(parseDeepLink("?design=a.b&family=base:4:14:6&view=pattern:0&cut=-10")?.cut).toBe(-10);
  });

  it("an old link still means what it meant: no cut= at the view's own angle", () => {
    // A family at its own angles links exactly as it did before AK#1950.
    expect(chartLinkCut(family("pattern:0"))).toBeNull();
    expect(chartLinkCut(family("pattern:1"))).toBeNull();
    expect(chartLinkCut(family("pattern:2"))).toBeNull();
    expect(linkSearch("", { ...base, family: fam, view: "pattern:0", cut: null })).toBe(
      "?design=dipoles.invvee&family=base:4:14:6&view=pattern:0",
    );
    // And it reads back as no cut: the session leaves the view's own.
    const old = parseDeepLink("?design=dipoles.invvee&family=base:4:14:6&view=pattern:0");
    expect(old?.cut).toBeUndefined();
    expect(old?.cutProblem).toBeUndefined();
  });

  it("cut= rides only beside a family; another link drops it", () => {
    expect(linkSearch("?cut=35", { ...base, analysis: "x", view: "Rx", cut: 35 })).toBe(
      "?design=dipoles.invvee&analysis=x&view=Rx",
    );
  });

  it("a malformed cut is reported, not applied", () => {
    for (const bad of ["35.5", "abc", "1e2"]) {
      const l = parseDeepLink(`?design=a.b&family=base:4:14:6&view=pattern:0&cut=${bad}`);
      expect(l?.cut).toBeUndefined();
      expect(l?.cutProblem).toContain("whole number of degrees");
    }
  });
});
