// Workbench deep links (AK#1838): the grammar and the resolution, alone.
import { describe, it, expect } from "vitest";
import type { AnalysisEntry } from "../lib/analyses";
import {
  linkHref,
  linkSearch,
  parseDeepLink,
  resolveAnalysis,
  resolveDesign,
  resolveVariant,
  resolveView,
} from "../lib/deepLink";
import type { ExampleDescriptor } from "../lib/params";
import { HARNESS_EXAMPLE } from "./designSessionHarness";

const ex = (name: string, variants = ["default"]): ExampleDescriptor => ({
  ...HARNESS_EXAMPLE,
  name,
  variants,
});

const CATALOG = [
  ex("dipoles.invvee", ["default", "long"]),
  ex("verticals.m0agp_invl"),
  ex("beams.moxon"),
  ex("wires.moxon"),
  ex("user.mine"),
];

const entry = (name: string, study?: { source: string; name: string }): AnalysisEntry => ({
  name,
  summary: "",
  code: "",
  problems: [],
  workbench: { runs: false, why: "test" },
  ...(study ? { study } : {}),
});

const study = (source: string, name: string) => entry(`${source}:${name}`, { source, name });

describe("parseDeepLink", () => {
  it("is null for a plain visit, or one with only other parameters", () => {
    expect(parseDeepLink("")).toBeNull();
    expect(parseDeepLink("?foo=1")).toBeNull();
    expect(parseDeepLink("?design=&analysis=%20")).toBeNull();
  });

  it("reads the design, its variant, the analysis and the view", () => {
    expect(
      parseDeepLink("?design=dipoles.invvee:long&analysis=resonance%20vs%20angle&view=Knobs"),
    ).toEqual({
      design: "dipoles.invvee",
      variant: "long",
      analysis: "resonance vs angle",
      view: "Knobs",
      run: false,
    });
    // A "+" is a space in a query, as a form writes it.
    expect(parseDeepLink("?design=dipoles.invvee&analysis=resonance+vs+angle")?.analysis).toBe(
      "resonance vs angle",
    );
  });

  it("splits the variant at the first colon; an empty one is none", () => {
    expect(parseDeepLink("?design=a.b:c:d")).toMatchObject({ design: "a.b", variant: "c:d" });
    expect(parseDeepLink("?design=a.b:")).toMatchObject({ design: "a.b", variant: null });
  });

  it("keeps a study's full name whole: its colon is the analysis's, not a variant", () => {
    expect(
      parseDeepLink("?design=dipoles.invvee&analysis=dipoles.apex_feed_on_invvee%3Afeed%20spelling%20(E7)"),
    ).toMatchObject({
      design: "dipoles.invvee",
      variant: null,
      analysis: "dipoles.apex_feed_on_invvee:feed spelling (E7)",
    });
  });

  it("runs only for run=1", () => {
    expect(parseDeepLink("?design=a.b")?.run).toBe(false);
    expect(parseDeepLink("?design=a.b&run=1")?.run).toBe(true);
    expect(parseDeepLink("?design=a.b&run=true")?.run).toBe(false);
    expect(parseDeepLink("?design=a.b&run=0")?.run).toBe(false);
  });
});

describe("resolveDesign", () => {
  it("takes a full name as it is", () => {
    expect(resolveDesign("dipoles.invvee", CATALOG)).toEqual({ ok: true, value: "dipoles.invvee" });
    expect(resolveDesign("user.mine", CATALOG)).toEqual({ ok: true, value: "user.mine" });
  });

  it("takes a bare name one family holds, as the CLI does", () => {
    expect(resolveDesign("m0agp_invl", CATALOG)).toEqual({ ok: true, value: "verticals.m0agp_invl" });
  });

  it("refuses a bare name two families hold, naming both", () => {
    const r = resolveDesign("moxon", CATALOG);
    expect(r.ok).toBe(false);
    expect(!r.ok && r.problem).toBe('design "moxon" is ambiguous: give one of "beams.moxon", "wires.moxon"');
  });

  it("never reaches a user design by its bare name", () => {
    expect(resolveDesign("mine", CATALOG).ok).toBe(false);
  });

  it("names an unknown design, and says a user design is per machine", () => {
    const r = resolveDesign("dipoles.nope", CATALOG);
    expect(!r.ok && r.problem).toBe(`no design "dipoles.nope" in this workbench's catalog`);
    const u = resolveDesign("user.theirs", CATALOG);
    expect(!u.ok && u.problem).toBe(
      'design "user.theirs" is not here: a user design opens only on the machine that has it',
    );
  });
});

describe("resolveVariant", () => {
  it("takes a variant the design has, and names one it has not", () => {
    expect(resolveVariant("long", CATALOG[0])).toEqual({ ok: true, value: "long" });
    const r = resolveVariant("short", CATALOG[0]);
    expect(!r.ok && r.problem).toBe('design "dipoles.invvee" has no variant "short"; its variants: default, long');
  });
});

