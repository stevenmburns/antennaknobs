// "Keep as study" and `cells=` in the page (AK#1757 step 7 unit 4),
// React-free: lib/keep.ts (what a keep sends, the endpoints' answers),
// lib/chartCells.ts's listed cells (a union, each on the slot that holds
// its engine) and lib/analyses.ts parsing a served `cells=` study.
import { afterEach, describe, expect, it, vi } from "vitest";
import { parseAnalyses } from "../lib/analyses";
import {
  type CrossEnv,
  crossPlan,
  FOLLOW_ACTIVE,
  type ListedCell,
  preselect,
  refusedLines,
  servedCell,
  skippedNote,
} from "../lib/chartCells";
import {
  fetchKeep,
  keepRequest,
  patternPinsKeep,
  saveStudy,
  StudyExistsError,
  suggestedPath,
  sweepPinsBlocked,
} from "../lib/keep";

const ENGINES: Record<string, string> = { A: "momwire:bspline", B: "momwire:razor-2p", C: "nec5" };
const GROUNDS: Record<string, string> = { "X": "finite-fast", "Y": "free" };
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
  design: "dipoles.invvee",
  ...over,
});

const cell = (over: Partial<ListedCell>): ListedCell => ({
  label: "",
  state: null,
  engine: null,
  ground: null,
  plane: null,
  refused: null,
  param: "length_factor",
  values: [0.95, 1],
  ...over,
});
const state = (name: string, over: Partial<NonNullable<ListedCell["state"]>> = {}) => ({
  name,
  design: "dipoles.invvee",
  variant: null,
  knobs: {},
  label: `dipoles.invvee, ${name}`,
  ...over,
});

