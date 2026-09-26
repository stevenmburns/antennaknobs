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
import { gammaMagFromZ, vswrFromGammaMag } from "../lib/math";
import { SWEEP_SCORE_BAND, sweepProjections } from "../lib/refine";
import { DEFAULT_AXES, type SweepAxisChoice, type SweepMode } from "../lib/sweepAxis";

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
  it("defaults: VSWR on 1–∞, S11 on Auto fitting the dip (floor −40 for a 1.1 dip)", () => {
    const v = render(<SweepChart {...BASE} sweep={notch(FREQS)} />);
    expect(canvasOf(v.container).dataset.axis).toBe("reciprocal");
    expect(domainOf(canvasOf(v.container))).toEqual({ lo: 0, hi: 1 });
    // The same instance switched to S11, as the stage does.
    v.rerender(<SweepChart {...BASE} mode="gamma" sweep={notch(FREQS)} />);
    // |Γ| = 5/105 ⇒ −26.4 dB, which clears −30 by less than 5 dB ⇒ −40.
    expect(domainOf(canvasOf(v.container))).toEqual({ lo: -40, hi: 0 });
  });

  it("a VSWR Auto (an old profile's) draws as 1–∞", () => {
    const { container } = render(<SweepChart {...BASE} sweep={notch(FREQS)} axis={{ kind: "auto" }} />);
    expect(canvasOf(container).dataset.axis).toBe("reciprocal");
    expect(domainOf(canvasOf(container))).toEqual({ lo: 0, hi: 1 });
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
    // Thresholds included: under S11's Auto the threshold moves the range
    // (a tight 1.02:1, −40.1 dB, forces a −50 floor).
    const cases: [SweepMode, SweepAxisChoice, number][] = [
      ["vswr", { kind: "fixed", lo: 1, hi: 1.5 }, 2],
      ["vswr", { kind: "fixed", lo: 1, hi: 2 }, 3],
      // The compressed scale: samples sit at 1 − 1/SWR on a fixed 0…1.
      ["vswr", { kind: "reciprocal" }, 2],
      ["gamma", { kind: "auto" }, 2],
      ["gamma", { kind: "auto" }, 1.02],
      ["gamma", { kind: "fixed", lo: -20, hi: 0 }, 2],
    ];
    const seen = new Set<string>();
    let offPlot = false;
    for (const [mode, axis, threshold] of cases) {
      const sweep = notch(FREQS);
      const { container, unmount } = render(
        <SweepChart
          {...BASE}
          mode={mode}
          sweep={sweep}
          axis={axis}
          swrThreshold={threshold}
        />,
      );
      const c = canvasOf(container);
      const d = domainOf(c);
      const ys = (c.dataset.yValues ?? "").split(",").map(Number);
      const [proj] = sweepProjections(
        sweep,
        50,
        { vswr: mode === "vswr", gamma: mode === "gamma", smith: false },
        { ...DEFAULT_AXES, [mode]: axis },
        threshold,
      );
      seen.add(`${mode}:${d.lo},${d.hi}`);
      // Worked out here, not through the library: 1 − 1/SWR on the
      // compressed scale, the linear map onto the domain otherwise, NOT
      // clamped — the chart draws its trail through these and clips it.
      const want = (y: number) =>
        axis.kind === "reciprocal" ? 1 - 1 / y : (y - d.lo) / (d.hi - d.lo);
      // The planner scores the same heights, saturated past the band.
      const [bLo, bHi] = SWEEP_SCORE_BAND;
      const band = (v: number) => Math.max(bLo, Math.min(bHi, v));
      // The height the chart DRAWS each sample at, published.
      const drawn = (c.dataset.yFrac ?? "").split(",").map(Number);
      expect(drawn).toHaveLength(ys.length);
      ys.forEach((y, i) => {
        expect(drawn[i]).toBeCloseTo(want(y), 3);
        expect(proj[i].y).toBeCloseTo(band(want(y)), 3);
      });
      // This sweep does leave the plot on the linear ranges, so the pin
      // covers off-plot heights, not just on-plot ones.
      if (axis.kind !== "reciprocal") offPlot ||= drawn.some((v) => v > 1 || v < 0);
      unmount();
    }
    // The threshold really moved S11's Auto range (else this pins nothing).
    expect(seen.has("gamma:-40,0") && seen.has("gamma:-50,0")).toBe(true);
    expect(seen.has("vswr:0,1")).toBe(true); // the compressed scale ran
    expect(offPlot).toBe(true);
  });
});

