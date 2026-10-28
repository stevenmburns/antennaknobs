// The live solve's band readings as Smith chart markers: each ticked band's Z
// from `band_zs`, at its place in the band list (its colour), at its feed and
// against its Z0 where a kept run's form gives them.
import { describe, it, expect } from "vitest";
import { liveBandReadings, nextBandMarks } from "../lib/optBands";

const zs = [
  { freq_mhz: 7.1, z0_ohms: 50, feeds: [[40, -5] as [number, number], [60, 8] as [number, number]] },
  { freq_mhz: 21.2, z0_ohms: 50, feeds: [null, [70, 1] as [number, number]] },
];

describe("liveBandReadings", () => {
  it("places each band by the list and reads feed 0 against the solve's Z0", () => {
    expect(liveBandReadings(zs, [7.1, 14.2, 21.2])).toEqual([
      { index: 0, freq_mhz: 7.1, z0_ohms: 50, z_re: 40, z_im: -5 },
      { index: 2, freq_mhz: 21.2, z0_ohms: 50, z_re: null, z_im: null },
    ]);
  });

  it("reads a kept form's feed and Z0, and drops a band the list no longer has", () => {
    const form = { bands: [{ freq: 21.2, feed: 1, z0: 75 }] };
    expect(liveBandReadings(zs, [21.2], form)).toEqual([
      { index: 0, freq_mhz: 21.2, z0_ohms: 75, z_re: 70, z_im: 1 },
    ]);
  });

  it("feeds the band markers, a null reading not drawn", () => {
    const marks = nextBandMarks(null, { bands: liveBandReadings(zs, [7.1, 21.2]) });
    expect(marks?.bands.map((b) => [b.freq_mhz, b.live, b.trail.length])).toEqual([
      [7.1, true, 1],
      [21.2, false, 0],
    ]);
  });
});
