// AK#2035: the solver settings' "wire radius" field says what it does on the
// design. A 5-inch dipole opened from .ez showed a bare 0.0005 there, which
// read as the solver using the wrong wire.
import { describe, it, expect } from "vitest";
import { DEFAULT_WIRE_RADIUS, wireRadiusNote } from "../lib/backends";

describe("wireRadiusNote", () => {
  it("says nothing when the design names no radius (the field is the radius)", () => {
    expect(wireRadiusNote(null, DEFAULT_WIRE_RADIUS)).toBeNull();
    expect(wireRadiusNote(undefined, 0.001)).toBeNull();
  });

  it("names the file's radius and says the field moves nothing", () => {
    const note = wireRadiusNote(
      { min: 0.0635, max: 0.0635, every_wire: true },
      DEFAULT_WIRE_RADIUS,
    );
    expect(note).toContain("0.0635 m");
    expect(note).toContain("changes nothing");
  });

  it("gives a span when the design's wires differ", () => {
    const note = wireRadiusNote(
      { min: 0.001, max: 0.0635, every_wire: true },
      0.002,
    );
    expect(note).toContain("0.001–0.0635 m");
  });

  it("calls the untouched field auto when the design sets a default radius", () => {
    const radii = { min: 0.000814, max: 0.000814, every_wire: false };
    expect(wireRadiusNote(radii, DEFAULT_WIRE_RADIUS)).toMatch(
      /^0\.0005 means auto.*0\.000814 m/,
    );
    expect(wireRadiusNote(radii, 0.002)).toMatch(
      /^Replaces the design's radius/,
    );
  });
});
