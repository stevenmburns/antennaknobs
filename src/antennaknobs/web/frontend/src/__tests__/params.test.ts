// Pins the pure param-schema logic in src/lib/params.ts (issue #642 Phase 3
// seam 2): the SchemaItem/group discrimination, visibility predicate, value-
// bag seeding, the design-switch band snap, the design-freq link lookup, the
// antenna search predicate, and family ordering. All pure functions with no
// DOM/React dependency.
import { describe, it, expect } from "vitest";
import {
  applyVisibility,
  defaultKnobOpt,
  familyOf,
  familyRank,
  FAMILY_LABELS,
  FAMILY_ORDER,
  findLinkedDesignFreq,
  groupExamplesForPicker,
  isGroup,
  linkedMeasFreqFor,
  matchesQuery,
  overlaySchemaForVariant,
  seedDefaults,
  setValueAtPath,
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

// --- setValueAtPath -----------------------------------------------------
// Issue #642 PR 5b-1: extracted verbatim from DesignSession's setParamAtPath
// local `setIn` closure.

describe("setValueAtPath", () => {
  it("sets a top-level scalar path immutably", () => {
    const node = { a: 1, b: 2 };
    const out = setValueAtPath(node, ["a"], 5) as Record<string, unknown>;
    expect(out).toEqual({ a: 5, b: 2 });
    expect(node).toEqual({ a: 1, b: 2 }); // original untouched
    expect(out).not.toBe(node);
  });

  it("returns `value` directly for an empty path", () => {
    expect(setValueAtPath({ a: 1 }, [], 42)).toBe(42);
  });

  it("sets a nested group-array leaf (['bands', 2, 'freq']) immutably at every level", () => {
    const inst0 = { freq: 1 };
    const inst1 = { freq: 2 };
    const inst2 = { freq: 3 };
    const node = { bands: [inst0, inst1, inst2] };
    const out = setValueAtPath(node, ["bands", 2, "freq"], 99) as {
      bands: { freq: number }[];
    };
    expect(out.bands[2]).toEqual({ freq: 99 });
    // Untouched sibling instances keep their original object identity —
    // only the path actually walked gets cloned.
    expect(out.bands[0]).toBe(inst0);
    expect(out.bands[1]).toBe(inst1);
    // Original tree is fully unmutated at every level (array + object).
    expect(node.bands[2]).toEqual({ freq: 3 });
    expect(node.bands).not.toBe(out.bands);
    expect(node).not.toBe(out);
  });

  it("clones the array via slice when indexing into it (no in-place mutation)", () => {
    const arr = [1, 2, 3];
    const node = { xs: arr };
    const out = setValueAtPath(node, ["xs", 1], 20) as { xs: number[] };
    expect(out.xs).toEqual([1, 20, 3]);
    expect(arr).toEqual([1, 2, 3]); // original array untouched
    expect(out.xs).not.toBe(arr);
  });

  it("builds a fresh array from an undefined node when the path starts with a numeric index", () => {
    const out = setValueAtPath(undefined, [0, "freq"], 14.1) as { freq: number }[];
    expect(out).toEqual([{ freq: 14.1 }]);
  });
});

// --- linkedMeasFreqFor -----------------------------------------------------

describe("linkedMeasFreqFor", () => {
  const groupSchema = makeGroup({
    name: "bands",
    max_repeats: 2,
    params: [makeParam({ name: "freq", kind: "float", default: 14.1 })],
    default_overrides: [{}, {}],
    link_meas_freq_to_param: "freq",
  });
  const flatSchema = makeParam({
    name: "freq_02",
    kind: "float",
    link_meas_freq_to_param: "freq_02",
  });

  it("returns null when the example is undefined", () => {
    expect(linkedMeasFreqFor(undefined, ["freq_02"], {})).toBeNull();
  });

  it("resolves a flat-scalar link (path length 1)", () => {
    const ex = makeExample({ param_schema: [flatSchema] });
    const newRoot: ParamValueBag = { freq_02: 21.2 };
    expect(linkedMeasFreqFor(ex, ["freq_02"], newRoot)).toBe(21.2);
  });

  it("returns null for a flat scalar with no link_meas_freq_to_param declared", () => {
    const unlinked = makeParam({ name: "angle_deg" });
    const ex = makeExample({ param_schema: [unlinked] });
    expect(linkedMeasFreqFor(ex, ["angle_deg"], { angle_deg: 30 })).toBeNull();
  });

  it("returns null when the flat-scalar linked value is non-numeric", () => {
    const ex = makeExample({ param_schema: [flatSchema] });
    const newRoot: ParamValueBag = { freq_02: "n/a" };
    expect(linkedMeasFreqFor(ex, ["freq_02"], newRoot)).toBeNull();
  });

  it("resolves a group-leaf link (path = [groupName, instanceIdx, leafName])", () => {
    const ex = makeExample({ param_schema: [groupSchema] });
    const newRoot: ParamValueBag = {
      bands: [{ freq: 7.1 }, { freq: 21.2 }],
    };
    expect(linkedMeasFreqFor(ex, ["bands", 1, "freq"], newRoot)).toBe(21.2);
  });

  it("returns null when the group-leaf linked value is non-numeric", () => {
    const ex = makeExample({ param_schema: [groupSchema] });
    const newRoot: ParamValueBag = { bands: [{ freq: "n/a" }] };
    expect(linkedMeasFreqFor(ex, ["bands", 0, "freq"], newRoot)).toBeNull();
  });

  it("returns null for a group with no link_meas_freq_to_param declared", () => {
    const unlinkedGroup = makeGroup({
      name: "bands",
      params: [makeParam({ name: "freq" })],
    });
    const ex = makeExample({ param_schema: [unlinkedGroup] });
    const newRoot: ParamValueBag = { bands: [{ freq: 7.1 }] };
    expect(linkedMeasFreqFor(ex, ["bands", 0, "freq"], newRoot)).toBeNull();
  });

  it("returns null when path.length is 2 (too short for the group-leaf shape)", () => {
    const ex = makeExample({ param_schema: [groupSchema] });
    expect(linkedMeasFreqFor(ex, ["bands", 0], { bands: [{ freq: 1 }] })).toBeNull();
  });

  it("returns null when the group instance index is out of range", () => {
    const ex = makeExample({ param_schema: [groupSchema] });
    const newRoot: ParamValueBag = { bands: [{ freq: 7.1 }] };
    expect(linkedMeasFreqFor(ex, ["bands", 5, "freq"], newRoot)).toBeNull();
  });

  it("returns null when the group's current value isn't an array", () => {
    const ex = makeExample({ param_schema: [groupSchema] });
    const newRoot: ParamValueBag = { bands: "oops" };
    expect(linkedMeasFreqFor(ex, ["bands", 0, "freq"], newRoot)).toBeNull();
  });
});

// --- overlaySchemaForVariant -----------------------------------------------------

describe("overlaySchemaForVariant", () => {
  it("returns [] when the example is undefined", () => {
    expect(overlaySchemaForVariant(undefined, "default")).toEqual([]);
  });

  it("passes the schema through unchanged (same reference) when the variant has no variant_ui entry", () => {
    const schema: SchemaItem[] = [makeParam({ name: "angle_deg" })];
    const ex = makeExample({ param_schema: schema });
    expect(overlaySchemaForVariant(ex, "default")).toBe(schema);
  });

  it("overlays a per-param override onto the matching scalar", () => {
    const schema: SchemaItem[] = [
      makeParam({ name: "length_factor", min: 0.5, max: 1.5 }),
    ];
    const ex = makeExample({
      param_schema: schema,
      variant_ui: {
        longwire: { params: { length_factor: { min: 1, max: 4 } } },
      },
    });
    const out = overlaySchemaForVariant(ex, "longwire");
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ name: "length_factor", min: 1, max: 4 });
  });

  it("hides a param the variant marks hidden, but leaves groups untouched (same reference)", () => {
    const group = makeGroup({ name: "bands" });
    const schema: SchemaItem[] = [makeParam({ name: "angle_deg" }), group];
    const ex = makeExample({
      param_schema: schema,
      variant_ui: {
        dipole: { params: { angle_deg: { hidden: true } } },
      },
    });
    const out = overlaySchemaForVariant(ex, "dipole");
    expect(out).toHaveLength(1);
    expect(out[0]).toBe(group);
  });

  it("falls back to the base schema (same reference) for a variant absent from variant_ui", () => {
    const schema: SchemaItem[] = [makeParam({ name: "angle_deg" })];
    const ex = makeExample({
      param_schema: schema,
      variant_ui: { longwire: { params: {} } },
    });
    expect(overlaySchemaForVariant(ex, "default")).toBe(schema);
  });
});

