// The map and hold builders' specs and Copy link's bounds (AK#2045), alone.
import { describe, expect, it } from "vitest";
import {
  analysesText,
  type Build,
  BUILD_MAX_POINTS,
  buildData,
  buildProblem,
  defaultBuildName,
  holdRange,
  holdRangeText,
  linkPartsProblem,
  uniqueName,
} from "../lib/buildAnalysis";
import { MAX_SHARE_CHARS } from "../lib/decks";
import { linkSearch, parseDeepLink } from "../lib/deepLink";
import type { SchemaParamSpec } from "../lib/params";

const knob = (over: Partial<SchemaParamSpec>): SchemaParamSpec => ({
  name: "sy_long_ft",
  label: "L",
  default: 17.066,
  kind: "float",
  min: 15,
  max: 36,
  step: 0.02,
  precision: 3,
  unit: null,
  visible_when: null,
  auto_range: false,
  ...over,
});
const KNOBS = [
  knob({}),
  knob({ name: "sy_short_ft", label: "M", min: 1, max: 34 }),
  // An opened deck's SY knob the link gave no range: the app's own window.
  knob({ name: "sy_h", label: "H", min: 5, max: 15, auto_range: true }),
];
const axis = (knob: string, lo: number, hi: number, points: number) => ({ knob, lo, hi, points, log: false });
const map: Build = { kind: "map", name: "m", x: axis("sy_long_ft", 16, 36, 41), y: axis("sy_short_ft", 1, 34, 34) };
const hold: Build = {
  kind: "hold",
  name: "high-R",
  sweep: axis("sy_short_ft", 33, 3.5, 31),
  objective: "resonance",
  adjust: ["sy_long_ft"],
};

describe("what a builder builds", () => {
  it("a map: two sweeps, the Map view, X = 0 as its contour", () => {
    expect(buildProblem(map, KNOBS)).toBeNull();
    expect(buildData(map)).toEqual({
      an: "Analysis",
      name: "m",
      sweep: [
        { an: "Sweep", knob: "sy_long_ft", lo: 16, hi: 36, points: 41 },
        { an: "Sweep", knob: "sy_short_ft", lo: 1, hi: 34, points: 34 },
      ],
      views: [{ an: "Map" }],
      references: { an: "Ref", x: [0] },
    });
  });

  it("a held sweep: the sweep (either way), R/X and the Knobs view, the hold", () => {
    expect(buildProblem(hold, KNOBS)).toBeNull();
    expect(buildData(hold)).toEqual({
      an: "Analysis",
      name: "high-R",
      sweep: { an: "Sweep", knob: "sy_short_ft", lo: 33, hi: 3.5, points: 31 },
      views: [{ an: "Rx" }, { an: "Knobs" }],
      hold: { an: "Hold", objective: "resonance", adjust: ["sy_long_ft"] },
    });
    const logged = { ...hold, sweep: { ...hold.sweep, log: true } } as Build;
    expect((buildData(logged).sweep as Record<string, unknown>).spacing).toBe("log");
  });

  it("a held deck knob searches the range set in its Optimize menu (an.Hold bounds)", () => {
    // Mike's doublet as a deck: an SY knob has only the app's automatic
    // window, so the hold takes the range the user set for it.
    const deck: Build = {
      ...hold,
      sweep: axis("sy_long_ft", 30, 36, 13),
      adjust: ["sy_h"],
      ranges: { sy_h: { min: 1, max: 16 } },
    };
    expect(buildProblem(deck, KNOBS)).toBeNull();
    expect((buildData(deck) as { hold: unknown }).hold).toEqual({
      an: "Hold",
      objective: "resonance",
      adjust: ["sy_h"],
      bounds: [{ an: "Knob", name: "sy_h", min: 1, max: 16 }],
    });
    const h = KNOBS[2];
    expect(holdRange(h, { min: 1, max: 16 })).toEqual({ lo: 1, hi: 16, from: "optimize" });
    expect(holdRange(h, null)).toBeNull();
    expect(holdRange(KNOBS[1], null)).toEqual({ lo: 1, hi: 34, from: "own" });
    expect(holdRangeText(h, { min: 1, max: 16 })).toBe("H searched over 1 to 16 (its Optimize menu's range)");
    expect(holdRangeText(KNOBS[1])).toBe("M searched over 1 to 34 (its own range)");
    // A range inside a knob's own is taken as the hold's.
    const inside: Build = { ...hold, ranges: { sy_long_ft: { min: 20, max: 30 } } };
    expect(buildProblem(inside, KNOBS)).toBeNull();
    expect((buildData(inside) as { hold: { bounds: unknown } }).hold.bounds).toEqual([
      { an: "Knob", name: "sy_long_ft", min: 20, max: 30 },
    ]);
  });

  it.each([
    [{ ...map, name: "  " }, "Give the analysis a name"],
    [{ ...map, y: map.x }, "A map sweeps two different knobs"],
    [{ ...map, x: axis("nope", 1, 2, 3) }, 'no knob "nope" to sweep'],
    [{ ...map, x: axis("sy_long_ft", 20, 20, 3) }, "L: the two ends are the same"],
    [{ ...map, x: axis("sy_long_ft", 20, NaN, 3) }, "L: the ends are numbers"],
    [{ ...map, x: axis("sy_long_ft", 20, 30, 1) }, "points is a whole number from 2"],
    [{ ...map, x: axis("sy_long_ft", 20, 30, BUILD_MAX_POINTS + 1) }, "points is a whole number"],
    [{ ...map, x: axis("sy_long_ft", 20, 30, 2.5) }, "points is a whole number"],
    [{ ...map, x: { ...axis("sy_long_ft", -1, 30, 3), log: true } }, "a log sweep needs both ends above zero"],
    [{ ...hold, adjust: ["sy_short_ft"] }, "M is the swept knob: a knob is swept or held, not both"],
    [{ ...hold, adjust: ["sy_long_ft", "sy_h"] }, "adjusts one knob"],
    [{ ...hold, objective: "match_z0", adjust: ["sy_long_ft"] }, "adjusts 2 knobs"],
    [
      { ...hold, adjust: ["sy_h"] },
      "H has no range for the hold to search: set one in its Optimize menu (right-click the knob)",
    ],
    [
      { ...hold, ranges: { sy_long_ft: { min: 10, max: 30 } } },
      "L: its Optimize range 10 to 30 reaches outside its own 15 to 36",
    ],
    [{ ...hold, objective: "swr" as never }, 'No hold target "swr"'],
  ] as [Build, string][])("refuses %#: %s", (b, words) => {
    expect(buildProblem(b, KNOBS)).toContain(words);
  });

  it("names itself by its knobs, never one the picker lists", () => {
    const label = (k: string) => KNOBS.find((s) => s.name === k)!.label;
    expect(defaultBuildName(map, label, new Set())).toBe("map L × M");
    expect(defaultBuildName(map, label, new Set(["map L × M"]))).toBe("map L × M (2)");
    expect(defaultBuildName(hold, label, new Set())).toBe("M 33 to 3.5, L held at resonance");
    expect(uniqueName("a", new Set(["a", "a (2)"]))).toBe("a (3)");
  });
});

