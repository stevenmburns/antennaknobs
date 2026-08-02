// Pins the pure ground-model derivations in src/lib/ground.ts (issue #642
// PR 5b-1), extracted verbatim from DesignSession's inline `groundModel` /
// `groundSummary` consts.
import { describe, it, expect } from "vitest";
import type { Backend } from "../lib/backends";
import { groundSummaryLabel, resolveGroundModel } from "../lib/ground";

// Every Backend variant today supports ground/terrain (see
// backendSupportsGround); the "unsupported" branches only matter for a
// hypothetical future backend, so we exercise them with a cast past the
// closed union — exactly the case the code's own comments call out.
const UNSUPPORTED = "future-backend" as Backend;

describe("resolveGroundModel", () => {
  it("is 'pec' for groundType 'pec' regardless of backend", () => {
    expect(resolveGroundModel("pec", "bspline", "fast")).toBe("pec");
    expect(resolveGroundModel("pec", UNSUPPORTED, "sommerfeld")).toBe("pec");
  });

  it("is 'terrain' for groundType 'terrain' on a terrain-capable backend", () => {
    expect(resolveGroundModel("terrain", "pynec", "fast")).toBe("terrain");
    expect(resolveGroundModel("terrain", "sinusoidal-galerkin", "fast")).toBe("terrain");
  });

  it("degrades 'terrain' to 'fast' on a backend without terrain (and ground) support", () => {
    expect(resolveGroundModel("terrain", UNSUPPORTED, "sommerfeld")).toBe("fast");
  });

  it("mirrors finiteGroundMethod for groundType 'finite' on a ground-capable backend", () => {
    expect(resolveGroundModel("finite", "bspline", "fast")).toBe("fast");
    expect(resolveGroundModel("finite", "bspline", "sommerfeld")).toBe("sommerfeld");
  });

  it("falls back to 'fast' for groundType 'finite' on a backend without ground support", () => {
    expect(resolveGroundModel("finite", UNSUPPORTED, "sommerfeld")).toBe("fast");
  });
});

describe("groundSummaryLabel", () => {
  it("is 'free space' when ground is disabled, regardless of model", () => {
    expect(groundSummaryLabel(false, "bspline", "pec", "levee")).toBe("free space");
  });

  it("is 'free space' when the backend doesn't support ground even if enabled", () => {
    expect(groundSummaryLabel(true, UNSUPPORTED, "fast", "levee")).toBe("free space");
  });

  it("labels 'PEC ground'", () => {
    expect(groundSummaryLabel(true, "bspline", "pec", "levee")).toBe("PEC ground");
  });

  it("labels 'terrain (<preset>)'", () => {
    expect(groundSummaryLabel(true, "bspline", "terrain", "cliff")).toBe("terrain (cliff)");
  });

  it("labels 'reflection-coef ground' for the fast finite method", () => {
    expect(groundSummaryLabel(true, "bspline", "fast", "levee")).toBe("reflection-coef ground");
  });

  it("labels 'Sommerfeld ground' for the sommerfeld finite method", () => {
    expect(groundSummaryLabel(true, "bspline", "sommerfeld", "levee")).toBe("Sommerfeld ground");
  });
});
