// A design's analyses in the workbench (lib/analyses.ts, AK#1757 step 3):
// /analyses' body parsed, and a runnable analysis mapped to the
// Z-vs-parameter view's spec, whose ladder is exactly the served values.
import { describe, it, expect } from "vitest";
import {
  analysisBlocked,
  analysisSpec,
  parseAnalyses,
  type AnalysisWorkbench,
} from "../lib/analyses";
import { DEFAULT_DENSITY_SPEC, DENSITY_LADDER, paramValues, sameSpec } from "../lib/paramSweep";

// E3 on the invvee, as the server serves it (tests/test_analyses_workbench_1757.py).
const E3_VALUES = Array.from({ length: 37 }, (_, i) => 2 + 0.5 * i);
const run = (over: Partial<Extract<AnalysisWorkbench, { runs: true }>>) =>
  ({ runs: true, param: "base", values: E3_VALUES, log: false, note: null, ...over }) as Extract<
    AnalysisWorkbench,
    { runs: true }
  >;

describe("analysisSpec", () => {
  it("E3: base, 2…20, 37 linear points, and the header's ladder is the served one", () => {
    const spec = analysisSpec(run({}), false);
    expect(spec).toEqual({ param: "base", lo: 2, hi: 20, points: 37, log: false });
    expect(paramValues(spec, false)).toEqual(E3_VALUES);
  });

  it("E1: the density ladder is the view's own default density spec", () => {
    const spec = analysisSpec(
      run({ param: "n_per_wire", values: [...DENSITY_LADDER], log: true }),
      false,
    );
    expect(sameSpec(spec, DEFAULT_DENSITY_SPEC)).toBe(true);
    expect(paramValues(spec, true)).toEqual([...DENSITY_LADDER]);
  });

  it("a deck's density knob carries the ladder itself: the header's would round differently", () => {
    const w = run({ param: "tmp_segs", values: [...DENSITY_LADDER], log: true });
    const spec = analysisSpec(w, true);
    // A geometric 8…68 in 7 points, rounded, is 8, 11, 16, … — not the ladder.
    const header = { param: "tmp_segs", lo: 8, hi: 68, points: 7, log: true };
    expect(paramValues(header, true)).not.toEqual([...DENSITY_LADDER]);
    expect(spec.values).toEqual([...DENSITY_LADDER]);
    expect(paramValues(spec, true)).toEqual([...DENSITY_LADDER]);
  });
});

describe("analysisBlocked", () => {
  const knobs = new Set(["base", "length_factor"]);
  it("a runnable analysis on a sweepable knob, or density, runs", () => {
    expect(analysisBlocked(run({}), knobs)).toBeNull();
    expect(analysisBlocked(run({ param: "n_per_wire" }), knobs)).toBeNull();
  });
  it("the server's why, or a knob this view cannot sweep, blocks it", () => {
    expect(analysisBlocked({ runs: false, why: "hold: step 6" }, knobs)).toBe("hold: step 6");
    expect(analysisBlocked(run({ param: "angle_deg" }), knobs)).toMatch(/angle_deg is not a knob/);
  });
});

describe("parseAnalyses", () => {
  it("keeps well-formed entries and drops the rest", () => {
    const got = parseAnalyses({
      analyses: [
        {
          name: "height",
          summary: "height (base) 2..20, 37 points",
          code: "an.Analysis(...)",
          problems: [],
          workbench: { runs: true, param: "base", values: [2, 20], log: false, note: "n" },
        },
        { name: "match", workbench: { runs: false, why: "step 6" } },
        { name: "bad", workbench: { runs: true, param: "base", values: ["x"] } },
        { workbench: { runs: false, why: "no name" } },
      ],
    });
    expect(got.map((a) => a.name)).toEqual(["height", "match"]);
    expect(got[0].workbench).toEqual({
      runs: true,
      param: "base",
      values: [2, 20],
      log: false,
      note: "n",
    });
    expect(got[1].workbench).toEqual({ runs: false, why: "step 6" });
  });
  it("no analyses on a body without them (an older server, a stub)", () => {
    expect(parseAnalyses({})).toEqual([]);
    expect(parseAnalyses(null)).toEqual([]);
  });
});
