// Pins reflectionCoefficient (Gamma from R/X/Z0) and the |Γ| / VSWR / S11
// helpers, the numeric cores behind the SWR/Smith-chart readouts. Z∞'s
// estimator is pinned in zinf.test.ts (AK#1781).
import { describe, it, expect } from "vitest";
import { reflectionCoefficient } from "../lib/format";
import {
  gammaDbFromMag,
  gammaMagFromZ,
  S11_DB_FLOOR,
  VSWR_CEILING,
  vswrFromGammaMag,
} from "../lib/math";

describe("reflectionCoefficient", () => {
  it("is zero at a matched load (Z == Z0)", () => {
    const { gRe, gIm, gMag } = reflectionCoefficient(50, 0, 50);
    expect(gRe).toBeCloseTo(0, 12);
    expect(gIm).toBeCloseTo(0, 12);
    expect(gMag).toBeCloseTo(0, 12);
  });

  it("is a pure real -1 at a dead short (Z == 0)", () => {
    const { gRe, gIm, gMag } = reflectionCoefficient(0, 0, 50);
    expect(gRe).toBeCloseTo(-1, 12);
    expect(gIm).toBeCloseTo(0, 12);
    expect(gMag).toBeCloseTo(1, 12);
  });

  it("pins a reactive-load value (R == X == Z0)", () => {
    const { gRe, gIm, gMag } = reflectionCoefficient(50, 50, 50);
    expect(gRe).toBeCloseTo(0.2, 12);
    expect(gIm).toBeCloseTo(0.4, 12);
    expect(gMag).toBeCloseTo(0.447213595499958, 12);
  });
});

// --- gammaMagFromZ / vswrFromGammaMag ---------------------------------------
// Closed-form oracle values for the gamma/VSWR-vs-frequency sweep charts
// (issue #700 unit 5). gammaMagFromZ is a wrapper over reflectionCoefficient,
// but pinned independently here — a caller that swapped the gamma/VSWR
// conversion (e.g. plotting VSWR numbers under the gamma label) must fail
// against these, not just against reflectionCoefficient's own suite.
describe("gammaMagFromZ", () => {
  it("is zero at a matched load", () => {
    expect(gammaMagFromZ(50, 0, 50)).toBeCloseTo(0, 12);
  });

  it("is 1/3 for a 2:1 real mismatch, either direction", () => {
    expect(gammaMagFromZ(100, 0, 50)).toBeCloseTo(1 / 3, 12);
    expect(gammaMagFromZ(25, 0, 50)).toBeCloseTo(1 / 3, 12);
  });

  // R == X == Z0: a real-part-only (or naive-magnitude) shortcut would read
  // this as gRe alone (0.2) — the true value needs the reactive component
  // folded in via Math.hypot, which is what distinguishes a complex |·|
  // from real-part arithmetic.
  it("is 1/sqrt(5) for a reactive load, not the real-part-only value", () => {
    const g = gammaMagFromZ(50, 50, 50);
    expect(g).toBeCloseTo(1 / Math.sqrt(5), 12);
    expect(g).not.toBeCloseTo(0.2, 3);
  });

  it("is 1 at a dead short or dead open", () => {
    expect(gammaMagFromZ(0, 0, 50)).toBeCloseTo(1, 12);
  });
});

describe("vswrFromGammaMag", () => {
  it("is 1 (perfectly matched) at |Γ| = 0", () => {
    expect(vswrFromGammaMag(0)).toBeCloseTo(1, 12);
  });

  it("is 2 at |Γ| = 1/3 (the 2:1 real-mismatch oracle pair)", () => {
    expect(vswrFromGammaMag(1 / 3)).toBeCloseTo(2, 12);
  });

  it("agrees with the gammaMagFromZ oracle pairs end to end", () => {
    expect(vswrFromGammaMag(gammaMagFromZ(50, 0, 50))).toBeCloseTo(1, 12);
    expect(vswrFromGammaMag(gammaMagFromZ(100, 0, 50))).toBeCloseTo(2, 12);
    expect(vswrFromGammaMag(gammaMagFromZ(25, 0, 50))).toBeCloseTo(2, 12);
  });

  it("clamps to the finite ceiling at and beyond |Γ| = 1", () => {
    expect(vswrFromGammaMag(1)).toBe(VSWR_CEILING);
    expect(vswrFromGammaMag(1.5)).toBe(VSWR_CEILING);
  });

  it("stays under the ceiling and monotonic below the point it clamps", () => {
    // (1+0.98)/(1-0.98) = 99 exactly, so 0.9 stays comfortably under the
    // ceiling while still exercising the un-clamped branch of the formula.
    const v = vswrFromGammaMag(0.9);
    expect(v).toBeLessThan(VSWR_CEILING);
    expect(v).toBeGreaterThan(vswrFromGammaMag(0.5));
  });
});

// S11 log-magnitude — the negative-dB VNA convention the gamma sweep view
// plots (0 dB = total reflection, dips are good). Pinned against closed
// forms so a sign flip (positive "return loss") or a base-10/ratio-20 slip
// fails here, not just in a chart eyeball.
describe("gammaDbFromMag", () => {
  it("is 0 dB at total reflection (dead short/open)", () => {
    expect(gammaDbFromMag(1)).toBeCloseTo(0, 12);
  });

  it("is 20·log10 of the magnitude, negative for any partial reflection", () => {
    expect(gammaDbFromMag(1 / 3)).toBeCloseTo(20 * Math.log10(1 / 3), 12);
    expect(gammaDbFromMag(1 / 3)).toBeCloseTo(-9.54242509439325, 12);
    expect(gammaDbFromMag(0.1)).toBeCloseTo(-20, 12);
  });

  it("floors a perfect (or numerically zero) match instead of -Infinity", () => {
    expect(gammaDbFromMag(0)).toBe(S11_DB_FLOOR);
    expect(gammaDbFromMag(1e-9)).toBe(S11_DB_FLOOR);
    expect(Number.isFinite(gammaDbFromMag(0))).toBe(true);
  });

  it("agrees with the gammaMagFromZ oracle pairs end to end", () => {
    expect(gammaDbFromMag(gammaMagFromZ(50, 0, 50))).toBe(S11_DB_FLOOR);
    expect(gammaDbFromMag(gammaMagFromZ(100, 0, 50))).toBeCloseTo(-9.5424, 4);
    expect(gammaDbFromMag(gammaMagFromZ(25, 0, 50))).toBeCloseTo(-9.5424, 4);
  });
});