describe("what Copy link writes of the analyses", () => {
  it("one list of the expressions, as analyses_text.write prints it", () => {
    expect(analysesText(['an.Analysis(\n    "a",\n)', "an.convergence()"])).toBe(
      '[\n    an.Analysis(\n        "a",\n    ),\n    an.convergence(),\n]\n',
    );
    expect(analysesText([])).toBe("[\n]\n");
  });

  it("refuses a part over what a link carries, by part", () => {
    expect(linkPartsProblem({ deck: MAX_SHARE_CHARS, analyses: MAX_SHARE_CHARS })).toBeNull();
    expect(linkPartsProblem({ deck: MAX_SHARE_CHARS + 1 })).toContain(
      `The deck is ${MAX_SHARE_CHARS + 1} characters packed, over the ${MAX_SHARE_CHARS}`,
    );
    expect(linkPartsProblem({ analyses: MAX_SHARE_CHARS + 1 })).toContain("The analyses are");
    expect(linkPartsProblem({ knobs: "too many knobs" })).toBe("too many knobs");
  });

  it("a catalog design's link carries analyses= beside the design, read and written back", () => {
    const d = parseDeepLink("?design=dipoles.two_wire_doublet&analyses=abc&analysis=x")!;
    expect(d.analyses).toBe("abc");
    expect(d.deck).toBeUndefined();
    expect(parseDeepLink("?analyses=abc")).not.toBeNull();
    // Beside a deck it rides the deck, never the design.
    const k = parseDeepLink("?deck=z&name=d.nec&analyses=abc")!;
    expect(k.analyses).toBeUndefined();
    expect(k.deck!.analyses).toBe("abc");
    const base = { variant: null, analysis: "x", view: null };
    expect(linkSearch("", { ...base, design: "dipoles.two_wire_doublet", analyses: "abc" })).toBe(
      "?design=dipoles.two_wire_doublet&analyses=abc&analysis=x",
    );
    // A deck's state writes its payload's, never a design-side one.
    expect(
      linkSearch("", { ...base, design: "deck.0123456789ab", deck: { z: "z", name: "d.nec", analyses: "q" }, analyses: "abc" }),
    ).toBe("?deck=z&name=d.nec&analyses=q&analysis=x");
  });
});
