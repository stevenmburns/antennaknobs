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
  engineRefusal,
  engineSpecHeld,
  FOLLOW_ACTIVE,
  groundSpecHeld,
  type ListedCross,
  NOTHING_LISTED,
  preselect,
  refusedLines,
  servedCell,
  skippedNote,
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
const GROUNDS: Record<string, string> = { "X": "finite:13,0.005", "Y": "free", "Z": "pec", "U": "finite:5,0.001" };

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
  activeGround: "X",
  ...over,
});

describe("the default cross follows the active slots", () => {
  it("is one cell: the active slot on the active ground, named by its engine", () => {
    const plan = crossPlan(FOLLOW_ACTIVE, NOTHING_LISTED, env({ activeSlot: "C", activeGround: "Y" }));
    expect(plan.cells).toEqual([
      { key: "C|Y", label: "C: pynec", slot: "C", ground: "Y", refused: null },
    ]);
    expect(plan.capRefusal).toBeNull();
  });

  it("never ticks nothing: an empty or stale list falls back to the active slot", () => {
    const e = env({ activeSlot: "B", activeGround: "Z" });
    expect(checkedSlots({ slots: [], grounds: null }, e)).toEqual(["B"]);
    expect(checkedSlots({ slots: ["Z"], grounds: null }, e)).toEqual(["B"]);
    expect(checkedGrounds({ slots: null, grounds: ["W"] }, e)).toEqual(["Z"]);
  });

  it("reads the ticked ids in id order, whatever order they were ticked in", () => {
    expect(checkedSlots({ slots: ["E", "A", "D"], grounds: null }, env())).toEqual(["A", "D", "E"]);
  });
});

