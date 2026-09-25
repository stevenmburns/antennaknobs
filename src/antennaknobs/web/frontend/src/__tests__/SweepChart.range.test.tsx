// AK#1738 through SweepChart: the drawn range (data-y-lo / data-y-hi), Auto's
// grow-while-live / re-fit-on-settle rule, the planner contract (the chart and
// lib/refine.ts's sweepProjections derive the same domain), the bandwidth
// readout and the axis popover. jsdom has no 2-D context, so — as in
// SweepChart.test.tsx — what is asserted is the render-time data-* output.
import type { ComponentProps } from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { AUTO_SETTLE_MS, SweepChart } from "../components/charts/SweepChart";
import type { SweepData } from "../lib/api";
import { sweepProjections } from "../lib/refine";
import { AUTO_AXES, type SweepAxisChoice, type SweepMode } from "../lib/sweepAxis";

HTMLCanvasElement.prototype.getContext =
  (() => null) as unknown as HTMLCanvasElement["getContext"];

afterEach(() => {
  vi.useRealTimers();
});

// A resonance whose best VSWR is ~1.1 at 14.2 MHz (R = 55 Ω there).
function notch(freqs: number[], rAtDip = 55): SweepData {
  return {
    freqs_mhz: freqs,
    z_re: freqs.map(() => rAtDip),
    z_im: freqs.map((f) => 400 * (f - 14.2)),
  };
}
const FREQS = Array.from({ length: 21 }, (_, i) => 13.7 + i * 0.05);

type Props = ComponentProps<typeof SweepChart>;
const BASE: Props = {
  mode: "vswr",
  r: 0,
  x: 0,
  z0: 50,
  size: 200,
  sweep: null,
  measFreqMhz: 14.2,
  running: false,
  multiFeed: false,
};

function canvasOf(container: HTMLElement): HTMLCanvasElement {
  return container.querySelector("canvas.sweep") as HTMLCanvasElement;
}
const domainOf = (c: HTMLCanvasElement) => ({
  lo: Number(c.dataset.yLo),
  hi: Number(c.dataset.yHi),
});

describe("the drawn range", () => {
  it("Auto fits the sweep's dip: VSWR 1–1.5, S11 floor −40 for a 1.1 dip", () => {
    const v = render(<SweepChart {...BASE} sweep={notch(FREQS)} />);
    expect(domainOf(canvasOf(v.container))).toEqual({ lo: 1, hi: 1.5 });
    // The same instance switched to S11, as the stage does: the VSWR range
    // is not carried over.
    v.rerender(<SweepChart {...BASE} mode="gamma" sweep={notch(FREQS)} />);
    // |Γ| = 5/105 ⇒ −26.4 dB, which clears −30 by less than 5 dB ⇒ −40.
    expect(domainOf(canvasOf(v.container))).toEqual({ lo: -40, hi: 0 });
  });

  it("a fixed choice is drawn exactly", () => {
    const axis: SweepAxisChoice = { kind: "fixed", lo: 1, hi: 3 };
    const { container } = render(
      <SweepChart {...BASE} sweep={notch(FREQS)} axis={axis} />,
    );
    expect(domainOf(canvasOf(container))).toEqual({ lo: 1, hi: 3 });
    expect(canvasOf(container).dataset.axis).toBe("fixed");
  });

  it("the planner judges curvature on the same domain the chart draws", () => {
    // sweepProjections maps y to (v − lo)/(hi − lo) on ITS domain; the
    // chart's published domain must give the same fraction per sample.
    const cases: [SweepMode, SweepAxisChoice][] = [
      ["vswr", { kind: "auto" }],
      ["vswr", { kind: "fixed", lo: 1, hi: 2 }],
      ["gamma", { kind: "auto" }],
      ["gamma", { kind: "fixed", lo: -20, hi: 0 }],
    ];
    for (const [mode, axis] of cases) {
      const sweep = notch(FREQS);
      const { container, unmount } = render(
        <SweepChart {...BASE} mode={mode} sweep={sweep} axis={axis} />,
      );
      const c = canvasOf(container);
      const d = domainOf(c);
      const ys = (c.dataset.yValues ?? "").split(",").map(Number);
      const [proj] = sweepProjections(
        sweep,
        50,
        { vswr: mode === "vswr", gamma: mode === "gamma", smith: false },
        { ...AUTO_AXES, [mode]: axis },
      );
      const clamp = (v: number) => Math.max(0, Math.min(1, v));
      ys.forEach((y, i) =>
        expect(proj[i].y).toBeCloseTo(clamp((y - d.lo) / (d.hi - d.lo)), 3),
      );
      unmount();
    }
  });
});

