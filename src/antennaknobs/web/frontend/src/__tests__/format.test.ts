// Pins the small display-formatting free functions in App.tsx: mixHex (knob
// arc color blend), formatScalar (generic numeric readout), formatOhms and
// formatSwr (impedance/SWR readouts, including the open-circuit sentinel and
// the |Gamma| -> 1 asymptote).
import { describe, it, expect } from "vitest";
import { formatOhms, formatScalar, formatSwr } from "../lib/format";
import { mixHex } from "../lib/math";

describe("mixHex", () => {
  it("returns exactly a at t=0 and exactly b at t=1", () => {
    expect(mixHex("#000000", "#ffffff", 0)).toBe("rgb(0, 0, 0)");
    expect(mixHex("#000000", "#ffffff", 1)).toBe("rgb(255, 255, 255)");
  });

  it("rounds the midpoint blend", () => {
    expect(mixHex("#000000", "#ffffff", 0.5)).toBe("rgb(128, 128, 128)");
  });

  it("pins a non-trivial asymmetric blend", () => {
    expect(mixHex("#3a7bd5", "#ff5e3a", 0.25)).toBe("rgb(107, 116, 174)");
  });
});

describe("formatScalar", () => {
  it("formats a number to the given precision with the unit appended", () => {
    expect(formatScalar(3.14159, 2, "dB")).toBe("3.14dB");
    expect(formatScalar(3, 0, null)).toBe("3");
  });

  it('renders a non-number (e.g. missing result) as "—"', () => {
    expect(formatScalar("n/a", 2, "dB")).toBe("—");
    expect(formatScalar(null, 2, null)).toBe("—");
    expect(formatScalar(undefined, 2, null)).toBe("—");
  });

  it("still stringifies NaN, since typeof NaN === 'number'", () => {
    expect(formatScalar(NaN, 2, null)).toBe("NaN");
  });

  it("has no unit segment when unit is null", () => {
    expect(formatScalar(1.5, 1, null)).toBe("1.5");
  });
});

describe("formatOhms", () => {
  it("prints two decimal places with the ohm sign", () => {
    expect(formatOhms(36.5)).toBe("36.50 Ω");
    expect(formatOhms(0)).toBe("0.00 Ω");
  });

  it("clamps to the open-circuit sentinel at |v| >= 1e8, either sign", () => {
    expect(formatOhms(1e9)).toBe("∞ (open)");
    expect(formatOhms(-1e9)).toBe("∞ (open)");
    expect(formatOhms(1e8)).toBe("∞ (open)"); // boundary is inclusive
  });

  it("prints the raw value just under the boundary", () => {
    expect(formatOhms(99999999)).toBe("99999999.00 Ω");
  });
});

describe("formatSwr", () => {
  it("is 1.00 at a matched load", () => {
    expect(formatSwr(50, 0, 50)).toBe("1.00");
  });

  it('is "∞" at a dead short, where |Gamma| == 1', () => {
    expect(formatSwr(0, 0, 50)).toBe("∞");
  });

  it('is "∞" once |Gamma| >= 0.9999, short of exactly 1', () => {
    // R=1e9 -> |Gamma| = 0.9999999000000048, over the 0.9999 threshold but
    // not exactly 1 — pins that the cutoff is the >= 0.9999 guard, not a
    // literal-1 check.
    expect(formatSwr(1e9, 0, 50)).toBe("∞");
  });

  it("prints two decimals below SWR 99", () => {
    expect(formatSwr(100, 0, 50)).toBe("2.00");
    expect(formatSwr(2000, 0, 50)).toBe("40.00");
  });

  it("switches to zero decimals once SWR exceeds 99", () => {
    // R=5000/X=0/Z0=50 -> |Gamma| = 0.9801980198019802 -> SWR = 100 (>99).
    expect(formatSwr(5000, 0, 50)).toBe("100");
  });
});
