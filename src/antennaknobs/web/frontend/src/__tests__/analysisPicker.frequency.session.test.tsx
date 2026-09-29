// A frequency analysis picked in the analysis chart's picker, through a real
// <DesignSession> (AK#1757, sweep-framework steps 4 and 5):
//   - picking one draws it IN the chart (step 5 unit 2), on its first view,
//     from the chart's own frequency sweep over the analysis's range, with
//     the analysis's SWR scale and threshold; nothing goes to /param_sweep,
//     and the session is not switched to another view. Step 4 handed off to
//     the standalone VSWR view and set the session's sweep range (the dial's
//     travel) and the viewer's saved VSWR scale; the chart touches neither;
//   - picking one whose range is the deck's own sweeps the file's grid;
//   - a knob analysis still goes to /param_sweep, in the Z-vs-parameter view.
import { describe, it, expect, afterEach, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import {
  HARNESS_EXAMPLE,
  mountReady,
  stageChart,
  sweepBaseDone,
  untilDom,
} from "./designSessionHarness";

vi.setConfig({ testTimeout: 20_000 });

const knob: SchemaParamSpec = {
  name: "base",
  label: "Height",
  default: 7,
  kind: "float",
  min: 1,
  max: 16,
  step: 0.5,
  precision: 1,
  unit: "m",
  visible_when: null,
};

// E4's deck as /examples serves it: the Generator sweep, 14.0-14.35 MHz by
// 0.025 (15 points).
const FILE_RANGE = { lo: 14, hi: 14.35, spacing: "lin", step: 0.025, source: "file" } as const;
const DECK: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  bands: [
    { key: "14.175 MHz", label: "14.175 MHz", freq_mhz: 14.175, min_mhz: 14, max_mhz: 14.35 },
  ],
  default_freq: 14.175,
  has_design_freq: false,
  meas_freq_range_mhz: [14, 14.35],
  sweep_range: FILE_RANGE,
  param_schema: [knob],
};

const HEIGHT_VALUES = Array.from({ length: 37 }, (_, i) => 2 + 0.5 * i);

const frequencyEntry = (name: string, workbench: Record<string, unknown>) => ({
  name,
  summary: `frequency (freq); 1 curve; views Swr`,
  code: "an.band_swr()",
  problems: [],
  workbench: { runs: true, kind: "frequency", note: null, views: ["Swr"], ...workbench },
});

const ANALYSES = {
  geometry: DECK.name,
  analyses: [
    // E4: the deck's own range, EZNEC's ρ scale.
    frequencyEntry("band SWR", {
      range: FILE_RANGE,
      level: "file",
      points: null,
      swr: { scale: "rho", threshold: 2 },
    }),
    // A range of its own, a tighter threshold, the 1 − 1/SWR scale.
    frequencyEntry("wide SWR", {
      range: { lo: 13.9, hi: 14.5, spacing: "lin", points: 25, source: "design" },
      level: "analysis",
      points: 25,
      swr: { scale: "reciprocal", threshold: 1.5 },
    }),
    {
      name: "height",
      summary: "height (base) 2..20, 37 points; 1 curve; views Rx",
      code: 'an.Analysis("height", an.Sweep(an.HEIGHT, 2, 20, points=37))',
      problems: [],
      workbench: { runs: true, kind: "knob", param: "base", values: HEIGHT_VALUES, log: false, note: null },
    },
  ],
};

function ndjson(lines: string[]): Response {
  const chunks = [new TextEncoder().encode(lines.join("\n") + "\n")];
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: async () =>
          chunks.length > 0 ? { done: false, value: chunks.shift() } : { done: true, value: undefined },
      }),
    },
  } as unknown as Response;
}

async function mount() {
  const sweeps: number[][] = [];
  const paramSweeps: { param: string; values: number[] }[] = [];
  const r = await mountReady({
    examples: [DECK],
    pinned: ["antenna", "zparam", "vswr", "smith"],
    routes: {
      "/sweep": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}"));
        const freqs = body.freqs_mhz as number[];
        if (!body._refine) sweeps.push(freqs);
        // SWR 1 + 20·|f − 14.2|: below 1.5:1 for 50 kHz around 14.2 MHz.
        const lines = freqs.map((f) =>
          JSON.stringify({ freq_mhz: f, z_re: 50 * (1 + 20 * Math.abs(f - 14.2)), z_im: 0 }),
        );
        lines.push(JSON.stringify({ done: true }));
        return ndjson(lines);
      },
      "/param_sweep": (_url: string, init?: RequestInit) => {
        const b = JSON.parse(String(init?.body ?? "{}")) as { param: string; values: number[] };
        paramSweeps.push(b);
        const lines = b.values.map((v) =>
          JSON.stringify({ param: b.param, value: v, z_re: 60 + v, z_im: -30 + v, solver: "momwire" }),
        );
        lines.push(JSON.stringify({ done: true, solver: "momwire" }));
        return ndjson(lines);
      },
      "/analyses": () =>
        ({ ok: true, status: 200, json: async () => ANALYSES }) as unknown as Response,
    },
  });
  return { ...r, sweeps, paramSweeps };
}