describe("Auto grows while live and re-fits once the inputs settle", () => {
  it("a drag into a bad match grows the top; it shrinks back only after the dwell", () => {
    vi.useFakeTimers();
    // Settled on a good sweep: 1–1.5.
    const v = render(<SweepChart {...BASE} sweep={notch(FREQS)} r={55} x={0} />);
    const c = () => canvasOf(v.container);
    expect(domainOf(c())).toEqual({ lo: 1, hi: 1.5 });

    // A knob step blanks the sweep and moves the marker to VSWR 4: grows to 10.
    v.rerender(<SweepChart {...BASE} sweep={null} r={200} x={0} />);
    expect(domainOf(c()).hi).toBe(10);
    // The drag comes back to a good match: still 10 — never shrinks under
    // the hand...
    v.rerender(<SweepChart {...BASE} sweep={null} r={60} x={0} />);
    expect(domainOf(c()).hi).toBe(10);
    act(() => vi.advanceTimersByTime(AUTO_SETTLE_MS - 50));
    expect(domainOf(c()).hi).toBe(10);
    // ...until the inputs have been still for the dwell: re-fit to 1.2's 1.5.
    act(() => vi.advanceTimersByTime(100));
    expect(domainOf(c()).hi).toBe(1.5);
  });

  it("holds while a sweep streams in, then re-fits to the finished sweep", () => {
    vi.useFakeTimers();
    const v = render(<SweepChart {...BASE} sweep={null} r={200} x={0} />);
    const c = () => canvasOf(v.container);
    expect(domainOf(c()).hi).toBe(10); // the marker alone, VSWR 4
    // Points land while running: the partial sweep's fit is 1.5, but a
    // streaming sweep is live, so the 10 holds.
    v.rerender(
      <SweepChart {...BASE} sweep={notch(FREQS.slice(0, 12))} running r={200} x={0} />,
    );
    expect(domainOf(c()).hi).toBe(10);
    act(() => vi.advanceTimersByTime(AUTO_SETTLE_MS * 2));
    expect(domainOf(c()).hi).toBe(10); // still running
    v.rerender(<SweepChart {...BASE} sweep={notch(FREQS)} r={200} x={0} />);
    expect(domainOf(c()).hi).toBe(10); // the last point just landed
    act(() => vi.advanceTimersByTime(AUTO_SETTLE_MS));
    expect(domainOf(c()).hi).toBe(1.5);
  });

  it("a sweep's first streamed points (the band edge) do not grow the axis", () => {
    // Found in the real app: the first points of a streaming sweep are the
    // band edge, a mismatch; fitting them grew the axis to 100 until the
    // settle. While running, Auto fits the marker instead.
    vi.useFakeTimers();
    const v = render(<SweepChart {...BASE} sweep={null} r={55} x={0} />);
    const c = () => canvasOf(v.container);
    expect(domainOf(c()).hi).toBe(1.5);
    v.rerender(
      <SweepChart {...BASE} sweep={notch(FREQS.slice(0, 3))} running r={55} x={0} />,
    );
    expect(domainOf(c()).hi).toBe(1.5);
    v.rerender(<SweepChart {...BASE} sweep={notch(FREQS)} r={55} x={0} />);
    act(() => vi.advanceTimersByTime(AUTO_SETTLE_MS));
    expect(domainOf(c()).hi).toBe(1.5);
  });

  it("a fixed range never moves, live or not", () => {
    vi.useFakeTimers();
    const axis: SweepAxisChoice = { kind: "fixed", lo: 1, hi: 2 };
    const v = render(<SweepChart {...BASE} sweep={notch(FREQS)} axis={axis} />);
    v.rerender(<SweepChart {...BASE} sweep={null} r={400} x={0} axis={axis} />);
    expect(domainOf(canvasOf(v.container))).toEqual({ lo: 1, hi: 2 });
  });
});

