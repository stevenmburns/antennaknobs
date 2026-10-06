// AK 0.97.1: "We need the impedance feedback on the Smith chart so we can
// see that it is doing something." During a band run the Smith chart shows
// one live marker per band, from every progress frame's `bands[]`: its MHz,
// its colour, a short fading trail, and the bright ring on the worst band.
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SmithChart } from "../components/charts/SmithChart";
import { feedColor } from "../components/charts/palette";
import { reflectionCoefficient } from "../lib/format";
import { BAND_TRAIL_LEN, nextBandMarks, type BandMarks } from "../lib/optBands";

type Rec = {
  index: number;
  freq_mhz: number;
  z0_ohms: number;
  z_re: number | null;
  z_im: number | null;
};
const rec = (index: number, freq: number, re: number | null, im: number | null, z0 = 50): Rec => ({
  index,
  freq_mhz: freq,
  z0_ohms: z0,
  z_re: re,
  z_im: im,
});

describe("nextBandMarks: the per-band markers from progress frames", () => {
  it("one marker per band, its trail the band's last positions, capped", () => {
    let m: BandMarks | null = null;
    for (let i = 0; i < BAND_TRAIL_LEN + 3; i++) {
      m = nextBandMarks(m, {
        bands: [rec(0, 7.2, 50 + i, 10), rec(1, 3.6, 30, -100 + i)],
        worst_band: 1,
      });
    }
    expect(m!.bands.map((b) => b.freq_mhz)).toEqual([7.2, 3.6]);
    expect(m!.worst).toBe(1);
    const b0 = m!.bands[0];
    expect(b0.trail).toHaveLength(BAND_TRAIL_LEN);
    // Oldest first, the newest last: the head is the latest frame's Z.
    expect(b0.trail.at(-1)).toEqual({ re: 50 + BAND_TRAIL_LEN + 2, im: 10 });
    expect(b0.trail[0]).toEqual({ re: 53, im: 10 });
  });

  it("a band absent from a frame (a sequential sub-step) keeps its position", () => {
    let m = nextBandMarks(null, { bands: [rec(0, 7.2, 50, 0), rec(1, 3.6, 30, -40)], worst_band: 0 });
    m = nextBandMarks(m, { bands: [rec(0, 7.2, 60, 5)], worst_band: 0 });
    expect(m!.bands[1].trail).toEqual([{ re: 30, im: -40 }]);
    expect(m!.bands[1].live).toBe(true);
    expect(m!.bands[0].trail).toEqual([
      { re: 50, im: 0 },
      { re: 60, im: 5 },
    ]);
  });

  it("a null Z draws nothing until a reading returns, and the trail is kept", () => {
    let m = nextBandMarks(null, { bands: [rec(0, 1.8, 40, 20)] });
    m = nextBandMarks(m, { bands: [rec(0, 1.8, null, null)] });
    expect(m!.bands[0].live).toBe(false);
    expect(m!.bands[0].trail).toEqual([{ re: 40, im: 20 }]);
    m = nextBandMarks(m, { bands: [rec(0, 1.8, 45, 15)] });
    expect(m!.bands[0].live).toBe(true);
    expect(m!.bands[0].trail).toHaveLength(2);
  });

  it("a repeated Z (a cache hit) does not stretch the trail", () => {
    let m = nextBandMarks(null, { bands: [rec(0, 7.2, 50, 0)] });
    m = nextBandMarks(m, { bands: [rec(0, 7.2, 50, 0)] });
    expect(m!.bands[0].trail).toHaveLength(1);
  });

  it("a frame without bands (a single-frequency run) changes nothing", () => {
    expect(nextBandMarks(null, {})).toBeNull();
    const m = nextBandMarks(null, { bands: [rec(0, 7.2, 50, 0)] });
    expect(nextBandMarks(m, {})).toBe(m);
  });
});

// --------------------------------------------------------- drawn on the chart

type ArcCall = { x: number; y: number; radius: number; fillStyle: string; strokeStyle: string; lineWidth: number };
type TextCall = { text: string; x: number; y: number; fillStyle: string };

function recordingContext() {
  const arcs: ArcCall[] = [];
  const texts: TextCall[] = [];
  const state = { fillStyle: "", strokeStyle: "", lineWidth: 1, font: "" };
  const ctx = new Proxy(
    {
      arc(x: number, y: number, radius: number) {
        arcs.push({ x, y, radius, fillStyle: state.fillStyle, strokeStyle: state.strokeStyle, lineWidth: state.lineWidth });
      },
      fillText(text: string, x: number, y: number) {
        texts.push({ text, x, y, fillStyle: state.fillStyle });
      },
      measureText() {
        return { width: 0 };
      },
    } as Record<string, unknown>,
    {
      get(t, k: string) {
        if (k in state) return state[k as keyof typeof state];
        if (k in t) return t[k];
        return () => {};
      },
      set(_t, k: string, v) {
        (state as Record<string, unknown>)[k] = v;
        return true;
      },
    },
  );
  return { ctx: ctx as unknown as CanvasRenderingContext2D, arcs, texts };
}

