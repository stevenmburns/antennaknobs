// An analysis chart's engine and ground crosses (AK#1757 step 5 unit 4,
// lib/chartCells.ts): which slots a chart compares, its cells, their CLI
// labels, the refused cells and the curve cap. React-free.
import { describe, expect, it } from "vitest";
import {
  capRefusal,
  checkedGrounds,
  checkedSlots,
  type CrossEnv,
  crossPlan,
  CURVE_CAP,
  engineSpecHeld,
  FOLLOW_ACTIVE,
  groundSpecHeld,
  NOTHING_LISTED,
  preselect,
  refusedLines,
} from "../lib/chartCells";

// Five solver slots and four ground slots: ids are open-ended (A…E, 1…5),
// so nothing here may assume three.
const ENGINES: Record<string, string> = {
  A: "momwire:bspline",
  B: "momwire:razor-2p",
  C: "pynec",
  D: "nec5",
  E: "momwire:sinusoidal",
};
const GROUNDS: Record<string, string> = { "1": "finite:13,0.005", "2": "free", "3": "pec", "4": "finite:5,0.001" };

const env = (over: Partial<CrossEnv> = {}): CrossEnv => ({
  slots: Object.entries(ENGINES).map(([id, spec]) => ({
    id,
    label: `${id}: ${spec}`,
    holds: (s: string) => s === spec,
    refusal: null,
  })),
  activeSlot: "A",
  grounds: Object.entries(GROUNDS).map(([id, spec]) => ({
    id,
    label: `${id}: ${spec}`,
    holds: (s: string) => s === spec,
  })),
  activeGround: "1",
  ...over,
});

describe("the default cross follows the active slots", () => {
  it("is one cell: the active slot on the active ground, named by its engine", () => {
    const plan = crossPlan(FOLLOW_ACTIVE, NOTHING_LISTED, env({ activeSlot: "C", activeGround: "2" }));
    expect(plan.cells).toEqual([
      { key: "C|2", label: "C: pynec", slot: "C", ground: "2", refused: null },
    ]);
    expect(plan.capRefusal).toBeNull();
  });

  it("never ticks nothing: an empty or stale list falls back to the active slot", () => {
    const e = env({ activeSlot: "B", activeGround: "3" });
    expect(checkedSlots({ slots: [], grounds: null }, e)).toEqual(["B"]);
    expect(checkedSlots({ slots: ["Z"], grounds: null }, e)).toEqual(["B"]);
    expect(checkedGrounds({ slots: null, grounds: ["9"] }, e)).toEqual(["3"]);
  });

  it("reads the ticked ids in id order, whatever order they were ticked in", () => {
    expect(checkedSlots({ slots: ["E", "A", "D"], grounds: null }, env())).toEqual(["A", "D", "E"]);
  });
});

describe("the engine cross", () => {
  it("draws one cell per ticked slot, each named by its slot, on the ground each", () => {
    const plan = crossPlan({ slots: ["A", "E"], grounds: null }, NOTHING_LISTED, env());
    expect(plan.cells.map((c) => [c.slot, c.ground, c.label])).toEqual([
      ["A", "1", "A: momwire:bspline"],
      ["E", "1", "E: momwire:sinusoidal"],
    ]);
  });

  it("preselects the slots holding a pick's engines, in the analysis's order", () => {
    const listed = { engines: ["nec5", "momwire:bspline"], grounds: null };
    const cross = preselect(listed, env());
    expect(cross).toEqual({ slots: ["D", "A"], grounds: null });
    const plan = crossPlan(cross, listed, env());
    // Named as the analysis spells them, in its order (the CLI's cells).
    expect(plan.cells.map((c) => [c.slot, c.label])).toEqual([
      ["D", "nec5"],
      ["A", "momwire:bspline"],
    ]);
  });

  it("names a listed engine no slot holds as a refused cell, and draws the rest", () => {
    const listed = { engines: ["momwire:bspline", "nec2", "nec5"], grounds: null };
    const plan = crossPlan(preselect(listed, env()), listed, env());
    expect(plan.cells.map((c) => [c.label, c.slot, c.refused])).toEqual([
      ["momwire:bspline", "A", null],
      ["nec2", null, "no solver slot holds nec2"],
      ["nec5", "D", null],
    ]);
    expect(refusedLines(plan)).toEqual(["nec2: no solver slot holds nec2"]);
  });

  it("draws the active slot beside refused cells when a pick names nothing held", () => {
    const listed = { engines: ["nec2"], grounds: null };
    const plan = crossPlan(preselect(listed, env()), listed, env());
    expect(plan.cells.map((c) => [c.label, c.slot, c.refused])).toEqual([
      ["nec2", null, "no solver slot holds nec2"],
      ["A: momwire:bspline", "A", null],
    ]);
  });

  it("refuses a slot that cannot draw the design, with the slot's reason", () => {
    const e = env();
    e.slots[2] = { ...e.slots[2], refusal: "a poor match for this design" };
    const plan = crossPlan({ slots: ["A", "C"], grounds: null }, NOTHING_LISTED, e);
    expect(plan.cells.map((c) => c.refused)).toEqual([null, "a poor match for this design"]);
  });
});

describe("the ground cross", () => {
  it("draws one cell per ticked ground slot, on the chart's engine", () => {
    const plan = crossPlan({ slots: null, grounds: ["2", "4"] }, NOTHING_LISTED, env({ activeSlot: "B" }));
    expect(plan.cells.map((c) => [c.slot, c.ground, c.label])).toEqual([
      ["B", "2", "2: free"],
      ["B", "4", "4: finite:5,0.001"],
    ]);
  });

  it("names a listed ground no slot holds as a refused cell", () => {
    const listed = { engines: null, grounds: ["free", "finite:20,0.03"] };
    const plan = crossPlan(preselect(listed, env()), listed, env());
    expect(plan.cells.map((c) => [c.label, c.ground, c.refused])).toEqual([
      ["free", "2", null],
      ["finite:20,0.03", null, "no ground slot holds finite:20,0.03"],
    ]);
  });
});

