// Pins the SWR / S11 charts' frequency zoom math (lib/sweepView.ts): zooming
// about a frequency keeps it at the same place on the axis, the view never
// leaves the sweep, it stops at span / SWEEP_ZOOM_MAX, a band click shows the
// band with its margin, and all the way out is exactly the whole sweep.
import { describe, expect, it } from "vitest";
import {
  BAND_MARGIN,
  FULL_VIEW,
  SWEEP_ZOOM_MAX,
  bandView,
  clampView,
  dragView,
  formatView,
  isZoomed,
  panBy,
  roundView,
  visibleSpan,
  visibleValues,
  zoomAbout,
} from "../lib/sweepView";

const SPAN = { lo: 13, hi: 15 };
const frac = (f: number, v: { lo: number; hi: number }) => (f - v.lo) / (v.hi - v.lo);
const expectSpan = (v: { lo: number; hi: number } | null, lo: number, hi: number) => {
  expect(v).not.toBeNull();
  expect(v!.lo).toBeCloseTo(lo, 12);
  expect(v!.hi).toBeCloseTo(hi, 12);
};

describe("zoomAbout", () => {
  it("keeps the frequency under the anchor at the same place on the axis", () => {
    let view = FULL_VIEW;
    for (const [factor, at] of [
      [1.6, 14.2],
      [2.5, 14.05],
      [0.7, 14.1],
    ] as const) {
      const before = visibleSpan(view, SPAN);
      const t = frac(at, before);
      view = zoomAbout(view, factor, at, SPAN);
      expect(frac(at, visibleSpan(view, SPAN))).toBeCloseTo(t, 9);
    }
    const v = visibleSpan(view, SPAN);
    expect((SPAN.hi - SPAN.lo) / (v.hi - v.lo)).toBeCloseTo(1.6 * 2.5 * 0.7, 9);
  });

  it("shifts back inside the sweep near an end instead of overhanging it", () => {
    // 13.2 sits a fifth of the way across; zooming out 2.5× about it would
    // start the window at 12.95, below the sweep.
    expectSpan(zoomAbout({ lo: 13.1, hi: 13.6 }, 0.4, 13.2, SPAN), 13, 14.25);
  });

  it("stops at the minimum span, span / SWEEP_ZOOM_MAX", () => {
    let view = FULL_VIEW;
    for (let i = 0; i < 40; i++) view = zoomAbout(view, 2, 14, SPAN);
    const v = visibleSpan(view, SPAN);
    expect(v.hi - v.lo).toBeCloseTo((SPAN.hi - SPAN.lo) / SWEEP_ZOOM_MAX, 12);
    expect(v.lo).toBeLessThanOrEqual(14);
    expect(v.hi).toBeGreaterThanOrEqual(14);
  });

  it("zooming all the way out is the whole sweep, not a view a hair short of it", () => {
    const view = zoomAbout(zoomAbout(FULL_VIEW, 3, 14.5, SPAN), 1 / 3.0001, 14.5, SPAN);
    expect(view).toBeNull();
    expect(isZoomed(view, SPAN)).toBe(false);
    expect(zoomAbout(FULL_VIEW, 0.5, 14, SPAN)).toBeNull();
  });
});