const SIZE = 220;
const CX = SIZE / 2;
const CY = SIZE / 2;
const R = SIZE / 2 - 10;
function at(re: number, im: number, z0: number) {
  const g = reflectionCoefficient(re, im, z0);
  return { x: CX + g.gRe * R, y: CY - g.gIm * R };
}

function draw(marks: BandMarks | null, extra: Partial<React.ComponentProps<typeof SmithChart>> = {}) {
  const rc = recordingContext();
  HTMLCanvasElement.prototype.getContext = (() => rc.ctx) as unknown as HTMLCanvasElement["getContext"];
  const { container } = render(
    <SmithChart
      r={30}
      x={-140}
      z0={50}
      size={SIZE}
      sweep={null}
      paramSweep={null}
      measured={null}
      measFreqMhz={7.2}
      running={false}
      paramSweepRunning={false}
      multiFeed={false}
      trial
      trialBands={marks}
      {...extra}
    />,
  );
  return { ...rc, canvas: container.querySelector("canvas")! };
}

const near = (arcs: ArcCall[], p: { x: number; y: number }) =>
  arcs.filter((a) => Math.abs(a.x - p.x) < 1e-6 && Math.abs(a.y - p.y) < 1e-6);

describe("the Smith chart draws a band run's markers", () => {
  const MARKS: BandMarks = {
    worst: 1,
    bands: [
      { index: 0, freq_mhz: 7.2, z0_ohms: 50, live: true, trail: [{ re: 56, im: 21 }, { re: 60, im: 30 }, { re: 70, im: 50 }] },
      { index: 1, freq_mhz: 3.6, z0_ohms: 50, live: true, trail: [{ re: 31, im: -142 }, { re: 45, im: -90 }] },
      // A band in a 75 ohm reference: normalised to ITS z0, not the chart's.
      { index: 2, freq_mhz: 1.8, z0_ohms: 75, live: true, trail: [{ re: 75, im: 0 }] },
    ],
  };

  it("one head ring per band in its colour, labelled with its MHz; the worst bright", () => {
    const { arcs, texts, canvas } = draw(MARKS);
    const h0 = near(arcs, at(70, 50, 50)).find((a) => a.radius >= 4)!;
    expect(h0.strokeStyle).toBe(feedColor(0, 0.6));
    expect(h0.radius).toBe(4);
    const h1 = near(arcs, at(45, -90, 50)).find((a) => a.radius >= 4)!;
    expect(h1.strokeStyle).toBe(feedColor(1, 0.85));
    expect(h1.radius).toBe(5);
    expect(h1.lineWidth).toBe(2);
    // 75 + j0 against its own 75 ohm is the centre.
    expect(near(arcs, { x: CX, y: CY }).some((a) => a.strokeStyle === feedColor(2, 0.6))).toBe(true);
    expect(texts.map((t) => t.text)).toEqual(expect.arrayContaining(["7.2", "3.6", "1.8"]));
    expect(texts.find((t) => t.text === "3.6")!.fillStyle).toBe(feedColor(1, 0.95));
    expect(canvas.dataset.bands).toBe("7.2:3,3.6:2*,1.8:1");
  });

  it("the worst band's ring is painted last", () => {
    const { arcs } = draw(MARKS);
    const heads = arcs.filter((a) => a.radius >= 4 && a.strokeStyle.startsWith("rgba"));
    expect(heads.at(-1)!.strokeStyle).toBe(feedColor(1, 0.85));
  });

  it("each trail fades towards its oldest position", () => {
    const { arcs } = draw(MARKS);
    const t0 = near(arcs, at(56, 21, 50)).find((a) => a.radius === 2.5)!;
    const t1 = near(arcs, at(60, 30, 50)).find((a) => a.radius === 2.5)!;
    const alpha = (c: string) => Number(c.match(/([\d.]+)\)$/)![1]);
    expect(alpha(t0.fillStyle)).toBeLessThan(alpha(t1.fillStyle));
  });

  it("a band with no reading draws nothing", () => {
    const off: BandMarks = { worst: 0, bands: [{ ...MARKS.bands[0], live: false }] };
    const { arcs, texts, canvas } = draw(off);
    expect(near(arcs, at(70, 50, 50))).toHaveLength(0);
    expect(texts.map((t) => t.text)).not.toContain("7.2");
    expect(canvas.dataset.bands).toBe("7.2:3:off*");
  });

  it("the band markers replace the single trial ring", () => {
    const { arcs } = draw(MARKS);
    expect(near(arcs, at(30, -140, 50))).toHaveLength(0);
    const single = draw(null);
    expect(near(single.arcs, at(30, -140, 50))).toHaveLength(1);
    expect(single.canvas.dataset.bands).toBe("");
  });

  it("after the run (no trial point) the markers stay beside the settled dot", () => {
    const { arcs } = draw(MARKS, { trial: false });
    expect(near(arcs, at(45, -90, 50)).some((a) => a.radius === 5)).toBe(true);
    // The settled solve's filled dot is drawn too.
    expect(near(arcs, at(30, -140, 50))).toHaveLength(1);
  });
});

