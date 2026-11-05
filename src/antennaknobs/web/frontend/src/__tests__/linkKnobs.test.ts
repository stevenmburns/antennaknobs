// Knob values and ranges in a link (AK#2045, `knobs=`): the grammar, what
// the panel takes of it on a design, and what the writer writes, alone.
import { describe, it, expect } from "vitest";
import {
  knobRanges,
  knobsParam,
  linkKnobsOf,
  linkKnobValues,
  linkNumber,
  linkSearch,
  MAX_LINK_KNOBS,
  MAX_LINK_KNOBS_CHARS,
  parseDeepLink,
  parseKnobs,
  rangesOf,
} from "../lib/deepLink";
import type { SchemaParamSpec } from "../lib/params";

const knob = (over: Partial<SchemaParamSpec>): SchemaParamSpec => ({
  name: "long_ft",
  label: "L",
  default: 17.066,
  kind: "float",
  min: 15,
  max: 36,
  step: 0.01,
  precision: 2,
  unit: "ft",
  visible_when: null,
  auto_range: false,
  ...over,
});

const SCHEMA = [
  knob({}),
  knob({ name: "short_ft", label: "M", min: 1, max: 34 }),
  knob({ name: "segs", kind: "int", default: 20, min: 10, max: 30, step: 1 }),
  knob({ name: "free", default: 2, min: 1, max: 3, auto_range: true }),
  knob({
    name: "wire",
    kind: "enum",
    default: "copper",
    min: null,
    max: null,
    enum_options: ["copper", "steel", "B034+B099", "a:b,c"].map((value) => ({ value, label: value })),
  }),
  knob({ name: "band", kind: "enum", default: "40", min: null, max: null, enum_options: [
    { value: "40", label: "40 m" },
    { value: "20", label: "20 m" },
  ] }),
  knob({ name: "lit", kind: "bool", default: false, min: null, max: null }),
];

describe("the knobs= grammar", () => {
  it("reads values and ranges, and writes them back as they read", () => {
    const raw = "sy_long_ft:33:15:36,sy_short_ft:17,x:-1.5e-3:-2:0.5";
    const { knobs, problems } = parseKnobs(raw);
    expect(problems).toEqual([]);
    expect(knobs).toEqual([
      { name: "sy_long_ft", value: 33, min: 15, max: 36 },
      { name: "sy_short_ft", value: 17 },
      { name: "x", value: -0.0015, min: -2, max: 0.5 },
    ]);
    expect(parseKnobs(knobsParam(knobs)).knobs).toEqual(knobs);
    expect(knobRanges(knobs)).toBe("sy_long_ft:15:36,x:-2:0.5");
    expect(rangesOf(knobRanges(knobs))).toEqual(
      new Map([
        ["sy_long_ft", [15, 36]],
        ["x", [-2, 0.5]],
      ]),
    );
  });

  it("numbers are decimal and finite, nothing Number() alone would take", () => {
    for (const ok of ["1", "-1", "+2.5", ".5", "5.", "1e3", "1E-3", "1e+21"]) expect(linkNumber(ok)).not.toBeNull();
    for (const bad of ["", " 1", "1 ", "0x10", "Infinity", "NaN", "1_0", "1e999", "1,0", "(1)", "1e"]) {
      expect(linkNumber(bad)).toBeNull();
    }
  });

  it.each([
    ["long_ft", `"long_ft" is not <knob>:<value>[:<min>:<max>]`],
    ["long_ft:1:2", `"long_ft:1:2" is not <knob>:<value>[:<min>:<max>]`],
    ["long_ft:1:2:3:4", "is not <knob>:<value>"],
    ["1x:3", `"1x:3" is not <knob>`],
    ["a.b:3", `"a.b:3" is not <knob>`],
    ["long_ft:%E0%A4%A", `long_ft's "long_ft:%E0%A4%A" has a value that is neither a number nor a dropdown option`],
    [`long_ft:${"x".repeat(65)}`, "neither a number nor a dropdown option"],
    ["long_ft:abc:1:2", `long_ft's "long_ft:abc:1:2" has a value that is not a finite decimal number`],
    ["long_ft:1:Infinity:3", "not a finite decimal number"],
    ["long_ft:20:36:15", "long_ft's range 36:15 does not have min < max"],
    ["long_ft:40:15:36", "long_ft's value 40 is outside its range 15:36"],
    ["long_ft:20,long_ft:21", "long_ft is given twice"],
  ])("refuses %s by name, and keeps the rest", (bad, words) => {
    const { knobs, problems } = parseKnobs(`${bad},short_ft:9`);
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain(words);
    expect(knobs.map((k) => k.name)).toContain("short_ft");
  });

  it("is bounded in entries and characters", () => {
    const many = Array.from({ length: MAX_LINK_KNOBS + 1 }, (_, i) => `k${i}:1`).join(",");
    expect(parseKnobs(many)).toEqual({ knobs: [], problems: [expect.stringContaining(`over the ${MAX_LINK_KNOBS}`)] });
    const long = `k:${"1".repeat(MAX_LINK_KNOBS_CHARS)}`;
    expect(parseKnobs(long).problems[0]).toContain(`over the ${MAX_LINK_KNOBS_CHARS}`);
  });

  it("a link with knobs= is a link; its ranges ride the deck, its values do not", () => {
    const d = parseDeepLink("?design=dipoles.two_wire_doublet&knobs=long_ft:33,bad")!;
    expect(d.design).toBe("dipoles.two_wire_doublet");
    expect(d.knobs).toEqual([{ name: "long_ft", value: 33 }]);
    expect(d.knobsProblems).toEqual([`knobs: "bad" is not <knob>:<value>[:<min>:<max>]`]);
    expect(d.deck).toBeUndefined();
    const k = parseDeepLink("?deck=abc&name=d.nec&knobs=sy_a:3:1:5,sy_b:2")!;
    expect(k.deck).toEqual({ z: "abc", name: "d.nec", ranges: "sy_a:1:5" });
    // No range: the deck payload has none (its key is the old one).
    expect(parseDeepLink("?deck=abc&name=d.nec&knobs=sy_b:2")!.deck).toEqual({ z: "abc", name: "d.nec" });
    expect(parseDeepLink("?knobs=long_ft:3")).not.toBeNull();
  });
});

