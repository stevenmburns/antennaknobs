// The combined Az + El plot (AK#1730): one radial scale over every drawn
// trace, and the elevation trace laid out by elevation angle (0° = the cut
// bearing's horizon on the right, 90° = zenith at the top), the same polar
// parameter the server's cuts use and the one-cut charts draw.
import { describe, it, expect } from "vitest";
import type { PatternCuts } from "../lib/api";
import { cutDbiTop, cutDbiToFrac } from "../lib/refine";
import {
  combinedDbiTop,
  combinedTraces,
  LIVE_ENTITY,
} from "../components/charts/combined";
import { polarPoint, sampleAngleRad, type PolarGeom } from "../components/charts/polar";

const FLOOR = -100;
const cuts = (azimuth: number[], elevation: number[], extra: Partial<PatternCuts> = {}): PatternCuts => ({
  az_elev_deg: 0,
  elev_az_deg: 0,
  n_dir: azimuth.length,
  floor_dbi: FLOOR,
  azimuth,
  elevation,
  diffraction: false,
  ...extra,
});
const flat = (n: number, v: number) => Array.from({ length: n }, () => v);

describe("combinedTraces", () => {
  it("draws both cuts per design, pins first so the live pair lands on top", () => {
    const traces = combinedTraces(
      [cuts(flat(8, 2), flat(8, 3)), cuts(flat(8, 1), flat(8, 0))],
      [{ id: "pin-a" }],
    );
    expect(traces.map((t) => [t.entity, t.cut, t.pinned])).toEqual([
      ["pin-a", "xy", true],
      ["pin-a", "yz", true],
      [LIVE_ENTITY, "xy", false],
      [LIVE_ENTITY, "yz", false],
    ]);
  });

  it("leaves out a cut with nothing above the floor", () => {
    const traces = combinedTraces([cuts(flat(8, 2), flat(8, FLOOR))], []);
    expect(traces.map((t) => t.cut)).toEqual(["xy"]);
  });
});

describe("the shared radial scale", () => {
  it("covers the higher cut's peak, whichever cut it is", () => {
    // Elevation peaks at +14 dBi, azimuth at +3: the rim must clear +14.
    const elevHigh = combinedTraces([cuts(flat(8, 3), [14, ...flat(7, 0)])], []);
    expect(combinedDbiTop(elevHigh)).toBe(15);
    const azHigh = combinedTraces([cuts([12.2, ...flat(7, 0)], flat(8, 3))], []);
    expect(combinedDbiTop(azHigh)).toBe(14);
  });

  it("covers a pin's peak too", () => {
    const traces = combinedTraces(
      [cuts(flat(8, 2), flat(8, 2)), cuts(flat(8, 1), [16.5, ...flat(7, 0)])],
      [{ id: "pin-a" }],
    );
    expect(combinedDbiTop(traces)).toBe(18);
    // Every trace fits under it.
    const frac = cutDbiToFrac(combinedDbiTop(traces));
    for (const t of traces) expect(frac(t.peakDbi)).toBeLessThan(1);
  });

  it("keeps the one-cut charts' default rim for a low-gain pair", () => {
    // The same rule the azimuth and elevation charts use (lib/refine.ts), so
    // a quiet antenna reads on the same rings in all three views.
    expect(combinedDbiTop(combinedTraces([cuts(flat(8, 2), flat(8, 5))], []))).toBe(
      cutDbiTop([5]),
    );
  });
});

describe("the elevation trace's angles", () => {
  const g: PolarGeom = { cx: 100, cy: 100, R: 80, dbiToFrac: cutDbiToFrac(10) };
  const at = (elevDeg: number) => polarPoint(g, (elevDeg * Math.PI) / 180, 10);

  it("puts 0° on the right, 90° at the top and 180° on the left", () => {
    const right = at(0);
    expect(right.x).toBeCloseTo(180);
    expect(right.y).toBeCloseTo(100);
    const top = at(90);
    expect(top.x).toBeCloseTo(100);
    expect(top.y).toBeCloseTo(20); // canvas y runs down: the top is SMALLER y
    const left = at(180);
    expect(left.x).toBeCloseTo(20);
    expect(left.y).toBeCloseTo(100);
  });

  it("reads each sample's angle from the trace: uniform, or refined", () => {
    // A uniform 8-sample elevation cut: sample 2 is 90°, the zenith.
    const uniform = combinedTraces([cuts(flat(8, 0), [0, 0, 9, 0, 0, 0, 0, 0])], []);
    const el = uniform.find((t) => t.cut === "yz")!;
    expect(el.anglesDeg).toBeUndefined();
    const zenith = polarPoint(g, sampleAngleRad(2, 8, el.anglesDeg), el.dbi[2]);
    expect(zenith.x).toBeCloseTo(100);
    expect(zenith.y).toBeLessThan(100);
    // A refined cut carries explicit angles (issue #744): a sample at 30°
    // lands up and to the right, wherever its index is.
    const refined = combinedTraces(
      [cuts(flat(4, 0), [0, 5, 0, 0], { elev_angles_deg: [0, 30, 180, 270] })],
      [],
    ).find((t) => t.cut === "yz")!;
    const p = polarPoint(g, sampleAngleRad(1, 4, refined.anglesDeg), refined.dbi[1]);
    expect(p.x).toBeGreaterThan(100);
    expect(p.y).toBeLessThan(100);
    expect(Math.atan2(100 - p.y, p.x - 100) * (180 / Math.PI)).toBeCloseTo(30);
  });
});