describe("listed cells are a union", () => {
  it("draws one cell per listed cell, each on the slots holding its engine and ground", () => {
    const cells = [
      cell({ label: "low, nec5", state: state("low", { knobs: { base: 5 } }), engine: "nec5" }),
      cell({
        label: "tall, razor",
        state: state("tall", { variant: "dipole", knobs: { base: 12 } }),
        engine: "momwire:razor-2p",
        ground: "free",
        plane: "feed",
      }),
    ];
    const plan = crossPlan(FOLLOW_ACTIVE, { engines: null, grounds: null, axes: ["cells"], cells }, env());
    expect(plan.capRefusal).toBeNull();
    expect(plan.cells).toEqual([
      {
        key: "C|X|cell:0",
        label: "low, nec5",
        slot: "C",
        ground: "X",
        design: "dipoles.invvee",
        listed: 0,
        refused: null,
        state: { label: "dipoles.invvee, low", knobs: { base: 5 } },
      },
      {
        key: "B|Y|cell:1",
        label: "tall, razor",
        slot: "B",
        ground: "Y",
        plane: "feed",
        design: "dipoles.invvee",
        listed: 1,
        refused: null,
        state: { label: "dipoles.invvee, tall", knobs: { base: 12 }, variant: "dipole" },
      },
    ]);
    // Its sweep is the listed cell's own, as served.
    expect(servedCell(plan.cells[1], { engines: null, grounds: null, cells })).toBe(cells[1]);
  });

  it("a cell that names nothing follows the analysis's one engine, else the active slot", () => {
    const cells = [cell({ label: "a" })];
    const listed = { engines: ["nec5"], grounds: null, axes: ["cells" as const], cells };
    expect(crossPlan(FOLLOW_ACTIVE, listed, env()).cells[0].slot).toBe("C");
    expect(crossPlan(FOLLOW_ACTIVE, { ...listed, engines: null }, env()).cells[0].slot).toBe("A");
  });

  it("a cell whose engine no slot holds is skipped and noted; a ground no slot holds refuses its cell", () => {
    const cells = [cell({ label: "x", engine: "nec2" }), cell({ label: "y", ground: "pec" }), cell({ label: "z" })];
    const plan = crossPlan(FOLLOW_ACTIVE, { engines: null, grounds: null, cells }, env());
    expect(plan.cells.map((c) => [c.label, c.listed, c.refused])).toEqual([
      ["y", 1, "no ground slot holds pec"],
      ["z", 2, null],
    ]);
    expect(plan.skipped).toEqual(["nec2"]);
    expect(plan.fallback).toBe(false);
    expect(skippedNote(plan)).toBe("skipped: NEC-2, which no slot holds. Put it in a slot to include it.");
  });

  it("cells that are only an engine list, every one skipped, fall back to the slots", () => {
    // No state, one ground, one plane: nothing tells the cells apart but
    // the engine, so the slots stand in for them.
    const cells = [
      cell({ label: "two-pole", engine: "nec2", ground: "free" }),
      cell({ label: "pynec", engine: "pynec", ground: "free" }),
    ];
    const listed = { engines: null, grounds: null, axes: ["cells" as const], cells };
    const cross = preselect(listed, env());
    expect(cross.slots).toEqual(["A", "B", "C"]);
    const plan = crossPlan(cross, listed, env());
    expect(plan.cells.map((c) => [c.label, c.slot, c.ground, c.listed, c.refused])).toEqual([
      ["A: momwire:bspline", "A", "2", undefined, null],
      ["B: momwire:razor-2p", "B", "2", undefined, null],
      ["C: nec5", "C", "2", undefined, null],
    ]);
    expect(refusedLines(plan)).toEqual([]);
    expect(skippedNote(plan)).toBe(
      "skipped: NEC-2, PyNEC, which no slot holds, so the chart draws your slots instead. Put one in a slot to include it.",
    );
  });

  it("cells that say more than their engine, every one skipped, draw nothing but the note", () => {
    // Two states: no slot could stand in for either without dropping what
    // the cell says, so there is no fallback.
    const cells = [
      cell({ label: "low, nec2", state: state("low", { knobs: { base: 5 } }), engine: "nec2" }),
      cell({ label: "tall, nec2", state: state("tall", { knobs: { base: 12 } }), engine: "nec2" }),
    ];
    const listed = { engines: null, grounds: null, axes: ["cells" as const], cells };
    expect(preselect(listed, env()).slots).toBeNull();
    const plan = crossPlan(preselect(listed, env()), listed, env());
    expect(plan.cells).toEqual([]);
    expect(plan.fallback).toBe(false);
    expect(skippedNote(plan)).toBe("skipped: NEC-2, which no slot holds. Put it in a slot to include it.");
    // Different grounds tell them apart too.
    const grounds = [cell({ engine: "nec2", ground: "free" }), cell({ engine: "nec2", ground: "finite-fast" })];
    expect(crossPlan(FOLLOW_ACTIVE, { engines: null, grounds: null, cells: grounds }, env()).cells).toEqual([]);
  });

  it("the checkboxes multiply nothing, and over the cap the chart is refused whole", () => {
    const cells = [cell({ label: "a" }), cell({ label: "b", engine: "nec5" })];
    const ticked = crossPlan({ slots: ["A", "B"], grounds: ["X", "Y"] }, { engines: null, grounds: null, cells }, env());
    expect(ticked.cells.length).toBe(2);
    const seven = Array.from({ length: 7 }, (_, k) => cell({ label: `c${k}` }));
    const over = crossPlan(FOLLOW_ACTIVE, { engines: null, grounds: null, cells: seven }, env());
    expect(over.cells).toEqual([]);
    expect(over.capRefusal).toBe("REFUSED: 7 cells = 7 curves, over the cap of 6");
  });
});

describe("a served cells study parses", () => {
  it("keeps its cells, a state's variant and a group knob's entries, and the spec as data", () => {
    const bands = [{ freq: 14.3, length_factor: 0.49 }];
    const [e] = parseAnalyses({
      analyses: [
        {
          name: "fan/bands:bands",
          summary: "",
          code: "",
          spec: { an: "Analysis", name: "bands" },
          problems: [],
          study: { source: "fan/bands", name: "bands" },
          workbench: {
            runs: true,
            kind: "knob",
            param: "base",
            values: [5, 7],
            log: false,
            note: null,
            axes: ["cells", "junk"],
            cells: [
              {
                label: "fan, bands set",
                state: { name: "bands set", design: "fan", variant: "five_band", knobs: { bands }, label: "fan:five_band, bands set" },
                engine: "nec5",
                ground: null,
                plane: null,
                refused: null,
                param: "base",
                values: [5, 7],
                range: null,
                freqs: null,
              },
            ],
            states: [
              { name: "s", label: "s", design: null, variant: "v", knobs: { bands }, refused: null, param: "base", values: [5], on: null },
            ],
          },
        },
      ],
    }); // prettier-ignore
    expect(e.spec).toEqual({ an: "Analysis", name: "bands" });
    const w = e.workbench;
    if (!w.runs || w.kind !== "knob") throw new Error("not a knob analysis");
    expect(w.axes).toEqual(["cells"]);
    expect(w.cells?.[0]).toMatchObject({
      label: "fan, bands set",
      engine: "nec5",
      ground: null,
      state: { variant: "five_band", knobs: { bands } },
      values: [5, 7],
    });
    expect(w.states?.[0]).toMatchObject({ variant: "v", knobs: { bands } });
  });

  it("drops a malformed cell list rather than guessing", () => {
    const [e] = parseAnalyses({
      analyses: [
        {
          name: "x",
          workbench: {
            runs: true, kind: "knob", param: "base", values: [1], log: false,
            cells: [{ label: "bad", engine: 3, state: null }],
          },
        },
      ],
    }); // prettier-ignore
    if (!e.workbench.runs || e.workbench.kind !== "knob") throw new Error("not a knob analysis");
    expect(e.workbench.cells).toBeNull();
  });
});

