// AK#2321 (interim): a link carries a design's flat knobs only, so a
// repeated group's edited members (a fan dipole's bands) must be SAID to be
// left out, never dropped silently.
import { describe, it, expect } from "vitest";
import { linkKnobsOf, linkOmission } from "../lib/deepLink";
import { seedDefaults, type SchemaItem } from "../lib/params";

const leaf = (name: string, d: number) => ({
  kind: "float" as const,
  name,
  label: name,
  default: d,
  min: 0,
  max: 100,
});

// A fan dipole's shape: a flat `n_bands` and a `bands` group of five.
const SCHEMA = [
  { ...leaf("n_bands", 3), kind: "int" as const },
  {
    kind: "group" as const,
    name: "bands",
    label_template: "band {i}",
    repeat_count: "n_bands",
    max_repeats: 5,
    params: [leaf("freq", 14), leaf("length_factor", 0.5)],
    default_overrides: [
      { freq: 14 },
      { freq: 21 },
      { freq: 28 },
      { freq: 24.9 },
      { freq: 18.1 },
    ],
  },
] as unknown as SchemaItem[];

const DEFAULTS = seedDefaults(SCHEMA);
const clone = () =>
  structuredClone(DEFAULTS) as Record<string, unknown> & {
    bands: Record<string, number>[];
  };

describe("linkOmission (AK#2321)", () => {
  it("is silent for the design as it ships", () => {
    expect(linkOmission(SCHEMA, clone(), DEFAULTS)).toBeNull();
  });

  it("names each edited band, which the link's knobs do not carry", () => {
    const v = clone();
    v.bands[0].freq = 3.6;
    v.bands[2].length_factor = 0.49;
    const said = linkOmission(SCHEMA, v, DEFAULTS);
    expect(said).toContain("band 1, band 3");
    expect(said).toContain("Save the design or export a deck");
    // ...because the link itself has none of it: a group's leaves are no knobs
    expect(linkKnobsOf(SCHEMA, v, DEFAULTS, new Map())).toEqual([]);
  });

  it("looks only at the bands the repeat count shows", () => {
    const v = clone();
    v.bands[4].freq = 7.1; // band 5, hidden while n_bands is 3
    expect(linkOmission(SCHEMA, v, DEFAULTS)).toBeNull();
    v.n_bands = 5;
    expect(linkOmission(SCHEMA, v, DEFAULTS)).toContain("band 5");
  });

  it("says nothing for a design with no group", () => {
    const flat = [leaf("freq", 14)] as unknown as SchemaItem[];
    expect(linkOmission(flat, { freq: 7 }, { freq: 14 })).toBeNull();
  });
});