describe("what the panel takes of a link's knobs", () => {
  it("sets the values on a catalog design, and refuses a range there by name", () => {
    const { knobs } = parseKnobs("long_ft:33,short_ft:5:2:10,segs:24");
    const { values, problems } = linkKnobValues(knobs, SCHEMA, { deck: false });
    expect(values).toEqual({ long_ft: 33, short_ft: 5, segs: 24 });
    expect(problems).toEqual([
      "knobs: short_ft's range 2:10 is not applied: a link gives a range only to an opened deck's knob, " +
        "and this design's own (1 to 34) stands",
    ]);
  });

  it("on an opened deck the range is the knob's own already, and stands", () => {
    const { knobs } = parseKnobs("long_ft:33:15:36");
    expect(linkKnobValues(knobs, SCHEMA, { deck: true })).toEqual({ values: { long_ft: 33 }, problems: [] });
  });

  it.each([
    ["nope:1", `knobs: this design has no knob "nope"`],
    ["wire:1", `knobs: wire has no option "1"; it offers copper, steel, B034+B099, a:b,c`],
    ["band:20:10:30", "knobs: band is a dropdown, which takes no range"],
    ["long_ft:steel", `knobs: long_ft takes a number, not "steel"`],
    ["lit:1", `knobs: "lit" is not a numeric or dropdown knob`],
    ["segs:20.5", `knobs: "segs" takes a whole number, not 20.5`],
    ["long_ft:99", "knobs: long_ft's value 99 is outside its range 15 to 36"],
  ])("refuses %s by name, and sets nothing of it", (raw, words) => {
    const { values, problems } = linkKnobValues(parseKnobs(raw).knobs, SCHEMA, { deck: false });
    expect(values).toEqual({});
    expect(problems).toEqual([words]);
  });

  it("a knob with only the app's own window takes any value, as its field does", () => {
    const { values, problems } = linkKnobValues(parseKnobs("free:9").knobs, SCHEMA, { deck: false });
    expect(values).toEqual({ free: 9 });
    expect(problems).toEqual([]);
  });
});

describe("what a link writes of the knobs", () => {
  const defaults = { long_ft: 17.066, short_ft: 17.066, segs: 20, free: 2, wire: "copper", band: "40", lit: false };

  it("writes a knob moved off its default, and a deck's ranged knob always", () => {
    const values = { ...defaults, short_ft: 5 };
    expect(linkKnobsOf(SCHEMA, values, defaults, new Map())).toEqual([{ name: "short_ft", value: 5 }]);
    expect(linkKnobsOf(SCHEMA, defaults, defaults, new Map())).toEqual([]);
    const ranged = linkKnobsOf(SCHEMA, values, defaults, new Map([["long_ft", [15, 36] as [number, number]]]));
    expect(ranged).toEqual([
      { name: "long_ft", value: 17.066, min: 15, max: 36 },
      { name: "short_ft", value: 5 },
    ]);
  });

  it("linkSearch writes knobs= bare (colons and commas), beside a design or a deck", () => {
    const knobs = [
      { name: "sy_long_ft", value: 33, min: 15, max: 36 },
      { name: "sy_short_ft", value: 17 },
    ];
    const base = { variant: null, analysis: null, view: null, knobs };
    const s = linkSearch("?knobs=stale", { ...base, design: "dipoles.two_wire_doublet" });
    // Beside a catalog design a range is never written: only a deck takes one.
    expect(s).toBe("?design=dipoles.two_wire_doublet&knobs=sy_long_ft:33,sy_short_ft:17");
    const deck = { z: "abc", name: "d.nec", ranges: "sy_long_ft:15:36" };
    const d = linkSearch("", { ...base, design: "deck.0123456789ab", deck });
    expect(d).toBe("?deck=abc&name=d.nec&knobs=sy_long_ft:33:15:36,sy_short_ft:17");
    // Read back, the ranges ride the deck again.
    expect(parseDeepLink(d)!.deck).toEqual(deck);
    // No knobs moved: none written, and a stale one dropped.
    expect(linkSearch("?knobs=stale", { ...base, knobs: [], design: "dipoles.x" })).toBe("?design=dipoles.x");
  });

  it("a deck too long to carry falls back to its key, and the ranges stay with it", () => {
    const knobs = [{ name: "sy_a", value: 3, min: 1, max: 5 }];
    const deck = { z: "x".repeat(9000), name: "d.nec", ranges: "sy_a:1:5" };
    const s = linkSearch("", { design: "deck.0123456789ab", variant: null, analysis: null, view: null, knobs, deck });
    expect(s).toBe("?design=deck.0123456789ab&knobs=sy_a:3");
  });
});