describe("what a keep sends", () => {
  it("a request without the session's plumbing, the cut dials kept", () => {
    const req = {
      geometry: "g",
      solver: "momwire",
      _session: "s",
      _stream: "c0r1",
      _gen: 3,
      _approved: true,
      _track: {},
      z0_ohms: 75,
      az_elev_deg: 12,
      gap: 0.3,
    };
    expect(keepRequest(req)).toEqual({ geometry: "g", solver: "momwire", az_elev_deg: 12, gap: 0.3 });
  });

  it("sweep pins keep as one study only when they sweep one thing, under the cap", () => {
    const f = { x: { kind: "frequency" as const, name: "frequency" } };
    const k = { x: { kind: "knob" as const, name: "base" } };
    expect(sweepPinsBlocked([f, f], 6)).toBeNull();
    expect(sweepPinsBlocked([], 6)).toMatch(/No pins/);
    expect(sweepPinsBlocked([f, k], 6)).toMatch(/sweep different things/);
    expect(sweepPinsBlocked(Array(7).fill(f), 6)).toMatch(/7 pins is over the cap of 6/);
  });

  it("pattern pins keep the shown ones' own requests, refused by name otherwise", () => {
    const p = (label: string, enabled = true, req: Record<string, unknown> | null = { geometry: label }) => ({
      label,
      enabled,
      ...(req ? { req } : {}),
    });
    expect(patternPinsKeep([p("a"), p("hidden", false), p("b")], 6)).toEqual({
      pins: [
        { req: { geometry: "a" }, label: "a" },
        { req: { geometry: "b" }, label: "b" },
      ],
      blocked: null,
    });
    expect(patternPinsKeep([p("h", false)], 6).blocked).toMatch(/No shown pin/);
    expect(patternPinsKeep([p("old", true, null)], 6).blocked).toMatch(/pin it again/);
    expect(patternPinsKeep(Array.from({ length: 7 }, (_, k) => p(`p${k}`)), 6).blocked).toMatch(/over the cap of 6/);
  });

  it("a suggested path is one plain name part", () => {
    expect(suggestedPath("Pinned sweeps (E7)")).toBe("pinned-sweeps-e7");
    expect(suggestedPath("  ../..  ")).toBe("study");
  });
});

describe("the endpoints' answers", () => {
  afterEach(() => vi.unstubAllGlobals());
  const answer = (status: number, body: unknown) =>
    vi.fn(async () => ({ ok: status < 400, status, json: async () => body }) as unknown as Response);

  it("keep: the text, its name, problems and the study refusal; a refusal in the server's words", async () => {
    vi.stubGlobal("fetch", answer(200, { code: "c", name: "n", problems: ["p"], study_refusal: "r" }));
    const body = { origin: "chart" as const, form: "study" as const, spec: {}, tab: {} };
    expect(await fetchKeep(body)).toEqual({ code: "c", name: "n", problems: ["p"], studyRefusal: "r" });
    vi.stubGlobal("fetch", answer(422, { detail: "give the pins to keep" }));
    await expect(fetchKeep(body)).rejects.toThrow("give the pins to keep");
  });

  it("save: 409 is its own error (the dialog offers to replace), 403 names the hosted refusal", async () => {
    const body = { origin: "chart" as const, form: "study" as const, spec: {}, tab: {} };
    const fetch = answer(409, { detail: "x.py is there already" });
    vi.stubGlobal("fetch", fetch);
    await expect(saveStudy(body, "x", false)).rejects.toBeInstanceOf(StudyExistsError);
    const init = (fetch.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(String(init.body))).toMatchObject({ path: "x", overwrite: false, form: "study" });
    vi.stubGlobal("fetch", answer(403, { detail: "saving a study is disabled on the hosted instance; copy it instead" }));
    await expect(saveStudy(body, "x", false)).rejects.toThrow(/hosted instance/);
  });
});