describe("engines x grounds", () => {
  it("is engine-major, each label naming both, joined by ', ' as the CLI's", () => {
    const plan = crossPlan({ slots: ["A", "B"], grounds: ["1", "2"] }, NOTHING_LISTED, env());
    expect(plan.cells.map((c) => c.label)).toEqual([
      "A: momwire:bspline, 1: finite:13,0.005",
      "A: momwire:bspline, 2: free",
      "B: momwire:razor-2p, 1: finite:13,0.005",
      "B: momwire:razor-2p, 2: free",
    ]);
  });

  it("takes up to the cap: 3 x 2 = 6 curves draw", () => {
    const plan = crossPlan({ slots: ["A", "B", "C"], grounds: ["1", "2"] }, NOTHING_LISTED, env());
    expect(CURVE_CAP).toBe(6);
    expect(plan.capRefusal).toBeNull();
    expect(plan.cells).toHaveLength(6);
  });

  it("refuses over the cap with the CLI's wording, and draws nothing rather than truncate", () => {
    const plan = crossPlan({ slots: ["A", "B", "C", "D", "E"], grounds: ["1", "2"] }, NOTHING_LISTED, env());
    expect(plan.capRefusal).toBe("REFUSED: 5 engines x 2 grounds = 10 curves, over the cap of 6");
    expect(plan.cells).toEqual([]);
    expect(refusedLines(plan)).toEqual([plan.capRefusal]);
    expect(capRefusal(7, 1)).toBe("REFUSED: 7 engines x 1 grounds = 7 curves, over the cap of 6");
    expect(capRefusal(1, 6)).toBeNull();
  });

  it("counts a refused cell against the cap, as the CLI counts every listed curve", () => {
    const listed = { engines: ["momwire:bspline", "nec2", "nec5", "pynec"], grounds: ["free", "pec"] };
    const plan = crossPlan(preselect(listed, env()), listed, env());
    expect(plan.capRefusal).toBe("REFUSED: 4 engines x 2 grounds = 8 curves, over the cap of 6");
  });
});

describe("which slot holds a spec", () => {
  const b = (kind: "momwire" | "pynec" | "nec5" | "nec2", name: string) => ({ kind, name });
  it("reads --engine's spellings", () => {
    expect(engineSpecHeld("nec5", b("nec5", "nec5"), null)).toBe(true);
    expect(engineSpecHeld("pynec", b("pynec", "pynec"), null)).toBe(true);
    expect(engineSpecHeld("nec5", b("nec2", "nec2"), null)).toBe(false);
    expect(engineSpecHeld("momwire:razor-2p", b("momwire", "razor-2p"), null)).toBe(true);
    // The old spelling of razor-2p.
    expect(engineSpecHeld("momwire:razor-nec5", b("momwire", "razor-2p"), null)).toBe(true);
    // Bare momwire is the CLI's default basis, B-spline, and bspline-d1 its
    // degree-1 form.
    expect(engineSpecHeld("momwire", b("momwire", "bspline"), 2)).toBe(true);
    expect(engineSpecHeld("momwire:bspline", b("momwire", "bspline"), undefined)).toBe(true);
    expect(engineSpecHeld("momwire:bspline", b("momwire", "bspline"), 1)).toBe(false);
    expect(engineSpecHeld("momwire:bspline-d1", b("momwire", "bspline"), 1)).toBe(true);
    expect(engineSpecHeld("momwire:sinusoidal", b("momwire", "bspline"), 2)).toBe(false);
    // A basis suffix belongs to momwire only.
    expect(engineSpecHeld("nec5:x", b("nec5", "nec5"), null)).toBe(false);
  });

  it("reads --ground's spellings, soil included", () => {
    const g = (over: object) => ({ enabled: true, type: "finite" as const, method: "sommerfeld" as const, soil: null, ...over });
    const avg = { eps_r: 13, sigma: 0.005 };
    expect(groundSpecHeld("free", g({ enabled: false }), avg)).toBe(true);
    expect(groundSpecHeld("free", g({}), avg)).toBe(false);
    expect(groundSpecHeld("pec", g({ type: "pec" }), avg)).toBe(true);
    // finite is Sommerfeld at the CLI's default soil; a slot whose soil is
    // not known yet reads as the served default.
    expect(groundSpecHeld("finite", g({}), avg)).toBe(true);
    expect(groundSpecHeld("finite:13,0.005", g({ soil: avg }), null)).toBe(true);
    expect(groundSpecHeld("finite:5,0.001", g({ soil: avg }), null)).toBe(false);
    expect(groundSpecHeld("finite:5,0.001", g({ soil: { eps_r: 5, sigma: 0.001 } }), null)).toBe(true);
    expect(groundSpecHeld("finite", g({ method: "fast" }), avg)).toBe(false);
    expect(groundSpecHeld("finite-fast", g({ method: "fast" }), avg)).toBe(true);
    expect(groundSpecHeld("mininec:13,0.005", g({ method: "mininec" }), avg)).toBe(true);
    // A terrain slot holds no CLI spec; junk holds nothing.
    expect(groundSpecHeld("finite", g({ type: "terrain" }), avg)).toBe(false);
    expect(groundSpecHeld("finite:x", g({}), avg)).toBe(false);
    expect(groundSpecHeld("sand", g({}), avg)).toBe(false);
  });
});
