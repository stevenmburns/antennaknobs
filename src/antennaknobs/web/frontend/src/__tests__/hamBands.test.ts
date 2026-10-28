// The SWR chart's ham band spans (Steve, 2026-10-28): every band the sweep
// overlaps, labelled with how much of it the curve keeps under the threshold.
// AC6LA had read the old full-height green columns (the runs under 2:1) as
// "the band"; vertical marks are now frequency only.
import { describe, it, expect } from "vitest";
import { hamBandLabel, hamBandMarks } from "../lib/sweepAxis";

const B12 = { label: "12m", lo: 24.89, hi: 24.99 };
const B10 = { label: "10m", lo: 28.0, hi: 29.7 };
const B40 = { label: "40m", lo: 7.0, hi: 7.3 };
// The fan dipole's runs under 2:1, 23-30 MHz (measured 2026-10-28).
const UNDER = [
  { lo: 24.4, hi: 25.65, openLo: false, openHi: false },
  { lo: 28.27, hi: 28.94, openLo: false, openHi: false },
];

describe("hamBandMarks", () => {
  it("keeps the bands the sweep overlaps, each with its share under the threshold", () => {
    const marks = hamBandMarks([B40, B12, B10], UNDER, 23, 30);
    expect(marks.map((m) => m.label)).toEqual(["12m", "10m"]);
    expect(marks[0].covered).toBeCloseTo(1, 6);
    expect(marks[1].covered).toBeCloseTo(0.67 / 1.7, 6);
    expect(marks.map(hamBandLabel)).toEqual(["12m all", "10m 39%"]);
  });

  it("names a band the sweep only partly covers, with no share", () => {
    const [m] = hamBandMarks([B10], UNDER, 28.5, 30);
    expect(m.covered).toBeNull();
    expect(hamBandLabel(m)).toBe("10m");
  });

  it("says none when the curve never gets under the threshold in the band", () => {
    const [m] = hamBandMarks([B10], [], 27, 30);
    expect(hamBandLabel(m)).toBe("10m none");
  });
});
