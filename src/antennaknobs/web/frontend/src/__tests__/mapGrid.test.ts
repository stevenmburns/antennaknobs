// The map's colours, contours and best node (lib/mapGrid.ts) against the
// CLI: dipoles.invvee's tuning map as `antennaknobs analyze` solves it, with
// contourpy's vertices on it (scripts/map_chart_fixture.py writes the
// fixture; tests/test_map_chart_fixture.py keeps it honest).
//
// The gate (docs/design/sweep-framework-map.md, unit 2): every contour
// vertex within 1e-9 of the axis span of contourpy's, both ways.
import { describe, expect, it } from "vitest";
import fixture from "./fixtures/invveeTuningMap.json";
import {
  bestNode,
  bestNodeLine,
  cellEdges,
  colourValue,
  contourField,
  contourReached,
  contourSegments,
  emptyGrid,
  formatG,
  gammaOf,
  landed,
  type MapGrid,
  mapContourLevels,
  mapContours,
  nodeAt,
  swrGamma,
  viridisR,
} from "../lib/mapGrid";

type Contour = {
  quantity: "X" | "R" | "SWR";
  level: number;
  at: number;
  reached: boolean;
  lines: number[][][];
};
const FX = fixture as unknown as {
  z0: number;
  x: { param: string; values: number[] };
  y: { param: string; values: number[] };
  re: number[][];
  im: number[][];
  refs: { r: number[]; x: number[]; swr: number };
  contours: Contour[];
  best: { i: number; j: number; line: string };
};
const GRID: MapGrid = { xs: FX.x.values, ys: FX.y.values, re: FX.re, im: FX.im };
const SPAN_X = Math.max(...GRID.xs) - Math.min(...GRID.xs);
const SPAN_Y = Math.max(...GRID.ys) - Math.min(...GRID.ys);
const TOL = 1e-9;

/** Every point of `a` has one of `b` within TOL of each axis's span. */
function covered(a: number[][], b: number[][]): number[][] {
  return a.filter(
    ([x, y]) => !b.some(([u, v]) => Math.abs(u - x) <= TOL * SPAN_X && Math.abs(v - y) <= TOL * SPAN_Y),
  );
}

describe("the contours are contourpy's (the unit-2 gate)", () => {
  const ours = mapContours(GRID, FX.refs, FX.z0);

  it("the CLI's contour list: the Ref lines, then the SWR threshold", () => {
    expect(ours.map((c) => [c.quantity, c.level])).toEqual(
      FX.contours.map((c) => [c.quantity, c.level]),
    );
    expect(ours.map((c) => c.at)).toEqual(FX.contours.map((c) => c.at));
  });

  for (const c of FX.contours.filter((k) => k.reached)) {
    it(`${c.quantity} = ${c.level}: every vertex within 1e-9 of the span, both ways`, () => {
      const field = contourField(GRID, c.quantity, FX.z0);
      const segs = contourSegments(GRID.xs, GRID.ys, field, c.at);
      const mine = segs.flatMap(([x1, y1, x2, y2]) => [
        [x1, y1],
        [x2, y2],
      ]);
      const theirs = c.lines.flat();
      expect(theirs.length).toBeGreaterThan(10);
      expect(covered(mine, theirs)).toEqual([]);
      expect(covered(theirs, mine)).toEqual([]);
      // One segment per step along each of contourpy's lines.
      const steps = c.lines.reduce((n, l) => n + l.length - 1, 0);
      expect(segs.length).toBe(steps);
    });
  }

  it('a level the grid never reaches is named "(not reached)" and draws nothing', () => {
    const never = ours.find((c) => c.level === 5000)!;
    expect(never.reached).toBe(false);
    expect(never.segments).toEqual([]);
    expect(never.label).toBe("R = 5000 Ω (not reached)");
    expect(ours.filter((c) => c.reached).map((c) => c.label)).toEqual([
      "X = 0 Ω",
      "R = 50 Ω",
      "R = 75 Ω",
      "SWR = 2 (|Γ| = 0.333)",
    ]);
    for (const c of FX.contours) {
      expect(contourReached(contourField(GRID, c.quantity, FX.z0), c.at)).toBe(c.reached);
    }
  });

  it("the SWR threshold is traced on |Γ| at (s − 1)/(s + 1)", () => {
    expect(swrGamma(2)).toBeCloseTo(1 / 3, 15);
    const f = contourField(GRID, "SWR", FX.z0);
    expect(f[0][0]).toBe(gammaOf(FX.re[0][0], FX.im[0][0], FX.z0));
  });
});

