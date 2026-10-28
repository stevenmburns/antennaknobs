// Every lobe of a pattern's maximum, one rule for both peak readouts
// (AK#2094). The cases are the ones measured on the catalog's vertical and on
// SP3L's turnstile: one lobe, twins 180° apart, three lobes 120° apart, and a
// round ring that has no peak bearing at all.
import { describe, it, expect } from "vitest";
import {
  formatPeakAngles,
  lobeCentresDeg,
  maxAzimuthsDeg,
  maxBearingDeg,
} from "../lib/peakLobes";
import type { PatternMetrics } from "../components/charts/types";

// A 360-sample ring, 1° apart, from a function of the azimuth.
const ring = (f: (az: number) => number) => {
  const az = Array.from({ length: 360 }, (_, i) => i);
  return { az, dbi: az.map(f) };
};
const rad = (deg: number) => (deg * Math.PI) / 180;

describe("lobeCentresDeg on an azimuth ring", () => {
  it("finds one lobe at its peak", () => {
    const { az, dbi } = ring((a) => 5 * Math.cos(rad(a - 40)));
    expect(lobeCentresDeg(az, dbi, true)).toEqual([40]);
  });

  it("lists twin lobes 180° apart, as a turnstile has", () => {
    const { az, dbi } = ring((a) => 0.5 * Math.cos(2 * rad(a - 7)));
    expect(lobeCentresDeg(az, dbi, true)).toEqual([7, 187]);
  });

  it("lists three lobes 120° apart, as a vertical on three radials has", () => {
    const { az, dbi } = ring((a) => 0.25 * Math.cos(3 * rad(a - 60)));
    expect(lobeCentresDeg(az, dbi, true)).toEqual([60, 180, 300]);
  });

  it("puts a lobe that runs across 0° at its centre, not split in two", () => {
    const { az, dbi } = ring((a) => (a >= 356 || a <= 4 ? 3 : 0));
    expect(lobeCentresDeg(az, dbi, true)).toEqual([0]);
  });

  it("reads a flat top at its centre, not its first sample", () => {
    const { az, dbi } = ring((a) => (a >= 4 && a <= 10 ? 4.566 : 4.0));
    expect(lobeCentresDeg(az, dbi, true)).toEqual([7]);
  });

  it("has no lobe on a round ring: every bearing is the peak's", () => {
    const { az, dbi } = ring((a) => 0.4 + 0.004 * Math.cos(rad(a)));
    expect(lobeCentresDeg(az, dbi, true)).toEqual([]);
  });

  it("counts a closed ring's repeated 0°/360° once", () => {
    const az = Array.from({ length: 361 }, (_, i) => i);
    const dbi = az.map((a) => 0.5 * Math.cos(2 * rad(a)));
    expect(lobeCentresDeg(az, dbi, true)).toEqual([0, 180]);
  });
});

describe("lobeCentresDeg on an unwrapped cut", () => {
  it("keeps a flat trace as one run, at its centre", () => {
    expect(lobeCentresDeg([0, 10, 20], [1, 1, 1], false)).toEqual([10]);
  });
});

describe("formatPeakAngles", () => {
  it("reads one, several, many and none", () => {
    expect(formatPeakAngles([7.03], "az")).toBe("az 7°");
    expect(formatPeakAngles([7.03, 187.03], "az")).toBe("az 7° · 187°");
    expect(formatPeakAngles([0, 72, 144, 216, 288], "az")).toBe(
      "az 0° · 72° · 144° · 216° · +1",
    );
    expect(formatPeakAngles([], "az")).toBe("all az");
    expect(formatPeakAngles([359.7], "az")).toBe("az 0°");
  });
});

describe("the 3-D max's bearings", () => {
  const base: PatternMetrics = {
    peak_gain_dbi: 4.6,
    takeoff_deg: 31.7,
    azimuth_deg: 187.2,
    front_to_back_db: 0,
    az_beamwidth_deg: 360,
    el_beamwidth_deg: 60,
  };

  it("reads the server's lobes, else the one bearing an older server sends", () => {
    expect(maxAzimuthsDeg({ ...base, azimuth_lobes_deg: [7.0, 187.0] })).toEqual([7, 187]);
    expect(maxAzimuthsDeg(base)).toEqual([187.2]);
  });

  it("aims at the first lobe, and not at all when the peak is round", () => {
    expect(maxBearingDeg({ ...base, azimuth_lobes_deg: [7.0, 187.0] })).toBe(7);
    expect(maxBearingDeg({ ...base, azimuth_lobes_deg: [] })).toBeNull();
    expect(maxBearingDeg(base)).toBe(187);
  });
});
