// AK#1969: a drawn sweep polyline must not show a visible kink. Where a vertex
// turns by more than 5° and the sampling has not resolved it, the segments
// meeting there are not drawn and the samples show as dots; a kink that
// persists under refinement (a VSWR notch's tip) is a feature and stays drawn.
import { describe, expect, it } from "vitest";
import {
  type DisplayPoint,
  DEVIATION_TOLERANCE,
  KINK_BREAK_DEG,
  MIN_SEGMENT,
  kinkBreaks,
  turnAngles,
} from "../lib/refine";

const EXT = 350; // px, the charts' size

/** A circle of radius `r` px about the plot centre, sampled every `stepDeg`
 *  over `spanDeg` — a fast-rotating Smith locus when the step is coarse. */
function arc(r: number, stepDeg: number, spanDeg: number): DisplayPoint[] {
  const out: DisplayPoint[] = [];
  for (let a = 0; a <= spanDeg + 1e-9; a += stepDeg) {
    const t = (a * Math.PI) / 180;
    out.push({ x: EXT / 2 + r * Math.cos(t), y: EXT / 2 + r * Math.sin(t) });
  }
  return out;
}

/** A VSWR-like notch, |f − f0| shaped, sampled every `step` px of x across
 *  the plot: the tip is a genuine cusp whatever the sampling. */
function notch(step: number): DisplayPoint[] {
  const out: DisplayPoint[] = [];
  for (let x = 0; x <= EXT + 1e-9; x += step) {
    out.push({ x, y: 20 + 1.5 * Math.abs(x - EXT / 2) });
  }
  return out;
}

const tipOf = (pts: DisplayPoint[]) =>
  pts.reduce((best, p, i) => (p.y < pts[best].y ? i : best), 0);

describe("kinkBreaks", () => {
  it("a coarse fast-rotating locus draws no segment at its kinked vertices", () => {
    const pts = arc(150, 40, 320); // 40° per sample: every vertex turns 40°
    const { segments, dots } = kinkBreaks(pts, EXT);
    // The red control: today's always-connect drew every segment.
    expect(segments.every(Boolean)).toBe(false);
    const turns = turnAngles(pts.map((p) => ({ x: p.x / EXT, y: p.y / EXT })));
    turns.forEach((t, i) => {
      if (t * (180 / Math.PI) <= KINK_BREAK_DEG) return;
      if (i > 0) expect(segments[i - 1]).toBe(false);
      if (i < segments.length) expect(segments[i]).toBe(false);
      expect(dots[i]).toBe(true);
    });
  });

  it("a well-sampled smooth locus draws one continuous line and no dots", () => {
    const pts = arc(150, 1, 320);
    const { segments, dots } = kinkBreaks(pts, EXT);
    expect(segments.every(Boolean)).toBe(true);
    expect(dots.some(Boolean)).toBe(false);
  });

  it("a finely sampled notch draws through its tip; the same notch coarse breaks there", () => {
    // Fine: the tip's two segments are no longer than MIN_SEGMENT of the
    // plot, which is where refinement stops splitting — resolved.
    const fineStep = (MIN_SEGMENT * EXT) / 2;
    const fine = notch(fineStep);
    const ft = tipOf(fine);
    const f = kinkBreaks(fine, EXT);
    expect(f.segments[ft - 1]).toBe(true);
    expect(f.segments[ft]).toBe(true);
    expect(f.segments.every(Boolean)).toBe(true);
    // Coarse: the same cusp between samples 25 px apart is a corner nobody
    // resolved, so the line breaks at the tip and its samples show.
    const coarse = notch(25);
    const ct = tipOf(coarse);
    const c = kinkBreaks(coarse, EXT);
    expect(c.segments[ct - 1]).toBe(false);
    expect(c.segments[ct]).toBe(false);
    expect(c.dots[ct]).toBe(true);
    // ...and only there: the straight flanks stay drawn.
    expect(c.segments.filter((s) => !s)).toHaveLength(2);
  });

  it("a corner within a pixel of its chord stays drawn", () => {
    // Turns 10°, but the vertex sits under DEVIATION_TOLERANCE of the plot
    // from its chord: the picture is already right there.
    const h = 0.5 * DEVIATION_TOLERANCE * EXT;
    const run = h / Math.tan((5 * Math.PI) / 180);
    const pts = [
      { x: 100, y: 100 },
      { x: 100 + run, y: 100 + h },
      { x: 100 + 2 * run, y: 100 },
    ];
    const t = turnAngles(pts.map((p) => ({ x: p.x / EXT, y: p.y / EXT })))[1];
    expect(t * (180 / Math.PI)).toBeGreaterThan(KINK_BREAK_DEG);
    expect(kinkBreaks(pts, EXT).segments).toEqual([true, true]);
  });

  it("an off-plot vertex never breaks the line", () => {
    // A sharp spike above the plot: its corner is not seen, and breaking it
    // would drop the two visible segments that cross the edge.
    const spike = [
      { x: 0, y: 200 },
      { x: 50, y: -400, clamped: true },
      { x: 100, y: 200 },
    ];
    expect(kinkBreaks(spike, EXT).segments).toEqual([true, true]);
    const unclamped = spike.map(({ x, y }) => ({ x, y }));
    expect(kinkBreaks(unclamped, EXT).segments).toEqual([false, false]);
  });

  it("a non-finite sample draws nothing either side and gets no dot", () => {
    const pts = [
      { x: 0, y: 0 },
      { x: 10, y: 10 },
      { x: 20, y: Number.NaN },
      { x: 30, y: 30 },
      { x: 40, y: 40 },
    ];
    const { segments, dots } = kinkBreaks(pts, EXT);
    expect(segments).toEqual([true, false, false, true]);
    expect(dots).toEqual([false, true, false, true, false]);
  });

  it("degenerate inputs", () => {
    expect(kinkBreaks([], EXT)).toEqual({ segments: [], dots: [] });
    expect(kinkBreaks([{ x: 1, y: 1 }], EXT)).toEqual({ segments: [], dots: [true] });
    expect(kinkBreaks([{ x: 1, y: 1 }, { x: 5, y: 9 }], EXT).segments).toEqual([true]);
  });
});
