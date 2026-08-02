// Pins the pure param-schema logic in src/lib/params.ts (issue #642 Phase 3
// seam 2): the SchemaItem/group discrimination, visibility predicate, value-
// bag seeding, the design-switch band snap, the design-freq link lookup, the
// antenna search predicate, and family ordering. All pure functions with no
// DOM/React dependency.
import { describe, it, expect } from "vitest";
import {
  applyVisibility,
  familyOf,
  familyRank,
  FAMILY_ORDER,
  findLinkedDesignFreq,
  isGroup,
  matchesQuery,
  seedDefaults,
  snapForExample,
  type BandSpec,
  type ExampleDescriptor,
  type ParamValueBag,
  type SchemaItem,
  type SchemaParamGroupSpec,
  type SchemaParamSpec,
} from "../lib/params";

// --- fixture factories -----------------------------------------------------
// Real (fully-typed) minimal objects rather than `as` casts, so every field
// the functions might read is present and type-checked; only the fields a
// given test cares about are overridden.

function makeParam(overrides: Partial<SchemaParamSpec> = {}): SchemaParamSpec {
  return {
    name: "p",
    label: "P",
    default: 0,
    kind: "float",
    min: 0,
    max: 10,
    step: 1,
    precision: 2,
    unit: null,
    visible_when: null,
    ...overrides,
  };
}

function makeGroup(overrides: Partial<SchemaParamGroupSpec> = {}): SchemaParamGroupSpec {
  return {
    kind: "group",
    name: "g",
    label_template: "G {i}",
    repeat_count: "n_g",
    max_repeats: 2,
    params: [],
    default_overrides: [{}, {}],
    ...overrides,
  };
}

function makeExample(overrides: Partial<ExampleDescriptor> = {}): ExampleDescriptor {
  return {
    name: "dipoles.test",
    label: "Test Dipole",
    multi_feed: false,
    param_schema: [],
    result_schema: [],
    bands: [],
    meas_freq_range_mhz: null,
    default_view: null,
    default_freq: null,
    default_design_freq: null,
    default_backend: null,
    requires_backends: null,
    has_design_freq: true,
    variants: ["default"],
    variant_values: {},
    sweep_policy: { anchor: "design_freq", lo_factor: 0.5, hi_factor: 2 },
    ...overrides,
  };
}

const BAND_10M: BandSpec = { key: "10m", label: "10 m", freq_mhz: 28.5, min_mhz: 28.0, max_mhz: 29.7 };
const BAND_12M: BandSpec = { key: "12m", label: "12 m", freq_mhz: 24.94, min_mhz: 24.89, max_mhz: 24.99 };

// --- isGroup -----------------------------------------------------------

describe("isGroup", () => {
  it("discriminates a group spec by kind === 'group'", () => {
    expect(isGroup(makeGroup())).toBe(true);
  });

  it("discriminates a scalar spec (no kind: 'group')", () => {
    expect(isGroup(makeParam())).toBe(false);
  });
});

// --- applyVisibility -----------------------------------------------------

describe("applyVisibility", () => {
  it("is always visible when visible_when is null", () => {
    const spec = makeParam({ visible_when: null });
    expect(applyVisibility(spec, {})).toBe(true);
  });

  it("is visible when the referenced param is missing from the value bag", () => {
    const spec = makeParam({ visible_when: { name: "n_directors", op: "gt", value: 0 } });
    // `values` has no `n_directors` key at all.
    expect(applyVisibility(spec, { other: 1 })).toBe(true);
  });

  it("is visible when the referenced value is non-numeric (e.g. an enum)", () => {
    const spec = makeParam({ visible_when: { name: "mode", op: "eq", value: 1 } });
    expect(applyVisibility(spec, { mode: "fan" })).toBe(true);
  });

  const cases: { op: string; hideAt: number; showAt: number; threshold: number }[] = [
    { op: "eq", hideAt: 1, showAt: 0, threshold: 0 },
    { op: "ne", hideAt: 0, showAt: 1, threshold: 0 },
    { op: "gt", hideAt: 0, showAt: 1, threshold: 0 },
    { op: "ge", hideAt: -1, showAt: 0, threshold: 0 },
    { op: "lt", hideAt: 0, showAt: -1, threshold: 0 },
    { op: "le", hideAt: 1, showAt: 0, threshold: 0 },
  ];
  for (const { op, hideAt, showAt, threshold } of cases) {
    it(`supports op "${op}"`, () => {
      const spec = makeParam({ visible_when: { name: "n", op, value: threshold } });
      expect(applyVisibility(spec, { n: showAt })).toBe(true);
      expect(applyVisibility(spec, { n: hideAt })).toBe(false);
    });
  }

  it("defaults to visible for an unrecognized op", () => {
    const spec = makeParam({ visible_when: { name: "n", op: "weird", value: 0 } });
    expect(applyVisibility(spec, { n: 0 })).toBe(true);
  });
});

// --- seedDefaults -----------------------------------------------------

