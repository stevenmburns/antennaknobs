// Pinned sweeps' rules (AK#1757 item 1, lib/sweepPins.ts): the snapshot,
// one pin per curve, the colour slots, where a pin can draw and why not,
// the Z0 rule and the CSV.
//
// Mutation notes (run by hand, 2026-09-30; each reverted after):
//   - placePin matching a knob pin by kind alone (the name test dropped):
//     "a knob pin draws only on a chart sweeping the same knob" fails;
//   - nextColorSlots taking `pins.length % 8` instead of the smallest free
//     slot: "a freed slot is reused" fails;
//   - pinCsv's SWR at 50 Ω whatever the pin's Z0: "the CSV" fails.
import { describe, expect, it } from "vitest";
import {
  type ChartX,
  changedKnobs,
  DENSITY_X,
  FREQUENCY_X,
  knobX,
  nextColorSlots,
  pinCsv,
  pinLabel,
  pinsFromCurves,
  placePin,
  type SweepPin,
  swrAt,
  valueAt,
  withPins,
  z0Note,
} from "../lib/sweepPins";

const HEIGHT = knobX("height", "Height", "m");

const curve = (over: Partial<Parameters<typeof pinsFromCurves>[0][number]> = {}) => ({
  xs: [14.1, 14.0, 14.2],
  zRe: [51, 50, 52],
  zIm: [1, 0, 2],
  x: FREQUENCY_X,
  label: "invvee:dipole · NEC-5 · Sommerfeld · 13/0.005 · height 9.5",
  cell: "",
  design: "invvee",
  ...over,
});

let seq = 0;
const mint = () => `p${seq++}`;

describe("the snapshot", () => {
  it("holds Z at each x, sorted, the Z0 it was taken at, and its context", () => {
    const [p] = pinsFromCurves([curve()], 75);
    expect(p.x).toEqual(FREQUENCY_X);
    expect(p.xs).toEqual([14.0, 14.1, 14.2]);
    expect(p.zRe).toEqual([50, 51, 52]);
    expect(p.zIm).toEqual([0, 1, 2]);
    expect(p.z0).toBe(75);
    expect(p.label).toBe("invvee:dipole · NEC-5 · Sommerfeld · 13/0.005 · height 9.5");
    expect(p.design).toBe("invvee");
  });

  it("is a copy: a later change to the live curve's arrays does not move it", () => {
    const c = curve();
    const [p] = pinsFromCurves([c], 50);
    (c.zRe as number[])[0] = 999;
    expect(p.zRe).toEqual([50, 51, 52]);
  });

  it("makes one pin per curve of a crossed chart, each labelled by its cell; an empty curve pins nothing", () => {
    const pins = pinsFromCurves(
      [
        curve({ cell: "A: NEC-5, 1: free space", label: "d · NEC-5 · free space" }),
        curve({ cell: "B: B-spline d=2, 1: free space", label: "d · B-spline d=2 · free space" }),
        curve({ xs: [], zRe: [], zIm: [], cell: "C" }),
      ],
      50,
    );
    expect(pins.map((p) => p.cell)).toEqual(["A: NEC-5, 1: free space", "B: B-spline d=2, 1: free space"]);
  });
});

describe("colour slots", () => {
  const withSlots = (slots: number[]) => slots.map((colorIdx) => ({ colorIdx }));

  it("take the smallest free slot of 8, one per new pin", () => {
    expect(nextColorSlots([], 3)).toEqual([0, 1, 2]);
    expect(nextColorSlots(withSlots([0, 2]), 2)).toEqual([1, 3]);
  });

  it("a freed slot is reused, and deleting a pin never moves another's colour", () => {
    let pins: SweepPin[] = withPins([], pinsFromCurves([curve(), curve(), curve()], 50), mint);
    expect(pins.map((p) => p.colorIdx)).toEqual([0, 1, 2]);
    pins = pins.filter((p) => p.colorIdx !== 1);
    expect(pins.map((p) => p.colorIdx)).toEqual([0, 2]);
    pins = withPins(pins, pinsFromCurves([curve()], 50), mint);
    expect(pins.map((p) => p.colorIdx)).toEqual([0, 2, 1]);
    expect(pins.every((p) => p.enabled)).toBe(true);
  });

  it("wrap past the palette of 8 as the pattern pins do", () => {
    const full = withSlots([0, 1, 2, 3, 4, 5, 6, 7]);
    expect(nextColorSlots(full, 2)).toEqual([0, 1]);
  });
});