// --- groupExamplesForPicker -----------------------------------------------------

describe("groupExamplesForPicker", () => {
  const dipole = makeExample({ name: "dipoles.invvee", label: "Inverted Vee" });
  const yagi = makeExample({ name: "beams.yagi", label: "Yagi-Uda Beam" });
  const quad = makeExample({ name: "loops.quad", label: "Cubical Quad" });
  const examples = [dipole, yagi, quad];

  it("keeps the selected example visible even when the query matches nothing else", () => {
    const groups = groupExamplesForPicker(examples, "dipoles.invvee", "zzzznomatch");
    const names = groups.flatMap((g) => g.items.map((i) => i.name));
    expect(names).toEqual(["dipoles.invvee"]);
  });

  it("groups by family and orders groups by familyRank (dipoles, then loops, then beams)", () => {
    const groups = groupExamplesForPicker(examples, "", "");
    expect(groups.map((g) => g.fam)).toEqual(["dipoles", "loops", "beams"]);
    expect(groups.map((g) => g.label)).toEqual([
      FAMILY_LABELS.dipoles,
      FAMILY_LABELS.loops,
      FAMILY_LABELS.beams,
    ]);
  });

  it("sorts items within a family by label", () => {
    const dipoleZ = makeExample({ name: "dipoles.zepp", label: "AAA Zepp" });
    const groups = groupExamplesForPicker([dipole, dipoleZ], "", "");
    expect(groups[0].items.map((i) => i.label)).toEqual(["AAA Zepp", "Inverted Vee"]);
  });

  it("filters non-selected examples by matchesQuery", () => {
    const groups = groupExamplesForPicker(examples, "dipoles.invvee", "yagi");
    const names = groups.flatMap((g) => g.items.map((i) => i.name)).sort();
    expect(names).toEqual(["beams.yagi", "dipoles.invvee"]);
  });
});