describe("clampView", () => {
  it("is the identity on a window inside the sweep", () => {
    expectSpan(clampView({ lo: 13.5, hi: 14 }, SPAN), 13.5, 14);
  });

  it("shifts an overhanging window back inside, keeping its width", () => {
    expectSpan(clampView({ lo: 14.6, hi: 15.4 }, SPAN), 14.2, 15);
    expectSpan(clampView({ lo: 12.5, hi: 13.5 }, SPAN), 13, 14);
  });

  it("widens a window narrower than the minimum about its centre", () => {
    const v = clampView({ lo: 14, hi: 14 }, SPAN)!;
    expect(v.hi - v.lo).toBeCloseTo(0.002, 12);
    expect((v.lo + v.hi) / 2).toBeCloseTo(14, 12);
  });

  it("is the whole sweep for a window as wide as it, and for a sweep with no width", () => {
    expect(clampView({ lo: 12, hi: 16 }, SPAN)).toBeNull();
    expect(clampView({ lo: 14, hi: 14.1 }, { lo: 14, hi: 14 })).toBeNull();
  });

  it("follows a moved sweep: a window the new span still holds is kept", () => {
    const view = { lo: 14.1, hi: 14.2 };
    expectSpan(visibleSpan(view, { lo: 14, hi: 14.5 }), 14.1, 14.2);
    // Off the new span altogether: shifted inside, still its width.
    const moved = visibleSpan(view, { lo: 20, hi: 22 });
    expect(moved.lo).toBe(20);
    expect(moved.hi).toBeCloseTo(20.1, 12);
  });
});

describe("bandView", () => {
  it("shows the band with BAND_MARGIN of its width either side", () => {
    const v = bandView({ lo: 14, hi: 14.35 }, SPAN)!;
    expect(v.lo).toBeCloseTo(14 - BAND_MARGIN * 0.35, 12);
    expect(v.hi).toBeCloseTo(14.35 + BAND_MARGIN * 0.35, 12);
  });

  it("cuts the margin at the sweep's end", () => {
    const v = bandView({ lo: 13, hi: 13.2 }, SPAN)!;
    expect(v.lo).toBe(13);
    expect(v.hi).toBeCloseTo(13.22, 12);
  });

  it("is the whole sweep when the band covers it", () => {
    expect(bandView({ lo: 12, hi: 16 }, SPAN)).toBeNull();
  });
});

describe("dragView, panBy and reset", () => {
  it("selects the dragged span in either direction, cut to the sweep", () => {
    expectSpan(dragView(14.2, 13.8, SPAN), 13.8, 14.2);
    expectSpan(dragView(12, 13.5, SPAN), 13, 13.5);
  });

  it("pans a zoomed window and stops at the ends; the whole sweep does not pan", () => {
    expectSpan(panBy({ lo: 14, hi: 14.5 }, 0.25, SPAN), 14.25, 14.75);
    expectSpan(panBy({ lo: 14, hi: 14.5 }, 2, SPAN), 14.5, 15);
    expect(panBy(FULL_VIEW, 0.3, SPAN)).toBeNull();
  });

  it("reset is the identity: the full view draws the sweep's own span", () => {
    expect(FULL_VIEW).toBeNull();
    expect(visibleSpan(FULL_VIEW, SPAN)).toEqual(SPAN);
    expect(isZoomed(FULL_VIEW, SPAN)).toBe(false);
  });
});

describe("visibleValues", () => {
  const xs = [10, 12, 14, 16];
  const ys = [5, 1, 3, 9];

  it("takes the samples inside and the curve's height at each edge", () => {
    expect(visibleValues(xs, ys, 11, 15).sort((a, b) => a - b)).toEqual([1, 3, 3, 6]);
  });

  it("has a height for a window between two samples", () => {
    expect(visibleValues(xs, ys, 12.5, 13)).toEqual([1.5, 2]);
  });

  it("is empty off the curve", () => {
    expect(visibleValues(xs, ys, 20, 21)).toEqual([]);
  });
});

describe("formatView", () => {
  it("reads to the kHz, finer when the window is narrower", () => {
    expect(formatView({ lo: 14, hi: 14.35 })).toBe("14.000–14.350 MHz");
    expect(formatView({ lo: 14.1, hi: 14.1025 })).toBe("14.1000–14.1025 MHz");
    expect(formatView({ lo: 0.1357, hi: 0.1357021 })).toBe("0.1357000–0.1357021 MHz");
  });

  it("rounds the window to the digits it reads with", () => {
    expect(roundView({ lo: 14.01234567, hi: 14.3398765 })).toEqual({ lo: 14.012, hi: 14.34 });
  });
});