describe("resolveAnalysis (studies.find's order over the picker's entries)", () => {
  const entries = [
    entry("convergence"),
    entry("resonance vs angle"),
    study("dipoles.apex_feed_on_invvee", "feed spelling (E7)"),
    study("verticals.m0agp_invl", "invl vs vertical"),
    study("verticals.m0agp_invl", "invl vs vertical, buried"),
    study("dipoles.twins", "same name"),
    study("dipoles.twins2", "same name"),
    study("dipoles.solo", "convergence"),
  ];
  const name = (q: string) => {
    const r = resolveAnalysis(q, entries);
    return r.ok ? r.value.name : r.problem;
  };

  it("takes the design's own analysis by its name", () => {
    expect(name("resonance vs angle")).toBe("resonance vs angle");
  });

  it("takes a study by its full name", () => {
    expect(name("dipoles.apex_feed_on_invvee:feed spelling (E7)")).toBe(
      "dipoles.apex_feed_on_invvee:feed spelling (E7)",
    );
  });

  it("takes a study by its source when that holds one study", () => {
    expect(name("dipoles.apex_feed_on_invvee")).toBe("dipoles.apex_feed_on_invvee:feed spelling (E7)");
  });

  it("takes a study by its bare name when one study has it", () => {
    expect(name("feed spelling (E7)")).toBe("dipoles.apex_feed_on_invvee:feed spelling (E7)");
  });

  it("puts the full name first: an own analysis wins over a study's bare name", () => {
    expect(name("convergence")).toBe("convergence");
  });

  it("refuses an ambiguous source or bare name, naming the candidates", () => {
    expect(name("verticals.m0agp_invl")).toBe(
      'analysis "verticals.m0agp_invl" is ambiguous: give one of ' +
        '"verticals.m0agp_invl:invl vs vertical", "verticals.m0agp_invl:invl vs vertical, buried"',
    );
    expect(name("same name")).toBe(
      'analysis "same name" is ambiguous: give one of "dipoles.twins:same name", "dipoles.twins2:same name"',
    );
  });

  it("names an unknown analysis and what the design lists", () => {
    expect(name("nope")).toMatch(/^no analysis "nope" on this design; it lists "convergence", /);
    const r = resolveAnalysis("nope", []);
    expect(!r.ok && r.problem).toBe('no analysis "nope": this design lists none');
  });
});

describe("resolveView", () => {
  it("takes a view the chart draws, and names one it does not", () => {
    expect(resolveView("Knobs", ["Rx", "Smith", "Table", "Knobs"])).toEqual({ ok: true, value: "Knobs" });
    const r = resolveView("Spiral", ["Rx", "Smith"]);
    expect(!r.ok && r.problem).toBe('no view "Spiral" on this chart; it draws Rx, Smith');
  });
});

describe("linkSearch / linkHref", () => {
  const state = { design: "dipoles.invvee", variant: null, analysis: null, view: null };

  it("writes the design, and the variant only when it is not the first", () => {
    expect(linkSearch("", state)).toBe("?design=dipoles.invvee");
    expect(linkSearch("", { ...state, variant: "long" })).toBe("?design=dipoles.invvee:long");
  });

  it("writes the view only beside an analysis, spaces as %20", () => {
    expect(linkSearch("", { ...state, view: "Smith" })).toBe("?design=dipoles.invvee");
    expect(linkSearch("", { ...state, analysis: "resonance vs angle", view: "Knobs" })).toBe(
      "?design=dipoles.invvee&analysis=resonance%20vs%20angle&view=Knobs",
    );
  });

  it("replaces the link's own parameters, drops run, and keeps any other", () => {
    expect(
      linkSearch("?x=1&design=beams.moxon&analysis=old&view=Rx&run=1", {
        ...state,
        analysis: "a+b",
      }),
    ).toBe("?x=1&design=dipoles.invvee&analysis=a%2Bb");
  });

  it("leaves a study's colon bare", () => {
    expect(linkSearch("", { ...state, analysis: "dipoles.apex_feed_on_invvee:feed spelling (E7)" })).toBe(
      "?design=dipoles.invvee&analysis=dipoles.apex_feed_on_invvee:feed%20spelling%20(E7)",
    );
  });

  it("round-trips through parseDeepLink", () => {
    const s = { design: "dipoles.invvee", variant: "long", analysis: "src.x:study (E7)", view: "Rx" };
    expect(parseDeepLink(linkSearch("", s))).toEqual({ ...s, run: false });
  });

  it("is a whole link at this page's address", () => {
    expect(
      linkHref(
        { origin: "https://antennaknobs.dev", pathname: "/app/", search: "?design=x.y", hash: "" },
        { ...state, analysis: "convergence", view: "Rx" },
      ),
    ).toBe("https://antennaknobs.dev/app/?design=dipoles.invvee&analysis=convergence&view=Rx");
  });
});