// --- defaultKnobOpt -----------------------------------------------------

describe("defaultKnobOpt", () => {
  it("seeds vary:false and mirrors the schema's min/max/step", () => {
    const schema: SchemaItem[] = [
      makeParam({ name: "length_factor", min: 0.5, max: 2, step: 0.01 }),
    ];
    expect(defaultKnobOpt(schema, "length_factor")).toEqual({
      vary: false,
      optMin: 0.5,
      optMax: 2,
      dispMin: 0.5,
      dispMax: 2,
      step: 0.01,
    });
  });

  it("falls back to 0/1/0.001 when the param name isn't in the schema", () => {
    expect(defaultKnobOpt([], "missing")).toEqual({
      vary: false,
      optMin: 0,
      optMax: 1,
      dispMin: 0,
      dispMax: 1,
      step: 0.001,
    });
  });

  it("falls back to 0/1/0.001 when the matched param's min/max/step are null", () => {
    const schema: SchemaItem[] = [
      makeParam({ name: "n_directors", min: null, max: null, step: null }),
    ];
    expect(defaultKnobOpt(schema, "n_directors")).toEqual({
      vary: false,
      optMin: 0,
      optMax: 1,
      dispMin: 0,
      dispMax: 1,
      step: 0.001,
    });
  });

  it("does not match a group with the same name (only scalar leaves are eligible)", () => {
    const group = makeGroup({ name: "length_factor" });
    expect(defaultKnobOpt([group], "length_factor")).toEqual({
      vary: false,
      optMin: 0,
      optMax: 1,
      dispMin: 0,
      dispMax: 1,
      step: 0.001,
    });
  });
});
