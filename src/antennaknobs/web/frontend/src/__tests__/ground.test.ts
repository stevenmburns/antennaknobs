// Pins the pure ground-model derivations in src/lib/ground.ts (issue #642
// PR 5b-1), extracted verbatim from DesignSession's inline `groundModel` /
// `groundSummary` consts.
import { describe, it, expect } from "vitest";
import { groundSummaryLabel, resolveGroundModel } from "../lib/ground";
import { backendEntry, entry } from "./backendFixtures";

// Every backend the server registers today supports ground/terrain, so the
// "unsupported" branches are driven by a roster fixture carrying
// supports_ground: false (issue #628) — real wire data now, reachable without
// casting past a closed union.
const UNSUPPORTED = backendEntry({
  name: "future-solver",
  supports_ground: false,
});

describe("resolveGroundModel", () => {
  it("is 'pec' for groundType 'pec' regardless of backend", () => {
    expect(resolveGroundModel("pec", entry("bspline"), "fast")).toBe("pec");
    expect(resolveGroundModel("pec", UNSUPPORTED, "sommerfeld")).toBe("pec");
  });

  it("is 'terrain' for groundType 'terrain' on a terrain-capable backend", () => {
    expect(resolveGroundModel("terrain", entry("pynec"), "fast")).toBe("terrain");
    expect(resolveGroundModel("terrain", entry("sinusoidal-galerkin"), "fast")).toBe("terrain");
  });

  it("degrades 'terrain' to 'fast' on a backend without terrain (and ground) support", () => {
    expect(resolveGroundModel("terrain", UNSUPPORTED, "sommerfeld")).toBe("fast");
  });

  it("mirrors finiteGroundMethod for groundType 'finite' on a ground-capable backend", () => {
    expect(resolveGroundModel("finite", entry("bspline"), "fast")).toBe("fast");
    expect(resolveGroundModel("finite", entry("bspline"), "sommerfeld")).toBe("sommerfeld");
  });

  it("falls back to 'fast' for groundType 'finite' on a backend without ground support", () => {
    expect(resolveGroundModel("finite", UNSUPPORTED, "sommerfeld")).toBe("fast");
  });
});

describe("groundSummaryLabel", () => {
  it("is 'free space' when ground is disabled, regardless of model", () => {
    expect(groundSummaryLabel(false, entry("bspline"), "pec", "levee")).toBe("free space");
  });

  it("is 'free space' when the backend doesn't support ground even if enabled", () => {
    expect(groundSummaryLabel(true, UNSUPPORTED, "fast", "levee")).toBe("free space");
  });

  it("labels 'PEC ground'", () => {
    expect(groundSummaryLabel(true, entry("bspline"), "pec", "levee")).toBe("PEC ground");
  });

  it("labels 'terrain (<preset>)'", () => {
    expect(groundSummaryLabel(true, entry("bspline"), "terrain", "cliff")).toBe("terrain (cliff)");
  });

  it("labels 'reflection-coef ground' for the fast finite method", () => {
    expect(groundSummaryLabel(true, entry("bspline"), "fast", "levee")).toBe("reflection-coef ground");
  });

  it("labels 'Sommerfeld ground' for the sommerfeld finite method", () => {
    expect(groundSummaryLabel(true, entry("bspline"), "sommerfeld", "levee")).toBe("Sommerfeld ground");
  });
});