function dial(): [number, number] {
  const k = screen.getByRole("slider", { name: "measurement frequency" });
  return [Number(k.getAttribute("aria-valuemin")), Number(k.getAttribute("aria-valuemax"))];
}

// Bring the Z-vs-parameter view up and return its analysis picker.
async function picker(container: HTMLElement) {
  fireEvent.click(container.querySelector(".thumbstrip canvas.zparam") as HTMLElement);
  return untilDom(
    () => screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null,
  );
}

const vswr = () => stageChart("canvas.sweep-vswr");

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a frequency analysis in the picker", () => {
  it("draws in the chart itself: its range, its SWR scale and threshold, its own sweep", async () => {
    const { container, sweeps, paramSweeps } = await mount();
    expect(dial()).toEqual([14, 14.35]);
    let select = await picker(container);
    // The frequency analyses are offered, not disabled.
    const wide = [...select.options].find((o) => o.value === "wide SWR")!;
    expect(wide.disabled).toBe(false);
    // The density sweep the view starts on lands first.
    await untilDom(() => paramSweeps.length > 0);
    const knobSweeps = paramSweeps.length;
    // The standalone VSWR view's scale, in the rail: the viewer's own.
    const railVswr = () =>
      container.querySelector(".thumbstrip canvas.sweep-vswr") as HTMLElement;
    const railAxis = railVswr().dataset.axis;

    // Its own range: 13.9-14.5 MHz in 25 points, on the 1 − 1/SWR scale
    // with a 1.5:1 threshold, drawn in the chart on the stage.
    fireEvent.change(select, { target: { value: "wide SWR" } });
    const chart = await untilDom(() => vswr());
    // In the chart: the zparam view's plot holds it, the R/X chart is gone,
    // and the chart's header names the pick.
    expect(chart.closest(".zparam-plot")).not.toBeNull();
    expect(stageChart("canvas.zparam")).toBeNull();
    const head = screen.getByRole("group", { name: "Analysis chart" });
    expect(head.dataset.chartKind).toBe("frequency");
    expect(head.dataset.analysis).toBe("wide SWR");
    await untilDom(() => sweeps.some((f) => f.length === 25) || null);
    await sweepBaseDone(chart);
    const own = sweeps.find((f) => f.length === 25)!;
    expect(own[0]).toBeCloseTo(13.9, 9);
    expect(own[24]).toBeCloseTo(14.5, 9);
    await untilDom(() => chart.dataset.readout?.startsWith("1.5:1 BW") || null);
    expect(chart.dataset.axis).toBe("reciprocal");
    // The chart's range is the chart's: the dial's travel (the session's
    // sweep range) is untouched.
    expect(dial()).toEqual([14, 14.35]);
    // The frequency sweep's own path: nothing went to /param_sweep.
    expect(paramSweeps).toHaveLength(knobSweeps);

    // E4: the deck's own range, the file's grid, on EZNEC's ρ scale at 2:1.
    select = screen.getByRole("combobox", { name: "Analysis" }) as HTMLSelectElement;
    const before = sweeps.length;
    fireEvent.change(select, { target: { value: "band SWR" } });
    await untilDom(() => sweeps.slice(before).some((f) => f.length === 15) || null);
    const again = await untilDom(() => vswr());
    await sweepBaseDone(again);
    await untilDom(() => again.dataset.axis === "rho" || null);
    const file = sweeps.slice(before).find((f) => f.length === 15)!;
    expect(file[0]).toBeCloseTo(14, 9);
    expect(file[14]).toBeCloseTo(14.35, 9);
    await untilDom(() => again.dataset.readout?.startsWith("2:1 BW") || null);
    expect(paramSweeps).toHaveLength(knobSweeps);
    // The chart's scale never became the viewer's: the standalone VSWR view
    // still draws on its own.
    expect(railVswr().dataset.axis).toBe(railAxis);
  });

  it("a knob analysis still sweeps its knob in the Z-vs-parameter view", async () => {
    const { container, sweeps, paramSweeps } = await mount();
    const select = await picker(container);
    await untilDom(() => paramSweeps.length > 0);
    const before = paramSweeps.length;
    const freqSweeps = sweeps.length;
    fireEvent.change(select, { target: { value: "height" } });
    await untilDom(() => paramSweeps.length > before);
    expect(paramSweeps[paramSweeps.length - 1]).toEqual(
      expect.objectContaining({ param: "base", values: HEIGHT_VALUES }),
    );
    // Still the Z-vs-parameter view, the dial untouched, no frequency sweep
    // asked for by the pick.
    expect(stageChart("canvas.zparam")).toBeTruthy();
    expect(vswr()).toBeNull();
    expect(dial()).toEqual([14, 14.35]);
    expect(sweeps.length).toBe(freqSweeps);
  });
});