describe("seedDefaults", () => {
  it("seeds a float/int scalar from `default` via Number()", () => {
    const schema: SchemaItem[] = [makeParam({ name: "len", kind: "float", default: 12.5 })];
    expect(seedDefaults(schema)).toEqual({ len: 12.5 });
  });

  it("seeds an enum scalar from `default` via String()", () => {
    const schema: SchemaItem[] = [makeParam({ name: "mode", kind: "enum", default: "fan" })];
    expect(seedDefaults(schema)).toEqual({ mode: "fan" });
  });

  it("seeds a bool scalar from `default` via Boolean()", () => {
    const schema: SchemaItem[] = [makeParam({ name: "linkMeas", kind: "bool", default: true })];
    expect(seedDefaults(schema)).toEqual({ linkMeas: true });
  });

  it("pre-allocates a group to max_repeats child bags regardless of repeat_count", () => {
    const group = makeGroup({
      name: "bands",
      max_repeats: 3,
      params: [makeParam({ name: "freq", kind: "float", default: 14.1 })],
      default_overrides: [{}, {}, {}],
    });
    const out = seedDefaults([group]);
    expect(Array.isArray(out.bands)).toBe(true);
    expect((out.bands as ParamValueBag[]).length).toBe(3);
    for (const inst of out.bands as ParamValueBag[]) {
      expect(inst).toEqual({ freq: 14.1 });
    }
  });

  it("applies default_overrides per group instance, bypassing kind coercion", () => {
    const group = makeGroup({
      name: "bands",
      max_repeats: 2,
      params: [makeParam({ name: "freq", kind: "float", default: 14.1 })],
      // Instance 0 overridden to a *string* — seedDefaults passes an
      // override through untouched (no Number()/String()/Boolean() applied),
      // unlike the plain-default path. Instance 1 has no override.
      default_overrides: [{ freq: "14.200" }, {}],
    });
    const out = seedDefaults([group]);
    const instances = out.bands as ParamValueBag[];
    expect(instances[0]).toEqual({ freq: "14.200" });
    expect(instances[1]).toEqual({ freq: 14.1 });
  });

  it("seeds nested groups (a group whose params contain another group)", () => {
    const inner = makeGroup({
      name: "inner",
      max_repeats: 1,
      params: [makeParam({ name: "x", kind: "float", default: 1 })],
      default_overrides: [{}],
    });
    const outer = makeGroup({
      name: "outer",
      max_repeats: 2,
      params: [inner],
      // The outer group's default_overrides is keyed by the outer's own
      // param names (here just "inner", the nested group) — but overrides
      // only apply to scalar leaves, never to a nested group, which always
      // self-seeds from its own default_overrides regardless.
      default_overrides: [{}, {}],
    });
    const out = seedDefaults([outer]);
    const outerInstances = out.outer as ParamValueBag[];
    expect(outerInstances).toHaveLength(2);
    for (const oi of outerInstances) {
      const innerInstances = oi.inner as ParamValueBag[];
      expect(innerInstances).toHaveLength(1);
      expect(innerInstances[0]).toEqual({ x: 1 });
    }
  });
});

// --- snapForExample -----------------------------------------------------

describe("snapForExample", () => {
  it("returns null when the example is undefined", () => {
    expect(snapForExample(undefined)).toBeNull();
  });

  it("returns null when the example has no bands", () => {
    const ex = makeExample({ bands: [], default_freq: 14.1, default_design_freq: 14.1 });
    expect(snapForExample(ex)).toBeNull();
  });

  it("snaps design freq and meas freq to the same in-band value for an on-band design", () => {
    const ex = makeExample({
      bands: [BAND_10M, BAND_12M],
      default_design_freq: 28.5,
      default_freq: 28.5,
    });
    expect(snapForExample(ex)).toEqual({
      bandKey: "10m",
      freq: 28.5,
      measBandKey: "10m",
      measFreq: 28.5,
      offBand: false,
    });
  });

  it("keeps design freq and meas freq in different bands for an off-band design", () => {
    // e.g. inverted_l_tmatch: native design is 10 m, worked on 12 m via tuner.
    const ex = makeExample({
      bands: [BAND_10M, BAND_12M],
      default_design_freq: 28.5,
      default_freq: 24.94,
    });
    expect(snapForExample(ex)).toEqual({
      bandKey: "10m",
      freq: 28.5,
      measBandKey: "12m",
      measFreq: 24.94,
      offBand: true,
    });
  });

  it("falls back to bands[0]'s own freq_mhz when the native freq matches no band", () => {
    const ex = makeExample({
      bands: [BAND_10M, BAND_12M],
      default_design_freq: 1.9, // 160 m — outside both listed bands
      default_freq: null,
    });
    expect(snapForExample(ex)).toEqual({
      bandKey: "10m",
      freq: 28.5, // dTarget.freq_mhz, NOT the raw 1.9
      measBandKey: "10m",
      measFreq: 28.5,
      offBand: false,
    });
  });
});

// --- findLinkedDesignFreq -----------------------------------------------------