describe("S11's Auto deepens while live and re-fits once the inputs settle", () => {
  // S11 values: a marker at R = 200 is −4.4 dB (floor −10); R = 55 is
  // −26.4 dB (floor −40); a notch with R = 150 at its dip bottoms at −6 dB
  // (floor −20).
  const S11: Props = { ...BASE, mode: "gamma" };

  it("a drag into a deep match deepens the floor; it comes back only after the dwell", () => {
    vi.useFakeTimers();
    const v = render(<SweepChart {...S11} sweep={null} r={200} x={0} />);
    const c = () => canvasOf(v.container);
    expect(domainOf(c()).lo).toBe(-10);
    v.rerender(<SweepChart {...S11} sweep={null} r={55} x={0} />);
    expect(domainOf(c()).lo).toBe(-40);
    // The drag comes back to a poor match: still −40, never shrinking under
    // the hand...
    v.rerender(<SweepChart {...S11} sweep={null} r={200} x={0} />);
    expect(domainOf(c()).lo).toBe(-40);
    act(() => vi.advanceTimersByTime(AUTO_SETTLE_MS - 50));
    expect(domainOf(c()).lo).toBe(-40);
    // ...until the inputs have been still for the dwell.
    act(() => vi.advanceTimersByTime(100));
    expect(domainOf(c()).lo).toBe(-10);
  });

  it("holds while a sweep streams in, then re-fits to the finished sweep", () => {
    vi.useFakeTimers();
    const v = render(<SweepChart {...S11} sweep={null} r={55} x={0} />);
    const c = () => canvasOf(v.container);
    expect(domainOf(c()).lo).toBe(-40);
    v.rerender(
      <SweepChart {...S11} sweep={notch(FREQS.slice(0, 12), 150)} running r={55} x={0} />,
    );
    expect(domainOf(c()).lo).toBe(-40);
    act(() => vi.advanceTimersByTime(AUTO_SETTLE_MS * 2));
    expect(domainOf(c()).lo).toBe(-40); // still running
    v.rerender(<SweepChart {...S11} sweep={notch(FREQS, 150)} r={55} x={0} />);
    expect(domainOf(c()).lo).toBe(-40); // the last point just landed
    act(() => vi.advanceTimersByTime(AUTO_SETTLE_MS));
    expect(domainOf(c()).lo).toBe(-20);
  });

  it("fits the marker, not a sweep still streaming in", () => {
    // A streaming sweep's first points are just the band edge; fitting them
    // moved the axis until the settle. Here they are a deep match.
    vi.useFakeTimers();
    const v = render(<SweepChart {...S11} sweep={null} r={200} x={0} />);
    const c = () => canvasOf(v.container);
    expect(domainOf(c()).lo).toBe(-10);
    const deepEdge: SweepData = { freqs_mhz: [13.7, 13.75, 13.8], z_re: [55, 55, 55], z_im: [0, 0, 0] };
    v.rerender(<SweepChart {...S11} sweep={deepEdge} running r={200} x={0} />);
    expect(domainOf(c()).lo).toBe(-10);
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
  it("opens from the y axis and picks a preset, a custom range or a threshold", () => {
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
    // VSWR's default is 1–∞, and it has no Auto.
    expect(screen.getByRole("button", { name: "1–∞" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.queryByRole("button", { name: "Auto" })).toBeNull();
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
    // S11 keeps its Auto (its default), and has no 1–∞.
    expect(screen.getByRole("button", { name: "Auto" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "-20 dB" }));
    expect(onAxisChange).toHaveBeenLastCalledWith({ kind: "fixed", lo: -20, hi: 0 });
  });

  it("a thumbnail (no callbacks) has no axis control", () => {
    render(<SweepChart {...BASE} sweep={notch(FREQS)} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("the compressed 1–∞ VSWR scale (1 − 1/SWR)", () => {
  // A recording 2-D context: what the chart actually drew.
  function recordingContext() {
    const texts: { text: string; y: number }[] = [];
    const lines: { y0: number; y1: number; dashed: boolean }[] = [];
    let dashed = false;
    let from: { x: number; y: number } | null = null;
    const ctx = new Proxy(
      {},
      {
        get: (_t, prop) => {
          if (prop === "fillText")
            return (text: string, _x: number, y: number) => texts.push({ text, y });
          if (prop === "setLineDash") return (d: number[]) => (dashed = d.length > 0);
          if (prop === "moveTo") return (x: number, y: number) => (from = { x, y });
          if (prop === "lineTo")
            return (_x: number, y: number) => {
              if (from) lines.push({ y0: from.y, y1: y, dashed });
            };
          if (prop === "measureText") return () => ({ width: 10 });
          return () => undefined;
        },
        set: () => true,
      },
    ) as unknown as CanvasRenderingContext2D;
    return { ctx, texts, lines };
  }

  it("draws SWR-labelled ticks with ∞ on top, the 2:1 line half way, nothing pegged", () => {
    const rec = recordingContext();
    const real = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = (() => rec.ctx) as unknown as HTMLCanvasElement["getContext"];
    try {
      // R = 50 with X swinging to ±200 Ω: the band edges are SWR ~18, which
      // a 1–10 scale pegs.
      const sweep = notch(FREQS, 50);
      const { container } = render(
        <SweepChart {...BASE} size={236} sweep={sweep} axis={{ kind: "reciprocal" }} />,
      );
      const c = canvasOf(container);
      expect(c.dataset.axis).toBe("reciprocal");
      expect(domainOf(c)).toEqual({ lo: 0, hi: 1 });
      expect(c.dataset.ticks).toBe("1,1.5,2,3,5,10,∞");
      expect(c.dataset.readout).toBe("2:1 BW 174 kHz");
      // Plot box: marginT 16, marginB 20 ⇒ plotH 200, y = 16 + 200·(1 − f).
      const yAt = (f: number) => 16 + 200 * (1 - f);
      const label = (t: string) => rec.texts.find((x) => x.text === t);
      expect(label("∞")!.y).toBeCloseTo(yAt(1) + 3, 6);
      expect(label("2")!.y).toBeCloseTo(yAt(0.5) + 3, 6);
      expect(label("3")!.y).toBeCloseTo(yAt(2 / 3) + 3, 6);
      expect(label("10")!.y).toBeCloseTo(yAt(0.9) + 3, 6);
      // The dashed 2:1 threshold line at 1 − 1/2 = ½.
      const dashes = rec.lines.filter((l) => l.dashed && l.y0 === l.y1);
      expect(dashes.some((l) => Math.abs(l.y0 - yAt(0.5)) < 1e-6)).toBe(true);
      // Every sample is on the plot: none drawn at the top edge (a peg).
      const ys = (c.dataset.yValues ?? "").split(",").map(Number);
      expect(Math.max(...ys)).toBeGreaterThan(10);
      const fr = (c.dataset.yFrac ?? "").split(",").map(Number);
      expect(Math.max(...fr)).toBeLessThan(1);
    } finally {
      HTMLCanvasElement.prototype.getContext = real;
    }
  });

  it("is outside Auto's hold: a live drag never widens it", () => {
    vi.useFakeTimers();
    const axis: SweepAxisChoice = { kind: "reciprocal" };
    const v = render(<SweepChart {...BASE} sweep={notch(FREQS)} axis={axis} />);
    v.rerender(<SweepChart {...BASE} sweep={null} r={2000} x={0} axis={axis} />);
    expect(domainOf(canvasOf(v.container))).toEqual({ lo: 0, hi: 1 });
    act(() => vi.advanceTimersByTime(AUTO_SETTLE_MS * 2));
    expect(domainOf(canvasOf(v.container))).toEqual({ lo: 0, hi: 1 });
  });

  it("is offered on the VSWR popover only", () => {
    const onAxisChange = vi.fn();
    const v = render(<SweepChart {...BASE} sweep={notch(FREQS)} onAxisChange={onAxisChange} />);
    fireEvent.click(screen.getByRole("button", { name: "VSWR range and SWR threshold" }));
    fireEvent.click(screen.getByRole("button", { name: "1–∞" }));
    expect(onAxisChange).toHaveBeenLastCalledWith({ kind: "reciprocal" });
    v.unmount();
    render(<SweepChart {...BASE} mode="gamma" sweep={notch(FREQS)} onAxisChange={onAxisChange} />);
    fireEvent.click(screen.getByRole("button", { name: "S11 range and SWR threshold" }));
    expect(screen.queryByRole("button", { name: "1–∞" })).toBeNull();
  });
});

describe("the trail is clipped, not clamped, at the plot edge", () => {
  // Records the calls that matter: the clip rect and the stroked polyline.
  function recorder() {
    const calls: { op: string; args: number[] }[] = [];
    const ctx = new Proxy(
      {},
      {
        get: (_t, prop) => {
          if (prop === "measureText") return () => ({ width: 10 });
          return (...args: unknown[]) =>
            calls.push({ op: String(prop), args: args.filter((a): a is number => typeof a === "number") });
        },
        set: () => true,
      },
    ) as unknown as CanvasRenderingContext2D;
    return { ctx, calls };
  }

  function drawn(mode: "vswr" | "gamma", axis: SweepAxisChoice, sweep: SweepData) {
    const rec = recorder();
    const real = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = (() => rec.ctx) as unknown as HTMLCanvasElement["getContext"];
    try {
      render(<SweepChart {...BASE} mode={mode} size={236} sweep={sweep} axis={axis} />);
    } finally {
      HTMLCanvasElement.prototype.getContext = real;
    }
    // The trail: the moveTo/lineTo run that follows the clip.
    const clipAt = rec.calls.findIndex((c) => c.op === "clip");
    const rect = rec.calls.slice(0, clipAt).reverse().find((c) => c.op === "rect");
    const trail: number[] = [];
    for (let i = clipAt + 1; i < rec.calls.length; i++) {
      const c = rec.calls[i];
      if (c.op === "stroke") break;
      if (c.op === "moveTo" || c.op === "lineTo") trail.push(c.args[1]);
    }
    return { clipAt, rect, trail };
  }

  // Plot box at size 236: marginL 26, marginT 16, plotW 202, plotH 200.
  const yAt = (f: number) => 16 + 200 * (1 - f);

  it("VSWR: an off-range sample is drawn at its true height, and the stroke clipped to the plot", () => {
    const sweep = notch(FREQS, 50); // band edges reach SWR ~18
    const { clipAt, rect, trail } = drawn("vswr", { kind: "fixed", lo: 1, hi: 2 }, sweep);
    expect(clipAt).toBeGreaterThan(-1);
    expect(rect?.args).toEqual([26, 16, 202, 200]);
    const vs = sweep.freqs_mhz.map((_, i) =>
      vswrFromGammaMag(gammaMagFromZ(sweep.z_re[i], sweep.z_im[i], 50)),
    );
    expect(trail).toHaveLength(vs.length);
    // Sample 0 is SWR ~18 on a 1–2 range: 17 plot-heights above the top,
    // not pinned on the edge at y = 16.
    trail.forEach((y, i) => expect(y).toBeCloseTo(yAt(vs[i] - 1), 6));
    expect(trail[0]).toBeLessThan(16 - 1000);
  });

  it("S11: a sample below the floor is drawn below it, clipped, not flattened onto it", () => {
    // R = 50 at the notch: S11 hits the −60 dB math floor, far under −20.
    const sweep = notch(FREQS, 50);
    const { trail } = drawn("gamma", { kind: "fixed", lo: -20, hi: 0 }, sweep);
    expect(Math.max(...trail)).toBeGreaterThan(yAt(0) + 100);
  });
});