describe("the CLI's other rules", () => {
  it("no R or X line: X = 0 and R = z0, and the threshold still draws", () => {
    expect(mapContourLevels({ r: [], x: [], swr: null }, 75)).toEqual([
      { quantity: "X", level: 0 },
      { quantity: "R", level: 75 },
    ]);
    expect(mapContourLevels({ r: [], x: [], swr: 1.5 }, 50).map((c) => c.quantity)).toEqual([
      "X",
      "R",
      "SWR",
    ]);
  });

  it("the best node is best_cell_line's, word for word", () => {
    const b = bestNode(GRID, FX.z0)!;
    expect([b.i, b.j]).toEqual([FX.best.i, FX.best.j]);
    expect(bestNodeLine(b, GRID, FX.x.param, FX.y.param)).toBe(FX.best.line);
  });

  it("formats as Python's g", () => {
    expect(formatG(0.023456, 3)).toBe("0.0235");
    expect(formatG(1.05, 3)).toBe("1.05");
    expect(formatG(30, 6)).toBe("30");
    expect(formatG(0.975, 6)).toBe("0.975");
    expect(formatG(4.99975e-5, 3)).toBe("5e-05");
    expect(formatG(1234567, 6)).toBe("1.23457e+06");
    expect(formatG(5000, 6)).toBe("5000");
  });
});

describe("a partial grid", () => {
  it("draws what has landed, and its best node so far", () => {
    const g = emptyGrid(GRID.xs, GRID.ys) as { xs: number[]; ys: number[]; re: (number | null)[][]; im: (number | null)[][] };
    // The first 8 rows of 25, as the stream lands them (y outer).
    for (let j = 0; j < 8; j++) {
      g.re[j] = FX.re[j].slice();
      g.im[j] = FX.im[j].slice();
    }
    expect(landed(g)).toBe(8 * 33);
    const b = bestNode(g, FX.z0)!;
    expect(b.j).toBeLessThan(8);
    // A cell with an unsolved corner draws nothing: no segment reaches
    // past row 7.
    for (const c of mapContours(g, FX.refs, FX.z0)) {
      for (const [, y1, , y2] of c.segments) {
        expect(Math.max(y1, y2)).toBeLessThanOrEqual(GRID.ys[7]);
      }
    }
  });
});

describe("colours and cells", () => {
  it("viridis_r: a match is yellow, |Γ| = 1 dark violet", () => {
    expect(viridisR(0)).toEqual([253, 231, 37]);
    expect(viridisR(1)).toEqual([68, 1, 84]);
    expect(viridisR(0.5)).toEqual([33, 144, 141]);
    expect(viridisR(2)).toEqual([68, 1, 84]);
  });
  it("1 − 1/SWR is 2|Γ|/(1 + |Γ|)", () => {
    const g = 1 / 3; // SWR 2
    expect(colourValue(g, "reciprocal")).toBeCloseTo(0.5, 15);
    expect(colourValue(g, "rho")).toBe(g);
  });
  it("cells run to the midpoints (nearest shading), and a hover finds its node", () => {
    expect(cellEdges([0, 1, 3])).toEqual([-0.5, 0.5, 2, 4]);
    expect(nodeAt([0, 1, 3], [10, 20], 1.9, 16)).toEqual({ i: 1, j: 1 });
    expect(nodeAt([0, 1, 3], [10, 20], 2.1, 14)).toEqual({ i: 2, j: 0 });
    expect(nodeAt([0, 1, 3], [10, 20], 4.5, 14)).toBeNull();
  });
});
