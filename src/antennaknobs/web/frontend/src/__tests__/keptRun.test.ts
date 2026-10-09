// A kept band run (AK#1906, lib/keptRun.ts): what /analyses serves for an
// an.Optimize study, and what a jump to it sets.
import { describe, expect, it } from "vitest";
import {
  formFor,
  keptAsResult,
  keptForm,
  keptMarks,
  keptValues,
  parseKept,
  type KeptRun,
} from "../lib/keptRun";
import { optimizeSpec } from "../components/session/useOptimizer";
import { KEPT_NOT_A_CHART, parseAnalyses } from "../lib/analyses";
import type { SchemaItem, SchemaParamSpec } from "../lib/params";

// As `analyses_offer._optimize_run` serves it.
const SERVED = {
  runs: true,
  kind: "optimize",
  state: { s: 0.2, bands: [{ freq: 26.6, length: 5.4 }, { freq: 29.3, length: 5.0 }] },
  free: [
    { name: "bands.0.length", min: 5.2, max: 5.8 },
    { name: "base", min: 6, max: 8 },
  ],
  bands: [
    { freq: 26.6, objective: "swr", feed: 0, z0: null },
    { freq: 29.3, objective: "swr", feed: 0, z0: null },
  ],
  mode: "minimax",
  mean_weight: 0.3,
  z0: 50,
  result: {
    knobs: { "bands.0.length": 5.55, base: 7.25 },
    bands: [
      { freq: 26.6, swr_before: 2.5, swr_after: 1.2 },
      { freq: 29.3, swr_before: null, swr_after: 1.4 },
    ],
  },
  note: null,
};

const knob = (name: string, over: Partial<SchemaParamSpec> = {}): SchemaParamSpec => ({
  name,
  label: name,
  default: 1,
  kind: "float",
  min: 0,
  max: 10,
  step: 0.1,
  precision: 2,
  unit: null,
  visible_when: null,
  ...over,
});

describe("parseKept", () => {
  it("reads the served run", () => {
    const k = parseKept(SERVED) as KeptRun;
    expect(k.free.map((f) => f.name)).toEqual(["bands.0.length", "base"]);
    expect(k.bands.map((b) => b.freq)).toEqual([26.6, 29.3]);
    expect(k.meanWeight).toBe(0.3);
    expect(k.result?.knobs).toEqual({ "bands.0.length": 5.55, base: 7.25 });
    expect(k.result?.bands[1]).toEqual({ freq: 29.3, swrBefore: null, swrAfter: 1.4 });
  });

  it("is null for anything else", () => {
    expect(parseKept({ runs: true, kind: "knob", param: "x", values: [1] })).toBeNull();
    expect(parseKept({ runs: false, why: "no" })).toBeNull();
    expect(parseKept({ ...SERVED, free: [] })).toBeNull();
  });

  it("an analyses entry holds it, its chart workbench inert", () => {
    const [e] = parseAnalyses({
      analyses: [{ name: "fan:kept", workbench: SERVED, study: { source: "fan", name: "kept" } }],
    });
    expect(e.kept?.free).toHaveLength(2);
    expect(e.workbench).toEqual({ runs: false, why: KEPT_NOT_A_CHART });
  });
});

describe("a jump", () => {
  const k = parseKept(SERVED) as KeptRun;
  const defaults = { s: 0.1, base: 7, bands: [{ freq: 26.6, length: 5.3 }, { freq: 29.3, length: 5.1 }] };

  it("sets the start over the defaults, then the stored answer", () => {
    const start = keptValues(defaults, k, "start");
    expect(start).toEqual({ ...SERVED.state, base: 7 });
    const at = keptValues(defaults, k, "result");
    expect(at.base).toBe(7.25);
    expect(at.s).toBe(0.2);
    expect(at.bands).toEqual([{ freq: 26.6, length: 5.55 }, { freq: 29.3, length: 5.0 }]);
    // The defaults are not touched.
    expect(defaults.bands[0].length).toBe(5.3);
  });

  it("marks exactly the run's knobs over its ranges", () => {
    const schema: SchemaItem[] = [knob("base"), knob("s")];
    const marks = keptMarks(k, schema);
    expect(Object.keys(marks)).toEqual(["bands.0.length", "base"]);
    expect(marks.base).toMatchObject({ vary: true, optMin: 6, optMax: 8, dispMin: 0, dispMax: 10 });
  });

  it("draws its stored table as a band result", () => {
    const r = keptAsResult(k)!;
    expect(r.objective).toBe("bands");
    expect(r.bands_after?.map((b) => b.swr)).toEqual([1.2, 1.4]);
    expect(r.worst_swr_after).toBe(1.4);
    // A band the engine read nothing at leaves the worst unknown.
    expect(r.worst_swr_before).toBeNull();
  });

  it("is run again in its own form, every band's Z0 spelled out (#1921)", () => {
    const root: KeptRun = {
      ...k,
      mode: "root",
      bands: [
        { freq: 26.6, objective: "resonance", feed: 1, z0: null },
        { freq: 29.3, objective: "match_z0", feed: 0, z0: 75 },
      ],
    };
    const form = keptForm(root);
    expect(form).toEqual({
      mode: "root",
      bands: [
        { freq: 26.6, objective: "resonance", feed: 1, z0: 50 },
        { freq: 29.3, objective: "match_z0", feed: 0, z0: 75 },
      ],
    });
    const free = [{ name: "base", min: 6, max: 8 }];
    const spec = optimizeSpec(free, {
      objective: "swr",
      seed: false,
      bands: [26.6, 29.3],
      meanWeight: 0.3,
      form: formFor(form, [26.6, 29.3]),
    });
    expect(spec).toEqual({ free, bands: form.bands, mode: "root", mean_weight: 0.3 });
  });

  it("drops the kept form once the band list is edited", () => {
    const form = keptForm(k);
    expect(formFor(form, [26.6, 29.3])).toBe(form);
    expect(formFor(form, [26.6, 29.4])).toBeNull();
    expect(formFor(form, [29.3, 26.6])).toBeNull();
    expect(formFor(form, [26.6])).toBeNull();
    expect(formFor(form, null)).toBeNull();
    // No form: the plain SWR minimax, as before.
    expect(
      optimizeSpec([], { objective: "swr", seed: false, bands: [26.6], meanWeight: 0.5, form: null }),
    ).toEqual({ free: [], bands: [{ freq: 26.6, objective: "swr" }], mode: "minimax", mean_weight: 0.5 });
  });
});