describe("a dropdown knob in a link (AK#2163)", () => {
  const defaults = { long_ft: 17.066, short_ft: 17.066, segs: 20, free: 2, wire: "copper", band: "40", lit: false };
  const base = { design: "user.choke", analyses: null, deck: null, variant: null, analysis: null, view: null };

  it("sets a dropdown beside a number, matched exactly", () => {
    const { knobs, problems } = parseKnobs("wire:steel,long_ft:20");
    expect(problems).toEqual([]);
    expect(linkKnobValues(knobs, SCHEMA, { deck: false })).toEqual({
      values: { wire: "steel", long_ft: 20 },
      problems: [],
    });
    expect(linkKnobValues(parseKnobs("wire:Steel").knobs, SCHEMA, { deck: false }).values).toEqual({});
  });

  it("an option spelled as a number reads back as that option", () => {
    expect(linkKnobValues(parseKnobs("band:20").knobs, SCHEMA, { deck: false })).toEqual({
      values: { band: "20" },
      problems: [],
    });
  });

  it("an unknown option is refused by name and the rest still applies", () => {
    const { values, problems } = linkKnobValues(parseKnobs("wire:B999,segs:24").knobs, SCHEMA, { deck: false });
    expect(values).toEqual({ segs: 24 });
    expect(problems).toEqual([`knobs: wire has no option "B999"; it offers copper, steel, B034+B099, a:b,c`]);
  });

  it.each(["steel", "B034+B099", "a:b,c", "50%"])("Copy link reproduces the dropdown at %s", (option) => {
    const opts = [...(SCHEMA[4] as SchemaParamSpec).enum_options!, { value: "50%", label: "half" }];
    const schema = SCHEMA.map((k) => (k.name === "wire" ? { ...k, enum_options: opts } : k));
    const values = { ...defaults, wire: option, band: "20", segs: 24 };
    const knobs = linkKnobsOf(schema, values, defaults, new Map());
    expect(knobs).toEqual([
      { name: "segs", value: 24 },
      { name: "wire", value: option },
      { name: "band", value: "20" },
    ]);
    const search = linkSearch("", { ...base, knobs });
    const back = parseDeepLink(search)!;
    expect(back.knobsProblems).toBeUndefined();
    expect(linkKnobValues(back.knobs!, schema, { deck: false })).toEqual({
      values: { segs: 24, wire: option, band: "20" },
      problems: [],
    });
  });

  it("writes an option's + once, as %2B, and its grammar characters escaped", () => {
    const search = linkSearch("", { ...base, knobs: [{ name: "wire", value: "B034+B099" }] });
    expect(search).toBe("?design=user.choke&knobs=wire:B034%2BB099");
    const odd = linkSearch("", { ...base, knobs: [{ name: "wire", value: "a:b,c" }] });
    expect(odd).toBe("?design=user.choke&knobs=wire:a%253Ab%252Cc");
  });

  it.each(["1:4", "225:4", "49-1 U 001"])("a shipped option %s survives the round trip", (option) => {
    const schema = [
      knob({ name: "ratio", kind: "enum", default: "1:1", min: null, max: null, enum_options: [
        { value: "1:1", label: "1:1" },
        { value: option, label: option },
      ] }),
    ];
    const search = linkSearch("", { ...base, knobs: [{ name: "ratio", value: option }] });
    const back = parseDeepLink(search)!;
    expect(back.knobsProblems).toBeUndefined();
    expect(linkKnobValues(back.knobs!, schema, { deck: false }).values).toEqual({ ratio: option });
  });

  it("a hand-typed %2B reads as +", () => {
    const d = parseDeepLink("?design=user.choke&knobs=wire:B034%2BB099")!;
    expect(d.knobs).toEqual([{ name: "wire", value: "B034+B099" }]);
  });
});