describe("the engine cross", () => {
  it("draws one cell per ticked slot, each named by its slot, on the ground each", () => {
    const plan = crossPlan({ slots: ["A", "E"], grounds: null }, NOTHING_LISTED, env());
    expect(plan.cells.map((c) => [c.slot, c.ground, c.label])).toEqual([
      ["A", "X", "A: momwire:bspline"],
      ["E", "X", "E: momwire:sinusoidal"],
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

  it("skips a listed engine no slot holds: no cell, no refusal, named in the note; the rest draw", () => {
    const listed = { engines: ["momwire:bspline", "nec2", "nec5"], grounds: null };
    const plan = crossPlan(preselect(listed, env()), listed, env());
    expect(plan.cells.map((c) => [c.label, c.slot, c.refused])).toEqual([
      ["momwire:bspline", "A", null],
      ["nec5", "D", null],
    ]);
    expect(refusedLines(plan)).toEqual([]);
    expect(plan.skipped).toEqual(["nec2"]);
    expect(plan.fallback).toBe(false);
    expect(skippedNote(plan)).toBe("skipped: NEC-2, which no slot holds. Put it in a slot to include it.");
  });

  it("draws every slot in place of a pick whose every listed engine is skipped, and says so", () => {
    const listed = { engines: ["nec2"], grounds: null };
    const cross = preselect(listed, env());
    expect(cross.slots).toEqual(["A", "B", "C", "D", "E"]);
    const plan = crossPlan(cross, listed, env());
    expect(plan.cells.map((c) => [c.label, c.slot, c.refused])).toEqual([
      ["A: momwire:bspline", "A", null],
      ["B: momwire:razor-2p", "B", null],
      ["C: pynec", "C", null],
      ["D: nec5", "D", null],
      ["E: momwire:sinusoidal", "E", null],
    ]);
    expect(plan.fallback).toBe(true);
    expect(skippedNote(plan)).toBe(
      "skipped: NEC-2, which no slot holds, so the chart draws your slots instead. Put it in a slot to include it.",
    );
  });

  it("refuses a slot that cannot draw the design, with the slot's reason", () => {
    const e = env();
    e.slots[2] = { ...e.slots[2], refusal: "a poor match for this design" };
    const plan = crossPlan({ slots: ["A", "C"], grounds: null }, NOTHING_LISTED, e);
    expect(plan.cells.map((c) => c.refused)).toEqual([null, "a poor match for this design"]);
  });
});

describe("a pair the engine refuses (AK#1856)", () => {
  // Slot D's NEC-5 refuses ground U, as NEC-5 refuses a refl-coef slot.
  const refusing = env({
    groundRefusal: (slot, ground) => (slot === "D" && ground === "U" ? "no refl-coef on NEC-5" : null),
  });

  it("refuses that cell in the served words and draws the rest", () => {
    const plan = crossPlan({ slots: ["A", "D"], grounds: ["X", "U"] }, NOTHING_LISTED, refusing);
    expect(plan.cells.map((c) => [c.slot, c.ground, c.refused])).toEqual([
      ["A", "X", null],
      ["A", "U", null],
      ["D", "X", null],
      ["D", "U", "no refl-coef on NEC-5"],
    ]);
    expect(refusedLines(plan)).toEqual(["D: nec5, U: finite:5,0.001: no refl-coef on NEC-5"]);
  });

  it("refuses a listed cell on that pair", () => {
    const listed: ListedCross = {
      engines: null,
      grounds: null,
      cells: [
        { label: "nec5 on U", state: null, engine: "nec5", ground: "finite:5,0.001", plane: null, refused: null, param: null, values: null },
      ],
    };
    const plan = crossPlan(FOLLOW_ACTIVE, listed, refusing);
    expect(plan.cells.map((c) => c.refused)).toEqual(["no refl-coef on NEC-5"]);
  });
});

describe("the ground cross", () => {
  it("draws one cell per ticked ground slot, on the chart's engine", () => {
    const plan = crossPlan({ slots: null, grounds: ["Y", "U"] }, NOTHING_LISTED, env({ activeSlot: "B" }));
    expect(plan.cells.map((c) => [c.slot, c.ground, c.label])).toEqual([
      ["B", "Y", "Y: free"],
      ["B", "U", "U: finite:5,0.001"],
    ]);
  });

  it("names a listed ground no slot holds as a refused cell", () => {
    const listed = { engines: null, grounds: ["free", "finite:20,0.03"] };
    const plan = crossPlan(preselect(listed, env()), listed, env());
    expect(plan.cells.map((c) => [c.label, c.ground, c.refused])).toEqual([
      ["free", "Y", null],
      ["finite:20,0.03", null, "no ground slot holds finite:20,0.03"],
    ]);
  });
});

describe("engines x grounds", () => {
  it("is engine-major, each label naming both, joined by ', ' as the CLI's", () => {
    const plan = crossPlan({ slots: ["A", "B"], grounds: ["X", "Y"] }, NOTHING_LISTED, env());
    expect(plan.cells.map((c) => c.label)).toEqual([
      "A: momwire:bspline, X: finite:13,0.005",
      "A: momwire:bspline, Y: free",
      "B: momwire:razor-2p, X: finite:13,0.005",
      "B: momwire:razor-2p, Y: free",
    ]);
  });

  it("takes up to the cap: 3 x 2 = 6 curves draw", () => {
    const plan = crossPlan({ slots: ["A", "B", "C"], grounds: ["X", "Y"] }, NOTHING_LISTED, env());
    expect(CURVE_CAP).toBe(6);
    expect(plan.capRefusal).toBeNull();
    expect(plan.cells).toHaveLength(6);
  });

  it("refuses over the cap with the CLI's wording, and draws nothing rather than truncate", () => {
    const plan = crossPlan({ slots: ["A", "B", "C", "D", "E"], grounds: ["X", "Y"] }, NOTHING_LISTED, env());
    expect(plan.capRefusal).toBe("REFUSED: 5 engines x 2 grounds = 10 curves, over the cap of 6");
    expect(plan.cells).toEqual([]);
    expect(refusedLines(plan)).toEqual([plan.capRefusal]);
    expect(capRefusal([{ n: 7, kind: "engines" }])).toBe(
      "REFUSED: 7 engines = 7 curves, over the cap of 6",
    );
    expect(capRefusal([{ n: 1, kind: "engines" }, { n: 6, kind: "grounds" }])).toBeNull();
  });

  it("counts a refused ground against the cap, and a skipped engine not, since it draws no curve", () => {
    // nec2 is skipped: 3 engines x 2 grounds, the second refused, is 6.
    const listed = { engines: ["momwire:bspline", "nec2", "nec5", "pynec"], grounds: ["free", "finite:20,0.03"] };
    const plan = crossPlan(preselect(listed, env()), listed, env());
    expect(plan.capRefusal).toBeNull();
    expect(plan.cells).toHaveLength(6);
    expect(plan.cells.filter((c) => c.refused).map((c) => c.refused)).toEqual([
      "no ground slot holds finite:20,0.03",
      "no ground slot holds finite:20,0.03",
      "no ground slot holds finite:20,0.03",
    ]);
    const four = { engines: ["momwire:bspline", "nec2", "nec5", "pynec", "momwire:razor-2p"], grounds: ["free", "pec"] };
    expect(crossPlan(preselect(four, env()), four, env()).capRefusal).toBe(
      "REFUSED: 4 engines x 2 grounds = 8 curves, over the cap of 6",
    );
  });
});

// Steve's slots (2026-10-01): B-spline d=2, B-spline d=1 and PyNEC, held as
// the session holds them (engineSpecHeld on the slot's backend and degree).
const steve = (): CrossEnv => {
  const slot = (id: string, kind: "momwire" | "pynec", name: string, degree: number | null) => ({
    id,
    label: `${id}: ${name}${degree ? ` d=${degree}` : ""}`,
    holds: (spec: string) => engineSpecHeld(spec, { kind, name }, degree),
    refusal: null,
  });
  return {
    slots: [slot("A", "momwire", "bspline", 2), slot("B", "momwire", "bspline", 1), slot("C", "pynec", "pynec", null)],
    activeSlot: "A",
    grounds: [{ id: "1", label: "1: finite:13,0.005", holds: (s: string) => s === "finite:13,0.005" }],
    activeGround: "1",
  };
};

describe("listed engines on Steve's slots (skipped, not refused)", () => {
  // E1, invvee's convergence: three engines, one ground.
  const E1: ListedCross = {
    engines: ["momwire:bspline", "momwire:razor-2p", "nec5"],
    grounds: ["finite:13,0.005"],
  };

  it("E1 draws its one held engine, B-spline on A, with a note naming the two skipped", () => {
    const cross = preselect(E1, steve());
    expect(cross.slots).toEqual(["A"]);
    const plan = crossPlan(cross, E1, steve());
    // Mutation check: with the skip reverted to a refused cell (axis()
    // pushing `{ id: null, refused }` for a solver spec again), this reads
    // two lines and the test fails here; checked by hand, 2026-10-01.
    expect(refusedLines(plan)).toEqual([]);
    expect(plan.cells.some((c) => c.refused)).toBe(false);
    expect(plan.cells.map((c) => [c.label, c.slot, c.ground, c.refused])).toEqual([
      ["momwire:bspline, finite:13,0.005", "A", "1", null],
    ]);
    expect(skippedNote(plan)).toBe(
      "skipped: razor-2p, NEC-5, which no slot holds. Put one in a slot to include it.",
    );
  });

  it("an analysis whose every engine is unslotted draws every slot, with the note saying so", () => {
    const listed: ListedCross = { engines: ["momwire:razor-2p", "nec5"], grounds: null };
    const cross = preselect(listed, steve());
    expect(cross.slots).toEqual(["A", "B", "C"]);
    const plan = crossPlan(cross, listed, steve());
    expect(plan.cells.map((c) => [c.label, c.slot, c.refused])).toEqual([
      ["A: bspline d=2", "A", null],
      ["B: bspline d=1", "B", null],
      ["C: pynec", "C", null],
    ]);
    expect(skippedNote(plan)).toBe(
      "skipped: razor-2p, NEC-5, which no slot holds, so the chart draws your slots instead. Put one in a slot to include it.",
    );
    // The checkboxes still choose among the slots.
    const two = crossPlan({ slots: ["A", "C"], grounds: null }, listed, steve());
    expect(two.cells.map((c) => c.slot)).toEqual(["A", "C"]);
    expect(two.fallback).toBe(true);
  });

  it("E7 on Steve's slots: B-spline on both designs, razor-2p and NEC-2 skipped", () => {
    const listed: ListedCross = {
      engines: ["momwire:bspline", "momwire:razor-2p", "nec2"],
      grounds: null,
      axes: ["designs", "engines"],
      designs: [
        { name: "dipoles.invvee", refused: null, param: "n_per_wire", values: [5, 7] },
        { name: "dipoles.invvee_apex", refused: null, param: "n_per_wire", values: [5, 7] },
      ],
    };
    const plan = crossPlan(preselect(listed, steve()), listed, steve());
    expect(plan.cells.map((c) => [c.label, c.slot, c.refused])).toEqual([
      ["dipoles.invvee, momwire:bspline", "A", null],
      ["dipoles.invvee_apex, momwire:bspline", "A", null],
    ]);
    expect(skippedNote(plan)).toBe(
      "skipped: razor-2p, NEC-2, which no slot holds. Put one in a slot to include it.",
    );
  });

  it("a held engine's own refusal (a slot that cannot draw the design) stays a named refusal", () => {
    const e = steve();
    e.slots[2] = { ...e.slots[2], refusal: "a poor match for this design" };
    const listed: ListedCross = { engines: ["pynec", "nec5"], grounds: null };
    const plan = crossPlan(preselect(listed, e), listed, e);
    expect(refusedLines(plan)).toEqual(["pynec: a poor match for this design"]);
    expect(plan.skipped).toEqual(["nec5"]);
  });

  it("an analysis naming no engines skips nothing and has no note", () => {
    const plan = crossPlan(FOLLOW_ACTIVE, NOTHING_LISTED, steve());
    expect(plan.skipped).toEqual([]);
    expect(skippedNote(plan)).toBeNull();
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

// Unit 4b: the analysis's own crosses over planes, designs and a family,
// multiplied with the slots, in the CLI's order and labels
// (analysis_run.cells).
describe("planes, designs and families", () => {
  const E7: ListedCross = {
    engines: ["momwire:bspline", "momwire:razor-2p", "pynec"],
    grounds: null,
    axes: ["designs", "engines"],
    designs: [
      { name: "dipoles.invvee", refused: null, param: "n_per_wire", values: [8, 12] },
      { name: "dipoles.invvee_apex", refused: null, param: "n_per_wire", values: [8, 12] },
    ],
  };

  it("multiplies in the order the analysis writes its crosses, labelled as the CLI labels", () => {
    const plan = crossPlan(preselect(E7, env()), E7, env());
    expect(plan.capRefusal).toBeNull();
    expect(plan.cells.map((c) => [c.label, c.slot, c.design])).toEqual([
      ["dipoles.invvee, momwire:bspline", "A", "dipoles.invvee"],
      ["dipoles.invvee, momwire:razor-2p", "B", "dipoles.invvee"],
      ["dipoles.invvee, pynec", "C", "dipoles.invvee"],
      ["dipoles.invvee_apex, momwire:bspline", "A", "dipoles.invvee_apex"],
      ["dipoles.invvee_apex, momwire:razor-2p", "B", "dipoles.invvee_apex"],
      ["dipoles.invvee_apex, pynec", "C", "dipoles.invvee_apex"],
    ]);
    // Keys stay unique across the product, the slot|ground pair leading.
    expect(new Set(plan.cells.map((c) => c.key)).size).toBe(6);
    expect(plan.cells[3].key).toBe("A|X|d:dipoles.invvee_apex");
  });

  it("caps the whole product, naming every axis in the CLI's words", () => {
    const four = { ...E7, engines: [...(E7.engines ?? []), "nec5"] };
    const plan = crossPlan(preselect(four, env()), four, env());
    expect(plan.capRefusal).toBe("REFUSED: 2 designs x 4 engines = 8 curves, over the cap of 6");
    expect(plan.cells).toEqual([]);
    // A family times two ticked slots: the slots' axis joins the wording.
    const fam: ListedCross = {
      ...NOTHING_LISTED,
      axes: ["step"],
      step: { knob: "angle_deg", values: [0, 15, 30, 45], labels: [] },
    };
    expect(crossPlan({ slots: ["A", "B"], grounds: null }, fam, env()).capRefusal).toBe(
      "REFUSED: 4 values x 2 engines = 8 curves, over the cap of 6",
    );
    expect(crossPlan(FOLLOW_ACTIVE, fam, env()).capRefusal).toBeNull();
  });

  it("a family sets its knob per cell, labelled by the server, the ticked slots after it", () => {
    const fam: ListedCross = {
      ...NOTHING_LISTED,
      axes: ["step"],
      step: { knob: "angle_deg", values: [0, 30], labels: ["angle_deg = 0", "angle_deg = 30"] },
    };
    const one = crossPlan(FOLLOW_ACTIVE, fam, env());
    expect(one.cells.map((c) => [c.label, c.step])).toEqual([
      ["angle_deg = 0", { knob: "angle_deg", value: 0 }],
      ["angle_deg = 30", { knob: "angle_deg", value: 30 }],
    ]);
    const two = crossPlan({ slots: ["A", "C"], grounds: null }, fam, env());
    expect(two.cells.map((c) => c.label)).toEqual([
      "angle_deg = 0, A: momwire:bspline",
      "angle_deg = 0, C: pynec",
      "angle_deg = 30, A: momwire:bspline",
      "angle_deg = 30, C: pynec",
    ]);
  });

  it("a plane the design lacks is a refused cell in the server's words, and the rest draw", () => {
    const planes: ListedCross = {
      ...NOTHING_LISTED,
      axes: ["planes"],
      planes: [
        { name: "rig", refused: null },
        { name: "nowhere", refused: "no plane 'nowhere' on this design; it offers rig, T1" },
      ],
    };
    const plan = crossPlan(FOLLOW_ACTIVE, planes, env());
    expect(plan.cells.map((c) => [c.label, c.plane, c.refused])).toEqual([
      ["rig", "rig", null],
      ["nowhere", "nowhere", "no plane 'nowhere' on this design; it offers rig, T1"],
    ]);
    expect(refusedLines(plan)).toEqual([
      "nowhere: no plane 'nowhere' on this design; it offers rig, T1",
    ]);
  });

  it("a slot's refusal is about the session's design, so another design's cell is the server's", () => {
    const e = env({ design: "dipoles.invvee" });
    e.slots[2].refusal = "restricted on this design";
    const plan = crossPlan(preselect(E7, e), E7, e);
    expect(plan.cells.map((c) => c.refused)).toEqual([
      null,
      null,
      "restricted on this design",
      null,
      null,
      null,
    ]);
  });

  it("an engine declining the design is a refusal in its own words; anything else is not", () => {
    expect(engineRefusal("ValueError: this design uses PortAtVertex (...)")).toBe(
      "this design uses PortAtVertex (...)",
    );
    expect(engineRefusal("NotImplementedError: no")).toBe("no");
    expect(engineRefusal("RuntimeError: degenerate")).toBeNull();
    expect(engineRefusal("a poor match for this design")).toBeNull();
    expect(engineRefusal(null)).toBeNull();
  });
});

// AK#1757 step 7 unit 2: states, a cross over named knob settings. Each
// state is one cell labelled by its name (after its design when it names
// one), multiplied with the other axes under the cap, carrying its knobs.
describe("states", () => {
  const cell = { refused: null, param: "length_factor", values: [0.95, 1] };
  const HEIGHTS: ListedCross = {
    engines: null,
    grounds: ["finite:13,0.005"],
    axes: ["states"],
    states: [
      { ...cell, name: "as built", design: null, knobs: {}, label: "as built", on: null },
      { ...cell, name: "low mast", design: null, knobs: { base: 5 }, label: "low mast", on: null },
      { ...cell, name: "tall mast", design: null, knobs: { base: 12 }, label: "tall mast", on: null },
    ],
  };

  it("is one cell per state, labelled by its name, carrying its knobs", () => {
    const plan = crossPlan(preselect(HEIGHTS, env()), HEIGHTS, env());
    expect(plan.capRefusal).toBeNull();
    expect(plan.cells.map((c) => [c.label, c.slot, c.ground, c.design, c.state])).toEqual([
      ["as built, finite:13,0.005", "A", "X", undefined, { label: "as built", knobs: {} }],
      ["low mast, finite:13,0.005", "A", "X", undefined, { label: "low mast", knobs: { base: 5 } }],
      ["tall mast, finite:13,0.005", "A", "X", undefined, { label: "tall mast", knobs: { base: 12 } }],
    ]);
    expect(new Set(plan.cells.map((c) => c.key)).size).toBe(3);
    expect(plan.cells[1].key).toBe("A|X|st:low mast");
    expect(servedCell(plan.cells[2], HEIGHTS)?.values).toEqual([0.95, 1]);
  });

  it("multiplies with the ticked slots under the cap, in the CLI's words", () => {
    const two = crossPlan({ slots: ["A", "B"], grounds: null }, HEIGHTS, env());
    expect(two.cells.map((c) => c.label)).toEqual([
      "as built, A: momwire:bspline, finite:13,0.005",
      "as built, B: momwire:razor-2p, finite:13,0.005",
      "low mast, A: momwire:bspline, finite:13,0.005",
      "low mast, B: momwire:razor-2p, finite:13,0.005",
      "tall mast, A: momwire:bspline, finite:13,0.005",
      "tall mast, B: momwire:razor-2p, finite:13,0.005",
    ]);
    const three = crossPlan({ slots: ["A", "B", "C"], grounds: null }, HEIGHTS, env());
    expect(three.capRefusal).toBe("REFUSED: 3 states x 3 engines = 9 curves, over the cap of 6");
    expect(three.cells).toEqual([]);
  });

  it("a state naming its design is that design's cell, and a served refusal is the cell's", () => {
    const named: ListedCross = {
      ...NOTHING_LISTED,
      axes: ["states"],
      states: [
        { ...cell, name: "tall", design: null, knobs: { base: 12 }, label: "tall", on: null },
        {
          ...cell,
          refused: "state 'apex' sets hieght, and this design has no knob 'hieght'",
          name: "apex",
          design: "dipoles.invvee_apex",
          knobs: { hieght: 12 },
          label: "dipoles.invvee_apex, apex",
          on: null,
        },
      ],
    };
    const plan = crossPlan(FOLLOW_ACTIVE, named, env({ design: "dipoles.invvee" }));
    expect(plan.cells.map((c) => [c.label, c.design, c.refused])).toEqual([
      ["tall", undefined, null],
      [
        "dipoles.invvee_apex, apex",
        "dipoles.invvee_apex",
        "state 'apex' sets hieght, and this design has no knob 'hieght'",
      ],
    ]);
    expect(refusedLines(plan)).toEqual([
      "dipoles.invvee_apex, apex: state 'apex' sets hieght, and this design has no knob 'hieght'",
    ]);
  });

  it("an unnamed state beside a designs cross is set on each design, refused where served so", () => {
    const why = "state 'long line' sets line_len_m, and this design has no knob 'line_len_m'";
    const crossed: ListedCross = {
      ...NOTHING_LISTED,
      axes: ["designs", "states"],
      designs: [
        { name: "dipoles.invvee", refused: null, param: "length_factor", values: [0.9, 1] },
        { name: "wire.doublet_ladder_tuner", refused: null, param: "length_factor", values: [0.9, 1] },
      ],
      states: [
        {
          refused: null,
          param: null,
          values: null,
          name: "long line",
          design: null,
          knobs: { line_len_m: 20 },
          label: "long line",
          on: [
            { name: "dipoles.invvee", refused: why, param: null, values: null },
            { name: "wire.doublet_ladder_tuner", refused: null, param: "length_factor", values: [0.8, 1.2] },
          ],
        },
      ],
    };
    const plan = crossPlan(FOLLOW_ACTIVE, crossed, env());
    expect(plan.cells.map((c) => [c.label, c.design, c.state?.knobs, c.refused])).toEqual([
      ["dipoles.invvee, long line", "dipoles.invvee", { line_len_m: 20 }, why],
      ["wire.doublet_ladder_tuner, long line", "wire.doublet_ladder_tuner", { line_len_m: 20 }, null],
    ]);
    // The cell sweeps what was served for the state on that design.
    expect(servedCell(plan.cells[1], crossed)?.values).toEqual([0.8, 1.2]);
  });
});
