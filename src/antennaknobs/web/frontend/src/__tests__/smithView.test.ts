// Pins the Smith chart's zoom math (lib/smithView.ts): zooming about a point
// keeps that point under the cursor, the zoom clamps to [1, 50], all the way
// out is exactly the fit view, and the grid refines to round ohms as the
// zoom grows.
import { describe, expect, it } from "vitest";
import {
  FIT_VIEW,
  SMITH_ZOOM_MAX,
  clampView,
  gammaToScreen,
  niceFloor,
  panBy,
  screenToGamma,
  smithGrid,
  zoomAbout,
} from "../lib/smithView";

const SIZE = 400;
const C = SIZE / 2;
const R = SIZE / 2 - 10;

describe("zoomAbout", () => {
  it("keeps the Γ point under the anchor fixed", () => {
    let v = FIT_VIEW;
    // Three detents at different anchors, so pan is non-trivial going in.
    for (const [f, ax, ay] of [
      [1.6, 250, 180],
      [2.5, 120, 260],
      [0.7, 300, 150],
    ] as const) {
      const before = screenToGamma(v, ax, ay, C, C, R);
      v = zoomAbout(v, f, ax, ay, C, C, R);
      const after = gammaToScreen(v, before.gRe, before.gIm, C, C, R);
      expect(after.x).toBeCloseTo(ax, 9);
      expect(after.y).toBeCloseTo(ay, 9);
    }
    expect(v.zoom).toBeCloseTo(1.6 * 2.5 * 0.7, 9);
  });

  it("clamps to [1, SMITH_ZOOM_MAX] and snaps back to the fit view at 1", () => {
    const deep = zoomAbout(FIT_VIEW, 1e6, 260, 190, C, C, R);
    expect(deep.zoom).toBe(SMITH_ZOOM_MAX);
    const out = zoomAbout(deep, 1e-6, 10, 10, C, C, R);
    expect(out).toEqual(FIT_VIEW);
    expect(zoomAbout(FIT_VIEW, 0.5, 300, 300, C, C, R)).toEqual(FIT_VIEW);
  });

  it("never lets a pan carry the view's centre off the chart", () => {
    const v = panBy({ zoom: 4, panX: 0, panY: 0 }, 1e5, -3e4, R);
    const mid = screenToGamma(v, C, C, C, C, R);
    expect(Math.hypot(mid.gRe, mid.gIm)).toBeCloseTo(1, 9);
    expect(clampView({ zoom: 1, panX: 50, panY: 5 }, R)).toEqual(FIT_VIEW);
  });
});

describe("smithGrid", () => {
  it("keeps the classic unlabelled grid at fit", () => {
    const g = smithGrid(1, 50);
    expect(g.stepOhms).toBeNull();
    expect(g.r.map((l) => l.n)).toEqual([0.2, 0.5, 1, 2, 5]);
    expect(g.r.every((l) => l.label === undefined)).toBe(true);
  });

  it("steps in round ohms that shrink with the zoom", () => {
    expect(smithGrid(2, 50).stepOhms).toBe(20);
    expect(smithGrid(10, 50).stepOhms).toBe(5);
    expect(smithGrid(20, 50).stepOhms).toBe(2);
    expect(smithGrid(50, 50).stepOhms).toBe(1);
    // A 75 Ω chart at 10×: 7.5 rounds down to 5.
    expect(smithGrid(10, 75).stepOhms).toBe(5);
  });

  it("puts labelled lines through the match point, in ohms", () => {
    const g = smithGrid(50, 50);
    const at50 = g.r.find((l) => l.label === "50");
    expect(at50?.n).toBeCloseTo(1, 12);
    const labels = g.r.map((l) => l.label);
    expect(labels).toEqual(expect.arrayContaining(["49", "51", "1", "200"]));
    // Coarse lines past the fine span carry the outer chart.
    expect(g.r[g.r.length - 1]).toEqual({ n: 20, label: "1000" });
    expect(smithGrid(10, 50).x.map((l) => l.label).slice(0, 3)).toEqual(["5", "10", "15"]);
  });

  it("niceFloor rounds down to 1/2/5 × 10^k", () => {
    expect([0.7, 1, 3, 7.5, 25, 49].map(niceFloor)).toEqual([0.5, 1, 2, 5, 20, 20]);
  });
});