describe("the threshold and the bandwidth readout", () => {
  it("reads the interpolated 2:1 band of feed 0's sweep", () => {
    // X = 400·(f − 14.2) against R = 50: VSWR = 2 where |X| = 35.36 Ω, i.e.
    // f = 14.2 ± 0.0884 MHz, a 176.8 kHz band. The 50 kHz samples inside it
    // are 14.15–14.25, so snapping to samples would read 100 kHz; the
    // straight segments the chart draws cross 2:1 at 174 kHz (VSWR is convex
    // in f, so the chord crosses a little inside the true curve).
    const { container } = render(
      <SweepChart {...BASE} sweep={notch(FREQS, 50)} />,
    );
    const c = canvasOf(container);
    expect(c.dataset.bands).toBe("1");
    expect(c.dataset.readout).toBe("2:1 BW 174 kHz");
  });

  it("follows the threshold prop, on the S11 chart too", () => {
    const { container } = render(
      <SweepChart {...BASE} mode="gamma" sweep={notch(FREQS, 50)} swrThreshold={3} />,
    );
    expect(canvasOf(container).dataset.readout).toMatch(/^3:1 BW 2\d\d kHz$/);
  });

  it("no sweep, no readout", () => {
    const { container } = render(<SweepChart {...BASE} r={50} x={0} />);
    expect(canvasOf(container).dataset.readout).toBe("");
  });
});

describe("the axis popover", () => {
  it("opens from the y axis and picks a preset, Auto or a threshold", () => {
    const onAxisChange = vi.fn();
    const onThresholdChange = vi.fn();
    render(
      <SweepChart
        {...BASE}
        sweep={notch(FREQS)}
        onAxisChange={onAxisChange}
        onThresholdChange={onThresholdChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "VSWR range and SWR threshold" }));
    const dialog = screen.getByRole("dialog", { name: "VSWR range" });
    expect(dialog).toBeTruthy();
    expect(screen.getByRole("button", { name: "Auto" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "1–3" }));
    expect(onAxisChange).toHaveBeenLastCalledWith({ kind: "fixed", lo: 1, hi: 3 });
    // The custom max: typed into the second field, against the drawn floor.
    const [, maxField, threshold] = screen.getAllByRole("spinbutton");
    fireEvent.change(maxField, { target: { value: "4" } });
    expect(onAxisChange).toHaveBeenLastCalledWith({ kind: "fixed", lo: 1, hi: 4 });
    fireEvent.change(threshold, { target: { value: "1.5" } });
    expect(onThresholdChange).toHaveBeenLastCalledWith(1.5);
    // A threshold outside 1.05–20 is refused, not clamped silently.
    fireEvent.change(threshold, { target: { value: "0.5" } });
    expect(onThresholdChange).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("the S11 chart offers floors", () => {
    const onAxisChange = vi.fn();
    render(<SweepChart {...BASE} mode="gamma" sweep={notch(FREQS)} onAxisChange={onAxisChange} />);
    fireEvent.click(screen.getByRole("button", { name: "S11 range and SWR threshold" }));
    fireEvent.click(screen.getByRole("button", { name: "-20 dB" }));
    expect(onAxisChange).toHaveBeenLastCalledWith({ kind: "fixed", lo: -20, hi: 0 });
  });

  it("a thumbnail (no callbacks) has no axis control", () => {
    render(<SweepChart {...BASE} sweep={notch(FREQS)} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