describe("the band run's pace (AK 0.97.1)", () => {
  it("formats wall time per solved point", async () => {
    const { fmtPace } = await import("../components/session/OptBands");
    expect(fmtPace(150)).toBe("0.15 s/eval");
    expect(fmtPace(5200)).toBe("5.2 s/eval");
    expect(fmtPace(12400)).toBe("12 s/eval");
  });

  it("shows beside the per-band progress while running, and not after", async () => {
    const { BandsReadout } = await import("../components/session/OptBands");
    const progress = {
      n_evals: 32,
      n_solves: 30,
      params: {},
      objective: 5,
      objective_worst: 5,
      metrics: { z_in_re: 30, z_in_im: -40, z0_ohms: 50, swr: 5 },
      bands: [{ ...rec(0, 7.2, 50, 0), objective: "swr", feed: 0, swr: 1.2, residual: null, value: 1.2 }],
    };
    const { rerender } = render(
      <BandsReadout running progress={progress} result={null} error={null} paceMs={5200} />,
    );
    expect(screen.getByText("5.2 s/eval")).toBeTruthy();
    rerender(<BandsReadout running={false} progress={progress} result={null} error={null} paceMs={5200} />);
    expect(screen.queryByText("5.2 s/eval")).toBeNull();
  });
});

describe("useOptimizer keeps a band run's markers until the next edit", () => {
  it("through the write-back, even knob by knob; an edit clears them", async () => {
    const { renderHook, act, waitFor } = await import("@testing-library/react");
    const { vi } = await import("vitest");
    const { useOptimizer } = await import("../components/session/useOptimizer");
    const frame = (n: number) =>
      `event: progress\ndata: ${JSON.stringify({
        n_evals: n,
        n_solves: n,
        params: {},
        objective: 3,
        objective_worst: 3,
        worst_band: 1,
        metrics: { z_in_re: 40, z_in_im: 10, z0_ohms: 50, swr: 3 },
        bands: [
          { ...rec(0, 7.2, 50 + n, 10), objective: "swr", feed: 0, swr: 2, residual: null, value: 2 },
          { ...rec(1, 3.6, 30, -40 + n), objective: "swr", feed: 0, swr: 3, residual: null, value: 3 },
        ],
      })}\n\n`;
    const result = { objective: "bands", params: { a: 2, b: 5 }, objective_before: 4, objective_after: 3,
      metrics_before: { z_in_re: 1, z_in_im: 0, z0_ohms: 50, swr: 4 },
      metrics_after: { z_in_re: 1, z_in_im: 0, z0_ohms: 50, swr: 3 }, n_evals: 3, improved: true };
    const body = [frame(1), frame(2), frame(3), `event: result\ndata: ${JSON.stringify(result)}\n\n`].join("");
    vi.stubGlobal("fetch", async () => ({
      headers: { get: () => "text/event-stream" },
      body: new ReadableStream<Uint8Array>({
        start(c) {
          c.enqueue(new TextEncoder().encode(body));
          c.close();
        },
      }),
    }));
    try {
      let values: Record<string, number> = { a: 1, b: 1, c: 7 };
      const hook = renderHook(
        ({ v }: { v: Record<string, number> }) =>
          useOptimizer({
            geometry: "deck.x",
            currentValues: v,
            currentValuesKey: JSON.stringify(v),
            currentSchema: [],
            backend: "momwire",
            designFreq: 7.2,
            measFreq: 7.2,
            autoSim: true,
            active: true,
            buildRequest: () => ({ geometry: "deck.x" }) as never,
            // NOT batched: each knob of the write-back is its own render.
            setParamAtPath: (path, val) => {
              values = { ...values, [String(path[0])]: val as number };
              hook.rerender({ v: values });
            },
          }),
        { initialProps: { v: values } },
      );
      act(() =>
        hook.result.current.setKnobOpt({
          "deck.x": {
            a: { vary: true, optMin: 0, optMax: 9, dispMin: 0, dispMax: 9, step: 1 },
            b: { vary: true, optMin: 0, optMax: 9, dispMin: 0, dispMax: 9, step: 1 },
          },
        }),
      );
      act(() => hook.result.current.setOptBands([7.2, 3.6]));
      act(() => hook.result.current.setOptEnabled(true));
      await waitFor(() => expect(hook.result.current.optResult).not.toBeNull(), { timeout: 3000 });
      await waitFor(() => expect(hook.result.current.optRunning).toBe(false));
      expect(values).toEqual({ a: 2, b: 5, c: 7 });
      const marks = hook.result.current.optBandMarks!;
      expect(marks.worst).toBe(1);
      expect(marks.bands.map((b) => [b.freq_mhz, b.trail.length])).toEqual([
        [7.2, 3],
        [3.6, 3],
      ]);
      // An edit (an unmarked knob, with Optimize off so nothing re-runs).
      act(() => hook.result.current.setOptEnabled(false));
      values = { ...values, c: 8 };
      hook.rerender({ v: values });
      expect(hook.result.current.optBandMarks).toBeNull();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
