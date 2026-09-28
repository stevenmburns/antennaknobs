// A design's analyses in the workbench (lib/analyses.ts, AK#1757 step 3):
// /analyses' body parsed, and a runnable analysis mapped to the
// Z-vs-parameter view's spec, whose ladder is exactly the served values.
import { describe, it, expect } from "vitest";
import {
  analysisBlocked,
  analysisSpec,
  frequencyPick,
  parseAnalyses,
  type FrequencyWorkbench,
  type KnobWorkbench,
} from "../lib/analyses";
import type { SweepRange } from "../lib/sweep";
import { RECIPROCAL, RHO } from "../lib/sweepAxis";
import { DEFAULT_DENSITY_SPEC, DENSITY_LADDER, paramValues, sameSpec } from "../lib/paramSweep";

// E3 on the invvee, as the server serves it (tests/test_analyses_workbench_1757.py).
const E3_VALUES = Array.from({ length: 37 }, (_, i) => 2 + 0.5 * i);
const run = (over: Partial<KnobWorkbench>): KnobWorkbench => ({
  runs: true,
  kind: "knob",
  param: "base",
  values: E3_VALUES,
  log: false,
  note: null,
  ...over,
});

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
    // An entry without `kind` (a step-3 server) is a knob sweep.
    expect(got[0].workbench).toEqual({
      runs: true,
      kind: "knob",
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

// E4 as the server serves it: the deck's Generator sweep, 14.0-14.35 MHz by
// 0.025 (tests/test_analyses_frequency_1757.py pins the served entry).
const E4_RANGE = { lo: 14, hi: 14.35, spacing: "lin", step: 0.025, source: "file" } as const;
const freq = (over: Partial<FrequencyWorkbench>): FrequencyWorkbench => ({
  runs: true,
  kind: "frequency",
  range: E4_RANGE,
  level: "file",
  points: null,
  views: ["Swr"],
  swr: { scale: "rho", threshold: 2 },
  note: null,
  ...over,
});
const E4_OWN: SweepRange = { lo: 14, hi: 14.35, spacing: "lin", step: 0.025 };
const POLICY: SweepRange = { lo: 14, hi: 14.35, spacing: "log" };

describe("frequency analyses (step 4)", () => {
  it("parses a frequency entry, and keeps only the views the workbench draws", () => {
    const [a] = parseAnalyses({
      analyses: [
        {
          name: "band SWR",
          workbench: {
            runs: true,
            kind: "frequency",
            range: E4_RANGE,
            level: "file",
            points: null,
            views: ["Swr", "Map", "Smith"],
            swr: { scale: "rho", threshold: 2 },
            note: null,
          },
        },
      ],
    });
    expect(a.workbench).toEqual(freq({ views: ["Swr", "Smith"] }));
  });

  it("a policy-level entry serves no range: the session's band policy places it", () => {
    const [a] = parseAnalyses({
      analyses: [
        {
          name: "band SWR",
          workbench: {
            runs: true,
            kind: "frequency",
            range: null,
            level: "policy",
            points: null,
            views: ["Swr"],
            swr: { scale: "auto", threshold: 2 },
          },
        },
      ],
    });
    expect(a.workbench).toMatchObject({ runs: true, kind: "frequency", range: null });
  });

  it("is never blocked by the knob list: it is not a knob sweep", () => {
    expect(analysisBlocked(freq({}), new Set())).toBeNull();
  });

  it("E4: the deck's own range clears the edit; the scale and threshold are the view's", () => {
    expect(frequencyPick(freq({}), E4_OWN)).toEqual({
      range: null,
      view: "vswr",
      vswr: RHO,
      threshold: 2,
    });
  });

  it("a range of its own, or a point count, is the session's edit", () => {
    const own = { lo: 13.9, hi: 14.5, spacing: "lin", points: 25, source: "design" } as const;
    expect(frequencyPick(freq({ range: own, level: "analysis" }), E4_OWN).range).toEqual({
      lo: 13.9,
      hi: 14.5,
      spacing: "lin",
      step: (14.5 - 13.9) / 24,
    });
    expect(frequencyPick(freq({ range: null, level: "policy", points: 31 }), POLICY).range).toEqual({
      ...POLICY,
      points: 31,
    });
  });

  it("the policy with no count of its own is the design range, unedited", () => {
    expect(frequencyPick(freq({ range: null, level: "policy" }), POLICY).range).toBeNull();
  });

  it("auto is the 1–∞ reciprocal scale; no Swr view leaves the scale alone; the threshold clamps", () => {
    expect(frequencyPick(freq({ swr: { scale: "auto", threshold: 2 } }), E4_OWN).vswr).toEqual(
      RECIPROCAL,
    );
    const smith = frequencyPick(
      freq({ views: ["Smith"], swr: { scale: null, threshold: 50 } }),
      E4_OWN,
    );
    expect(smith.vswr).toBeNull();
    expect(smith.view).toBe("smith");
    expect(smith.threshold).toBe(20);
  });
});
