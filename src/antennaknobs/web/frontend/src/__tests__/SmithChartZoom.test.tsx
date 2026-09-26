// Pins the Smith chart's own zoom (SmithChart.tsx + lib/smithView.ts): the
// stage chart takes the wheel — plain or Ctrl, the page must neither scroll
// nor zoom — and a thumbnail ignores it; double-click, the fit button and a
// design switch go back to the whole chart; the view survives a re-solve.
// data-zoom is the seam (jsdom has no canvas pixels), plus a recording
// context for "markers stay screen-sized and land where the transform says".
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { SmithChart } from "../components/charts/SmithChart";
import { reflectionCoefficient } from "../lib/format";
import { gammaToScreen } from "../lib/smithView";

const SIZE = 300;

function props(over: Partial<ComponentProps<typeof SmithChart>> = {}) {
  return {
    r: 70,
    x: 20,
    z0: 50,
    size: SIZE,
    sweep: null,
    converge: null,
    measured: null,
    measFreqMhz: 14,
    running: false,
    convergeRunning: false,
    multiFeed: false,
    ...over,
  };
}

const zoomOf = (c: HTMLElement) => Number(c.querySelector("canvas.smith")!.getAttribute("data-zoom"));

describe("Smith chart zoom", () => {
  it("zooms the stage chart on a plain wheel and keeps the page still", () => {
    const { container } = render(<SmithChart {...props({ interactive: true })} />);
    const canvas = container.querySelector("canvas.smith")!;
    expect(zoomOf(container)).toBe(1);
    // fireEvent returns false when the listener called preventDefault.
    expect(fireEvent.wheel(canvas, { deltaY: -300, clientX: 150, clientY: 150 })).toBe(false);
    expect(zoomOf(container)).toBeGreaterThan(1.5);
  });

  it("takes a Ctrl+wheel (trackpad pinch) instead of the browser's page zoom", () => {
    const { container } = render(<SmithChart {...props({ interactive: true })} />);
    const canvas = container.querySelector("canvas.smith")!;
    expect(fireEvent.wheel(canvas, { deltaY: -120, ctrlKey: true })).toBe(false);
    expect(zoomOf(container)).toBeGreaterThan(1);
  });

  it("leaves a thumbnail alone: no zoom, and the wheel goes to the page", () => {
    const { container } = render(<SmithChart {...props()} />);
    const canvas = container.querySelector("canvas.smith")!;
    expect(fireEvent.wheel(canvas, { deltaY: -300 })).toBe(true);
    expect(zoomOf(container)).toBe(1);
    expect(canvas.getAttribute("tabindex")).toBeNull();
  });

  it("double-click resets, and the fit control shows only while zoomed", () => {
    const { container } = render(<SmithChart {...props({ interactive: true })} />);
    const canvas = container.querySelector("canvas.smith")!;
    expect(screen.queryByRole("button", { name: "Show the whole chart" })).toBeNull();
    fireEvent.wheel(canvas, { deltaY: -500 });
    expect(zoomOf(container)).toBeGreaterThan(1);
    expect(screen.getByRole("button", { name: "Show the whole chart" })).toBeTruthy();
    fireEvent.doubleClick(canvas);
    expect(zoomOf(container)).toBe(1);
    expect(screen.queryByRole("button", { name: "Show the whole chart" })).toBeNull();
  });

  it("zooms with + / − / 0 when focused", () => {
    const { container } = render(<SmithChart {...props({ interactive: true })} />);
    const canvas = container.querySelector("canvas.smith")!;
    expect(canvas.getAttribute("aria-label")).toMatch(/zoom/i);
    fireEvent.keyDown(canvas, { key: "+" });
    fireEvent.keyDown(canvas, { key: "+" });
    expect(zoomOf(container)).toBeCloseTo(1.5625, 9);
    fireEvent.keyDown(canvas, { key: "-" });
    expect(zoomOf(container)).toBeCloseTo(1.25, 9);
    fireEvent.keyDown(canvas, { key: "0" });
    expect(zoomOf(container)).toBe(1);
  });

  it("keeps the view across solves of a design, and drops it on a design switch", () => {
    const { container, rerender } = render(
      <SmithChart {...props({ interactive: true, designKey: "dipoles.invvee" })} />,
    );
    fireEvent.wheel(container.querySelector("canvas.smith")!, { deltaY: -400 });
    const z = zoomOf(container);
    expect(z).toBeGreaterThan(1);
    // A knob drag: new impedance, same design.
    rerender(<SmithChart {...props({ interactive: true, designKey: "dipoles.invvee", r: 60 })} />);
    expect(zoomOf(container)).toBe(z);
    rerender(<SmithChart {...props({ interactive: true, designKey: "yagis.yagi3", r: 60 })} />);
    expect(zoomOf(container)).toBe(1);
  });

  it("moves the marker with the view but keeps its size in screen pixels", () => {
    const arcs: Array<{ x: number; y: number; radius: number }> = [];
    const noop = () => {};
    const ctx = {
      fillStyle: "",
      strokeStyle: "",
      lineWidth: 1,
      font: "",
      setTransform: noop,
      fillRect: noop,
      beginPath: noop,
      arc(x: number, y: number, radius: number) {
        arcs.push({ x, y, radius });
      },
      stroke: noop,
      fill: noop,
      moveTo: noop,
      lineTo: noop,
      save: noop,
      restore: noop,
      clip: noop,
      fillText: noop,
      measureText: () => ({ width: 10 }),
      setLineDash: noop,
      rect: noop,
      translate: noop,
      rotate: noop,
    };
    HTMLCanvasElement.prototype.getContext = (() => ctx) as unknown as HTMLCanvasElement["getContext"];
    try {
      const { container } = render(<SmithChart {...props({ interactive: true })} />);
      const canvas = container.querySelector("canvas.smith")!;
      fireEvent.wheel(canvas, { deltaY: -600, clientX: 170, clientY: 140 });
      const zoom = zoomOf(container);
      expect(zoom).toBeGreaterThan(2);
      // The last paint's markers: what the transform says, radius 4 as at fit.
      const g = reflectionCoefficient(70, 20, 50);
      const view = { zoom, panX: 0, panY: 0 };
      // Recover the pan from the anchor: the Γ under (170,140) stayed put.
      const R = SIZE / 2 - 10;
      const a = { gRe: (170 - SIZE / 2) / R, gIm: -(140 - SIZE / 2) / R };
      view.panX = 170 - SIZE / 2 - zoom * a.gRe * R;
      view.panY = 140 - SIZE / 2 + zoom * a.gIm * R;
      const want = gammaToScreen(view, g.gRe, g.gIm, SIZE / 2, SIZE / 2, R);
      const marker = arcs.filter((c) => c.radius === 4).pop();
      expect(marker).toBeTruthy();
      expect(marker!.x).toBeCloseTo(want.x, 6);
      expect(marker!.y).toBeCloseTo(want.y, 6);
    } finally {
      HTMLCanvasElement.prototype.getContext = (() =>
        null) as unknown as typeof HTMLCanvasElement.prototype.getContext;
    }
  });
});
