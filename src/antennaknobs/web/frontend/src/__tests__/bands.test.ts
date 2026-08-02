// Pins the pure band-window logic in src/lib/bands.ts (issue #642 PR 5b-1),
// extracted verbatim from DesignSession's inline `freqWindowCeiling` const
// and `bandContaining` closure.
import { describe, it, expect } from "vitest";
import { bandContaining, freqWindowCeiling } from "../lib/bands";
import type { BandSpec } from "../lib/params";

const BAND_2M: BandSpec = { key: "2m", label: "2 m", freq_mhz: 146, min_mhz: 144, max_mhz: 148 };
const BAND_10M: BandSpec = { key: "10m", label: "10 m", freq_mhz: 28.5, min_mhz: 28.0, max_mhz: 29.7 };
const BAND_20M: BandSpec = { key: "20m", label: "20 m", freq_mhz: 14.15, min_mhz: 14.0, max_mhz: 14.35 };

describe("freqWindowCeiling", () => {
  it("floors at 60 MHz for a bandless design", () => {
    expect(freqWindowCeiling([])).toBe(60);
  });

  it("floors at 60 MHz for an HF-only design (1.25x max stays under the floor)", () => {
    // 10 m's max_mhz * 1.25 = 37.125, well under the 60 MHz floor.
    expect(freqWindowCeiling([BAND_10M])).toBe(60);
  });

  it("uses 1.25x the highest band's max_mhz on VHF (the #497 inverted-VFO regression)", () => {
    // Before the fix this was hardcoded to 60, which INVERTED the VFO
    // window for a 146 MHz anchor (min 116.8 > max 60).
    expect(freqWindowCeiling([BAND_2M])).toBeCloseTo(148 * 1.25, 9);
  });

  it("takes the max across all bands, not just the last one", () => {
    expect(freqWindowCeiling([BAND_2M, BAND_10M, BAND_20M])).toBeCloseTo(148 * 1.25, 9);
    expect(freqWindowCeiling([BAND_10M, BAND_2M, BAND_20M])).toBeCloseTo(148 * 1.25, 9);
  });
});

describe("bandContaining", () => {
  const bands = [BAND_20M, BAND_10M];

  it("finds the band containing an in-band frequency", () => {
    expect(bandContaining(bands, 14.2)).toBe("20m");
    expect(bandContaining(bands, 28.4)).toBe("10m");
  });

  it("includes both boundaries (min_mhz and max_mhz are inclusive)", () => {
    expect(bandContaining(bands, 14.0)).toBe("20m");
    expect(bandContaining(bands, 14.35)).toBe("20m");
  });

  it("returns null just outside a boundary", () => {
    expect(bandContaining(bands, 13.999)).toBeNull();
    expect(bandContaining(bands, 14.351)).toBeNull();
  });

  it("returns null for a frequency outside every band", () => {
    expect(bandContaining(bands, 50.0)).toBeNull();
  });

  it("returns null for an empty band list", () => {
    expect(bandContaining([], 14.2)).toBeNull();
  });
});
