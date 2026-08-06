// The no-rebuild escape hatches for adaptive resolution's constants. Not
// settings (the gear menu deliberately carries only the on/off toggle) —
// just the guarantee that a difficult design can nudge the sampling
// machinery from the devtools console and a reload.
import { describe, it, expect, afterEach } from "vitest";
import { tunedFloat, tunedInt } from "../lib/tuning";

afterEach(() => localStorage.clear());

describe("tuning overrides", () => {
  it("falls back when nothing is set", () => {
    expect(tunedInt("t.i", 17, 101)).toBe(17);
    expect(tunedFloat("t.f", 0.003)).toBe(0.003);
  });

  it("reads a valid override, flooring ints and clamping to the cap", () => {
    localStorage.setItem("t.i", "31.7");
    expect(tunedInt("t.i", 17, 101)).toBe(31);
    localStorage.setItem("t.i", "9999");
    expect(tunedInt("t.i", 17, 101)).toBe(101); // the server caps stay safe
    localStorage.setItem("t.f", "0.01");
    expect(tunedFloat("t.f", 0.003)).toBe(0.01);
  });

  it("garbage and non-positive values fall back rather than half-apply", () => {
    for (const bad of ["banana", "", "0", "-4", "NaN", "Infinity"]) {
      localStorage.setItem("t.i", bad);
      expect(tunedInt("t.i", 17, 101)).toBe(17);
    }
    for (const bad of ["banana", "0", "-0.5", "Infinity"]) {
      localStorage.setItem("t.f", bad);
      expect(tunedFloat("t.f", 0.003)).toBe(0.003);
    }
  });
});
