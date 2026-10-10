// The Smith chart's design target circle and its admittance grid
// (SmithChart.tsx): the graphical L-network tune (PR #1967). A design
// declares, per measurement plane, the circle its tuner's remaining part
// moves the point along — "r" (r = 1, R = Z0) or "g" (g = 1, G = 1/Z0) —
// and the chart draws it heavier, in its own colour, labelled in the
// chart's own Z0. The admittance grid is the impedance grid mirrored
// through the centre. A recording context stands in for the canvas.
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { SmithChart } from "../components/charts/SmithChart";
import { smithTargetLabel } from "../lib/smithView";

const SIZE = 300;
const R = SIZE / 2 - 10; // the unit circle's radius at fit
const C = SIZE / 2;

function props(over: Partial<ComponentProps<typeof SmithChart>> = {}) {
  return {
    r: 70,
    x: 20,
    z0: 50,
    size: SIZE,
    sweep: null,
    paramSweep: null,
    measured: null,
    measFreqMhz: 14,
    running: false,
    paramSweepRunning: false,
    multiFeed: false,
    ...over,
  };
}

type Arc = { x: number; y: number; radius: number; stroke: string; width: number; dash: number[] };

/** Paint once with a recording context; every stroked arc with the ink it
 *  was stroked in, and every text drawn. */
function paint(over: Partial<ComponentProps<typeof SmithChart>>) {
  const arcs: Arc[] = [];
  const texts: Array<{ t: string; fill: string }> = [];
  let pending: Array<{ x: number; y: number; radius: number }> = [];
  let dash: number[] = [];
  const noop = () => {};
  const ctx = {
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 1,
    font: "",
    globalAlpha: 1,
    setTransform: noop,
    fillRect: noop,
    beginPath() {
      pending = [];
    },
    arc(x: number, y: number, radius: number) {
      pending.push({ x, y, radius });
    },
    stroke() {
      for (const a of pending)
        arcs.push({ ...a, stroke: String(ctx.strokeStyle), width: ctx.lineWidth, dash });
    },
    fill: noop,
    moveTo: noop,
    lineTo: noop,
    save: noop,
    restore: noop,
    clip: noop,
    fillText(t: string) {
      texts.push({ t, fill: String(ctx.fillStyle) });
    },
    measureText: (t: string) => ({ width: 6 * t.length }),
    setLineDash(d: number[]) {
      dash = d;
    },
    rect: noop,
    translate: noop,
    rotate: noop,
  };
  HTMLCanvasElement.prototype.getContext = (() => ctx) as unknown as HTMLCanvasElement["getContext"];
  const view = render(<SmithChart {...props(over)} />);
  return { arcs, texts, view };
}

afterEach(() => {
  HTMLCanvasElement.prototype.getContext = (() =>
    null) as unknown as typeof HTMLCanvasElement.prototype.getContext;
  vi.restoreAllMocks();
});

const near = (a: number, b: number) => Math.abs(a - b) < 1e-6;
/** Arcs of the circle centred at Γ = (g, 0) with Γ-radius `rho`. */
const circleAt = (arcs: Arc[], g: number, rho: number) =>
  arcs.filter((a) => near(a.x, C + g * R) && near(a.y, C) && near(a.radius, rho * R));

describe("Smith chart target circle", () => {
  it("draws r = 1 heavier than the grid, in its own ink, labelled R = Z0", () => {
    const { arcs, texts, view } = paint({ target: "r" });
    // The grid's own r = 1 circle and the target, on the same centre.
    const r1 = circleAt(arcs, 0.5, 0.5);
    expect(r1.length).toBe(2);
    const grid = r1.find((a) => a.width < 1)!;
    const tgt = r1.find((a) => a.width === 2)!;
    expect(tgt).toBeTruthy();
    expect(tgt.stroke).not.toBe(grid.stroke);
    expect(texts.some((t) => t.t === "R = 50 Ω" && t.fill === tgt.stroke)).toBe(true);
    expect(view.container.querySelector("canvas.smith")!.getAttribute("data-target")).toBe("r");
  });

  it("draws g = 1 on the admittance side, labelled G = 1/Z0 in the chart's Z0", () => {
    const { arcs, texts } = paint({ target: "g", z0: 75 });
    const g1 = circleAt(arcs, -0.5, 0.5);
    expect(g1.length).toBe(1);
    expect(g1[0].width).toBe(2);
    expect(texts.some((t) => t.t === "G = 13.3 mS")).toBe(true);
    // No r = 1 target: only the grid's thin r = 1 circle.
    expect(circleAt(arcs, 0.5, 0.5).every((a) => a.width < 1)).toBe(true);
  });

  it("draws nothing for a design that declares no target", () => {
    const { arcs, texts, view } = paint({});
    expect(arcs.some((a) => a.width === 2)).toBe(false);
    expect(texts.some((t) => /^[RG] = /.test(t.t))).toBe(false);
    expect(view.container.querySelector("canvas.smith")!.getAttribute("data-target")).toBe("");
  });

  it("labels in the chart's own Z0", () => {
    expect(smithTargetLabel("r", 50)).toBe("R = 50 Ω");
    expect(smithTargetLabel("g", 50)).toBe("G = 20 mS");
    expect(smithTargetLabel("r", 75)).toBe("R = 75 Ω");
  });
});

describe("Smith chart admittance grid", () => {
  it("is off by default: no circle centred left of the chart's centre", () => {
    const { arcs } = paint({});
    expect(arcs.some((a) => a.x < C - 1e-6 && near(a.y, C))).toBe(false);
  });

  it("mirrors the impedance grid through the centre, dashed in its own ink", () => {
    const { arcs } = paint({ yGrid: true });
    for (const n of [0.2, 0.5, 1, 2, 5]) {
      const z = circleAt(arcs, n / (n + 1), 1 / (n + 1));
      const y = circleAt(arcs, -n / (n + 1), 1 / (n + 1));
      expect(z.length).toBe(1);
      expect(y.length).toBe(1);
      expect(y[0].dash.length).toBeGreaterThan(0);
      expect(z[0].dash.length).toBe(0);
      expect(y[0].stroke).not.toBe(z[0].stroke);
    }
    // Constant-b arcs: centred on Γ = (−1, ±1/b), capacitive below.
    for (const b of [0.5, 2]) {
      for (const sgn of [1, -1]) {
        expect(
          arcs.some((a) => near(a.x, C - R) && near(a.y, C - (sgn / b) * R) && near(a.radius, R / b)),
        ).toBe(true);
      }
    }
  });

  it("offers its toggle on the stage chart only, and reports a press", () => {
    const onYGridChange = vi.fn();
    paint({ interactive: true, onYGridChange });
    const btn = screen.getByRole("button", { name: "Admittance grid" });
    expect(btn.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(btn);
    expect(onYGridChange).toHaveBeenCalledWith(true);
  });

  it("shows no toggle on a thumbnail", () => {
    paint({ yGrid: true, onYGridChange: vi.fn() });
    expect(screen.queryByRole("button", { name: "Admittance grid" })).toBeNull();
  });
});
