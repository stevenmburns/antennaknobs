// The canvas charts' one scale (components/charts/chartScale.ts, AK#1757
// unit 6 / AK#1807): 1.25 on a laptop or desktop, 1 on a phone and in a
// thumbnail. A chart draws in a logical square of size / k under a k
// transform, so its type ramp, marks and margins grow together.
//
// jsdom loads no stylesheet, so `--chart-scale` is set on the root's inline
// style here (what styles.css's :root rule does in the app), and the charts'
// 2-D context is a recording stub: what the test reads is the transform the
// chart set and the fonts it asked for.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import {
  CHART_FONT,
  CHART_TYPE,
  ChartScaleContext,
  readChartScale,
  useChartScale,
} from "../components/charts/chartScale";
import { SmithChart } from "../components/charts/SmithChart";
import { SweepChart } from "../components/charts/SweepChart";
import { ZParamChart } from "../components/charts/ZParamChart";
import { ZParamStage } from "../components/results/ZParamStage";
import type { ParamSweepData, SweepData } from "../lib/api";
import { ZPARAM_PLOT_MARGIN } from "../lib/zparamLayout";

const KNOB: ParamSweepData = {
  param: "length_factor",
  label: "length factor",
  values: [0.9, 1.0, 1.1],
  z_re: [55, 70, 88],
  z_im: [-40, 0, 45],
  z_re_extrap: null,
  z_im_extrap: null,
};

const SWEEP = {
  freqs_mhz: [13.9, 14.0, 14.1],
  z_re: [40, 50, 60],
  z_im: [-20, 0, 20],
} as unknown as SweepData;

type Rec = { transforms: number[][]; fonts: string[] };

// Every method a chart calls is a no-op that records setTransform; `font`
// assignments are recorded; measureText answers a monospace width.
function recordingContext(): { ctx: CanvasRenderingContext2D; rec: Rec } {
  const rec: Rec = { transforms: [], fonts: [] };
  const props: Record<string, unknown> = {};
  const ctx = new Proxy(props, {
    get(target, key: string) {
      if (key in target) return target[key];
      if (key === "setTransform") return (...a: number[]) => rec.transforms.push(a);
      if (key === "measureText") return (s: string) => ({ width: s.length * 6 });
      if (key === "createLinearGradient" || key === "createRadialGradient")
        return () => ({ addColorStop() {} });
      if (key === "getLineDash") return () => [];
      return () => {};
    },
    set(target, key: string, v: unknown) {
      if (key === "font") rec.fonts.push(v as string);
      target[key] = v;
      return true;
    },
  }) as unknown as CanvasRenderingContext2D;
  return { ctx, rec };
}

function stubMedia(mobile: boolean) {
  vi.stubGlobal("matchMedia", () => ({
    matches: mobile,
    addEventListener() {},
    removeEventListener() {},
  }));
}

let rec: Rec;
beforeEach(() => {
  const r = recordingContext();
  rec = r.rec;
  HTMLCanvasElement.prototype.getContext = (() =>
    r.ctx) as unknown as typeof HTMLCanvasElement.prototype.getContext;
  document.documentElement.style.setProperty("--chart-scale", "1.25");
});
afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.style.removeProperty("--chart-scale");
  HTMLCanvasElement.prototype.getContext = (() =>
    null) as unknown as typeof HTMLCanvasElement.prototype.getContext;
});

const dpr = () => window.devicePixelRatio || 1;
const lastScale = () => rec.transforms[rec.transforms.length - 1]?.[0] / dpr();

describe("reading --chart-scale", () => {
  it("reads the stylesheet's value, and 1 for none or nonsense", () => {
    expect(readChartScale()).toBe(1.25);
    document.documentElement.style.setProperty("--chart-scale", "banana");
    expect(readChartScale()).toBe(1);
    document.documentElement.style.setProperty("--chart-scale", "40");
    expect(readChartScale()).toBe(1);
    document.documentElement.style.removeProperty("--chart-scale");
    expect(readChartScale()).toBe(1);
  });

  it("desktop reads it; a phone is 1 whatever it says; a thumbnail pins 1", () => {
    expect(renderHook(() => useChartScale()).result.current).toBe(1.25);
    const thumb = ({ children }: { children: ReactNode }) => (
      <ChartScaleContext.Provider value={1}>{children}</ChartScaleContext.Provider>
    );
    expect(renderHook(() => useChartScale(), { wrapper: thumb }).result.current).toBe(1);
    stubMedia(true);
    expect(renderHook(() => useChartScale()).result.current).toBe(1);
  });
});

describe("the charts draw on the scale", () => {
  const zparam = () => (
    <ZParamChart
      data={KNOB}
      param={KNOB.param}
      label={KNOB.label}
      total={3}
      currentValue={1.0}
      liveR={70}
      liveX={0}
      size={400}
      running={false}
      xLog={false}
      onAxisChange={() => {}}
    />
  );

  it("the knob sweep: a k transform, the ramp's fonts, axis buttons in its margins", () => {
    const { container } = render(zparam());
    expect(lastScale()).toBeCloseTo(1.25);
    expect(rec.fonts.length).toBeGreaterThan(0);
    const ramp = new Set(Object.values(CHART_FONT));
    expect(rec.fonts.filter((f) => !ramp.has(f))).toEqual([]);
    const btn = container.querySelector(".zparam-axis-btn-r") as HTMLElement;
    expect(btn.style.top).toBe(`${ZPARAM_PLOT_MARGIN.t * 1.25}px`);
    expect(btn.style.height).toBe(
      `${400 - (ZPARAM_PLOT_MARGIN.t + ZPARAM_PLOT_MARGIN.b) * 1.25}px`,
    );
  });

  it("the knob sweep on a phone: unscaled, and lines only", () => {
    stubMedia(true);
    const { container } = render(zparam());
    expect(lastScale()).toBeCloseTo(1);
    expect(container.querySelector("canvas.zparam")?.getAttribute("data-dot-r")).toBe("0");
  });

  it("the Smith and sweep charts take the same transform", () => {
    render(
      <SmithChart
        r={50}
        x={0}
        z0={50}
        size={300}
        sweep={SWEEP}
        paramSweep={null}
        measured={null}
        measFreqMhz={14}
        running={false}
        paramSweepRunning={false}
        multiFeed={false}
      />,
    );
    expect(lastScale()).toBeCloseTo(1.25);
    rec.transforms.length = 0;
    render(
      <SweepChart
        mode="vswr"
        r={50}
        x={0}
        z0={50}
        size={300}
        sweep={SWEEP}
        measFreqMhz={14}
        running={false}
        multiFeed={false}
      />,
    );
    expect(lastScale()).toBeCloseTo(1.25);
  });

  it("a thumbnail's chart draws at 1", () => {
    render(<ChartScaleContext.Provider value={1}>{zparam()}</ChartScaleContext.Provider>);
    expect(lastScale()).toBeCloseTo(1);
  });

  it("the stage pins its readout inside the scaled margins", () => {
    const { container } = render(
      <ZParamStage size={400} fallbackHead={40} header={null} chart={() => null} />,
    );
    const plot = container.querySelector(".zparam-plot") as HTMLElement;
    expect(plot.style.getPropertyValue("--zparam-plot-l")).toBe(
      `${ZPARAM_PLOT_MARGIN.l * 1.25}px`,
    );
  });

  it("the ramp: ticks under labels, readouts at least labels", () => {
    expect(CHART_TYPE.tick).toBeLessThan(CHART_TYPE.label);
    expect(CHART_TYPE.readout).toBeGreaterThanOrEqual(CHART_TYPE.label);
  });
});