describe("where a pin draws", () => {
  const freqPin = { x: FREQUENCY_X, xs: [7.0, 7.1, 7.2, 7.3] };
  const heightPin = { x: HEIGHT, xs: [8, 9, 10] };
  const densityPin = { x: DENSITY_X, xs: [8, 12, 17] };
  const freqChart: ChartX = { x: FREQUENCY_X, lo: 7.15, hi: 7.5 };

  it("a frequency pin draws on a frequency chart over the overlap only", () => {
    expect(placePin(freqPin, freqChart)).toEqual({ drawable: true, idx: [2, 3] });
  });

  it("a frequency pin with no overlap is greyed with both ranges", () => {
    expect(placePin(freqPin, { x: FREQUENCY_X, lo: 14, hi: 14.35 })).toEqual({
      drawable: false,
      reason: "sweeps 7–7.3 MHz; this chart sweeps 14–14.35 MHz",
    });
  });

  it("a knob pin draws only on a chart sweeping the same knob, by name, whatever the design", () => {
    // Another design's chart sweeping `height`: the name is what matches.
    expect(placePin(heightPin, { x: knobX("height", "Mast height", "ft"), lo: 5, hi: 20 })).toEqual({
      drawable: true,
      idx: [0, 1, 2],
    });
    expect(placePin(heightPin, { x: knobX("gap", "Gap", null), lo: 5, hi: 20 })).toEqual({
      drawable: false,
      reason: "sweeps height; this chart sweeps gap",
    });
  });

  it("kinds never cross: the reason names both", () => {
    expect(placePin(heightPin, freqChart)).toEqual({
      drawable: false,
      reason: "sweeps height; this chart sweeps frequency",
    });
    expect(placePin(freqPin, { x: HEIGHT, lo: 0, hi: 20 })).toEqual({
      drawable: false,
      reason: "sweeps frequency; this chart sweeps height",
    });
    expect(placePin(densityPin, { x: DENSITY_X, lo: 8, hi: 68 })).toEqual({ drawable: true, idx: [0, 1, 2] });
    expect(placePin(densityPin, { x: HEIGHT, lo: 8, hi: 68 })).toEqual({
      drawable: false,
      reason: "sweeps density; this chart sweeps height",
    });
    // A knob named n_per_wire IS density.
    expect(knobX("n_per_wire", "N", null)).toEqual(DENSITY_X);
  });

  it("the Table draws no pin, and says so", () => {
    expect(placePin(freqPin, null)).toEqual({
      drawable: false,
      reason: "the Table lists this chart's own curves",
    });
  });
});

describe("Z0 and values", () => {
  it("a pin's SWR is at its own Z0; the label notes a Z0 that is not the chart's", () => {
    // 50 Ω: a perfect match at its own reference, 1.5:1 at 75 Ω.
    expect(swrAt(50, 0, 50)).toBeCloseTo(1, 9);
    expect(swrAt(50, 0, 75)).toBeCloseTo(1.5, 9);
    expect(z0Note(50, 75)).toBe("Z0 50 Ω");
    expect(z0Note(50, 50)).toBeNull();
  });

  it("reads a value between samples linearly, and nothing outside them", () => {
    expect(valueAt([1, 2, 4], [10, 20, 40], 3)).toBe(30);
    expect(valueAt([1, 2, 4], [10, 20, 40], 1)).toBe(10);
    expect(valueAt([1, 2, 4], [10, 20, 40], 4)).toBe(40);
    expect(valueAt([1, 2, 4], [10, 20, 40], 0.5)).toBeNull();
    expect(valueAt([1, 2, 4], [10, 20, 40], 5)).toBeNull();
  });
});

describe("the label", () => {
  it("names the design and variant, engine, ground, the changed knobs and the plane", () => {
    expect(
      pinLabel({
        design: "invvee",
        variant: "dipole",
        engine: "NEC-5",
        ground: "Sommerfeld 13/0.005",
        knobs: [["height", 9.5]],
        plane: null,
      }),
    ).toBe("invvee:dipole · NEC-5 · Sommerfeld 13/0.005 · height 9.5");
    expect(
      pinLabel({ design: "moxon", variant: "default", engine: "PyNEC", ground: "free space", knobs: [], plane: "feed" }),
    ).toBe("moxon · PyNEC · free space · plane feed");
  });

  it("changed knobs leave out the swept one, the defaults and group knobs", () => {
    expect(
      changedKnobs(
        { height: 9.5, gap: 0.25, length_factor: 1.02, bands: [{}], on: true },
        { height: 10, gap: 0.25, length_factor: 1, bands: [], on: true },
        "length_factor",
      ),
    ).toEqual([["height", 9.5]]);
  });
});

describe("the CSV", () => {
  it("is x, R, X and the SWR at the pin's own Z0, with its context", () => {
    const [p] = pinsFromCurves([curve({ xs: [14.0, 14.1], zRe: [50, 100], zIm: [0, 0] })], 50);
    expect(pinCsv(p).split("\n")).toEqual([
      "# invvee:dipole · NEC-5 · Sommerfeld · 13/0.005 · height 9.5",
      "# Z0 50 ohm",
      "freq_mhz,r_ohm,x_ohm,swr_z0_50",
      "14,50,0,1",
      "14.1,100,0,2",
      "",
    ]);
    const [k] = pinsFromCurves([curve({ x: HEIGHT, xs: [9], zRe: [50], zIm: [0], cell: "A, 1" })], 75);
    expect(pinCsv(k).split("\n").slice(0, 4)).toEqual([
      "# invvee:dipole · NEC-5 · Sommerfeld · 13/0.005 · height 9.5 (A, 1)",
      "# Z0 75 ohm",
      "height,r_ohm,x_ohm,swr_z0_75",
      "9,50,0,1.5",
    ]);
  });
});
