// Does picking an analysis start it (AC6LA, QRZ 1003328 #179)? The kind a
// pick is (lib/analysisChart.ts runOnPickKind), read off /analyses' served
// entries the way the session reads them (parseAnalyses), and the served
// [workbench.run_on_pick] table (lib/settings.ts parseUiDefaults).
import { describe, it, expect } from "vitest";
import { parseAnalyses, type AnalysisEntry } from "../lib/analyses";
import { pickRuns, runOnPickKind } from "../lib/analysisChart";
import { BUILTIN_RUN_ON_PICK, parseUiDefaults } from "../lib/settings";

const knob = (param: string, hold = false) => ({
  runs: true,
  kind: "knob",
  param,
  values: [2, 5, 8],
  log: false,
  views: hold ? ["Rx", "Knobs"] : ["Rx"],
  ...(hold
    ? {
        hold: {
          objective: "resonance",
          knobs: ["gap"],
          bounds: { gap: [0, 1] },
          z0: null,
          warm_start: true,
          spec: { an: "Hold" },
        },
      }
    : {}),
  note: null,
});
const FREQUENCY = {
  runs: true,
  kind: "frequency",
  range: null,
  level: "band",
  points: null,
  views: ["Swr"],
  swr: { scale: null, threshold: null },
  note: null,
};
const PATTERN = { runs: true, kind: "pattern", views: [{ view: "Elevation", az: 0 }], freq: 14.1, note: null };
const MAP = { runs: false, why: "a two-sweep map: not in the workbench yet (sweep-framework step 5)" };
const study = (name: string) => ({ source: "dipoles.apex_feed_on_deck", name });

const served = (entries: { name: string; workbench: unknown; study?: unknown }[]) =>
  parseAnalyses({
    analyses: entries.map((e) => ({ summary: "", code: "", problems: [], ...e })),
  });

const byName = (list: AnalysisEntry[], name: string) => list.find((a) => a.name === name)!;

describe("runOnPickKind: the kind of analysis a pick is", () => {
  const list = served([
    { name: "band SWR", workbench: FREQUENCY },
    { name: "pattern", workbench: PATTERN },
    { name: "height", workbench: knob("base") },
    { name: "match vs height", workbench: knob("base", true) },
    { name: "convergence", workbench: knob("n_per_wire") },
    { name: "map", workbench: MAP },
    { name: "s:held study", workbench: knob("base", true), study: study("held study") },
    { name: "s:convergence study", workbench: knob("n_per_wire"), study: study("convergence study") },
    { name: "s:frequency study", workbench: FREQUENCY, study: study("frequency study") },
  ]);
  it.each([
    ["band SWR", "frequency"],
    ["pattern", "pattern"],
    ["height", "knob"],
    ["match vs height", "held"],
    ["convergence", "convergence"],
    // A study is the kind of analysis it is: no `study` kind.
    ["s:held study", "held"],
    ["s:convergence study", "convergence"],
    ["s:frequency study", "frequency"],
  ])("%s is %s", (name, kind) => {
    const e = byName(list, name);
    expect(runOnPickKind(e.workbench)).toBe(kind);
  });

  it("an analysis the workbench cannot run (a map today) has no kind, and never runs", () => {
    const e = byName(list, "map");
    expect(runOnPickKind(e.workbench)).toBeNull();
    expect(pickRuns(e.workbench, { ...BUILTIN_RUN_ON_PICK, map: true })).toBe(false);
  });

  it("the built-in table: frequency sweeps and patterns run, the rest wait for Run", () => {
    const runs = Object.fromEntries(list.map((e) => [e.name, pickRuns(e.workbench, BUILTIN_RUN_ON_PICK)]));
    expect(runs).toEqual({
      "band SWR": true,
      pattern: true,
      height: false,
      "match vs height": false,
      convergence: false,
      map: false,
      "s:held study": false,
      "s:convergence study": false,
      "s:frequency study": true,
    });
  });

  it("a kind set true runs, and only that kind", () => {
    const table = { ...BUILTIN_RUN_ON_PICK, knob: true };
    expect(pickRuns(byName(list, "height").workbench, table)).toBe(true);
    expect(pickRuns(byName(list, "match vs height").workbench, table)).toBe(false);
    expect(pickRuns(byName(list, "convergence").workbench, table)).toBe(false);
  });
});

describe("parseUiDefaults: [workbench.run_on_pick]", () => {
  it("a server without it serves the built-in table", () => {
    expect(parseUiDefaults({}).runOnPick).toEqual(BUILTIN_RUN_ON_PICK);
    expect(parseUiDefaults(undefined).runOnPick).toEqual(BUILTIN_RUN_ON_PICK);
  });

  it("takes each served boolean, and the built-in for anything else", () => {
    const ui = parseUiDefaults({
      workbench: { run_on_pick: { knob: true, frequency: false, held: "yes", study: true } },
    });
    expect(ui.runOnPick).toEqual({ ...BUILTIN_RUN_ON_PICK, knob: true, frequency: false });
  });
});