describe("findLinkedDesignFreq", () => {
  it("returns null when no leaf is linked_to_design_freq", () => {
    const schema: SchemaItem[] = [makeParam({ name: "len", linked_to_design_freq: false })];
    expect(findLinkedDesignFreq(schema, { len: 10 })).toBeNull();
  });

  it("returns the value of a flat linked leaf", () => {
    const schema: SchemaItem[] = [
      makeParam({ name: "len", linked_to_design_freq: false }),
      makeParam({ name: "freq", linked_to_design_freq: true }),
    ];
    expect(findLinkedDesignFreq(schema, { len: 10, freq: 14.1 })).toBe(14.1);
  });

  it("finds a linked leaf inside the first instance of a group", () => {
    const inner = makeParam({ name: "freq", linked_to_design_freq: true });
    const group = makeGroup({ name: "bands", params: [inner] });
    const values: ParamValueBag = {
      bands: [{ freq: 7.1 }, { freq: 14.1 }],
    };
    expect(findLinkedDesignFreq([group], values)).toBe(7.1);
  });

  it("does not fall through to a later group instance when the first has no value", () => {
    // Only the first instance is ever consulted (documented limitation) —
    // even though the second instance's `freq` would resolve if reached.
    const inner = makeParam({ name: "freq", linked_to_design_freq: true });
    const group = makeGroup({ name: "bands", params: [inner] });
    const values: ParamValueBag = {
      // First instance's "freq" is a string (unlinked type), second is a
      // proper number — findLinkedDesignFreq must still miss.
      bands: [{ freq: "n/a" }, { freq: 14.1 }],
    };
    expect(findLinkedDesignFreq([group], values)).toBeNull();
  });

  it("skips a group with no instances", () => {
    const inner = makeParam({ name: "freq", linked_to_design_freq: true });
    const group = makeGroup({ name: "bands", params: [inner] });
    const values: ParamValueBag = { bands: [] };
    expect(findLinkedDesignFreq([group], values)).toBeNull();
  });
});

// --- matchesQuery -----------------------------------------------------

describe("matchesQuery", () => {
  it("matches everything for an empty query", () => {
    expect(matchesQuery(makeExample({ name: "beams.yagi", label: "Yagi" }), "")).toBe(true);
  });

  it("matches by (lowercased) name substring", () => {
    const ex = makeExample({ name: "beams.yagi", label: "Yagi-Uda Beam" });
    expect(matchesQuery(ex, "yagi")).toBe(true);
  });

  it("matches by (lowercased) label substring", () => {
    const ex = makeExample({ name: "beams.yagi", label: "Yagi-Uda Beam" });
    expect(matchesQuery(ex, "uda")).toBe(true);
  });

  it("matches by the family prefix (familyOf) even when absent from the label", () => {
    const ex = makeExample({ name: "loops.quad", label: "Cubical Quad" });
    expect(matchesQuery(ex, "loops")).toBe(true);
  });

  it("matches via SEARCH_KEYWORDS even when absent from name/label", () => {
    // wire.zepp's SEARCH_KEYWORDS entry is "end fed zeppelin".
    const ex = makeExample({ name: "wire.zepp", label: "Zepp" });
    expect(matchesQuery(ex, "zeppelin")).toBe(true);
  });

  it("does not match an unrelated query", () => {
    const ex = makeExample({ name: "beams.yagi", label: "Yagi-Uda Beam" });
    expect(matchesQuery(ex, "helix")).toBe(false);
  });

  it("lowercases the haystack but NOT the query — an uppercase query misses (caller must lowercase first)", () => {
    const ex = makeExample({ name: "beams.yagi", label: "Yagi-Uda Beam" });
    // Surprising: matchesQuery does `hay.toLowerCase().includes(q)`, so a
    // query that isn't already lowercase will not match even an
    // otherwise-identical substring.
    expect(matchesQuery(ex, "YAGI")).toBe(false);
    expect(matchesQuery(ex, "yagi")).toBe(true);
  });
});

// --- familyRank / familyOf -----------------------------------------------------

describe("familyOf", () => {
  it("takes the dot-prefix of a design name", () => {
    expect(familyOf("dipoles.invvee")).toBe("dipoles");
  });

  it("returns the whole name unchanged when there's no dot", () => {
    expect(familyOf("standalone")).toBe("standalone");
  });
});

describe("familyRank", () => {
  it("ranks known families in FAMILY_ORDER's declared order", () => {
    const ranks = FAMILY_ORDER.map((f) => familyRank(f));
    expect(ranks).toEqual(FAMILY_ORDER.map((_, i) => i));
    // Strictly increasing, i.e. matches declared order exactly.
    for (let i = 1; i < ranks.length; i++) {
      expect(ranks[i]).toBeGreaterThan(ranks[i - 1]);
    }
  });

  it("sorts an unknown family after every known one", () => {
    expect(familyRank("mystery")).toBe(FAMILY_ORDER.length);
    expect(familyRank("mystery")).toBeGreaterThan(familyRank(FAMILY_ORDER[FAMILY_ORDER.length - 1]));
  });
});
