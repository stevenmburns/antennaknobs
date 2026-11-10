// The SWR chart's "Sweep this span" through a real <DesignSession>: a drag
// zooms the stage chart's frequency axis without a solve, and the chip's
// button makes the zoomed window the chart's own range (its from / to, which
// ↺ restores), re-sweeping just that span at the same point count.
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import type { ExampleDescriptor } from "../lib/params";
import { HARNESS_EXAMPLE, mountReady, stageChart, sweepIdle, untilDom } from "./designSessionHarness";

vi.setConfig({ testTimeout: 30_000 });

// 14.00–14.35 MHz in 25 kHz steps: 15 points.
const DECK: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  bands: [{ key: "20m", label: "20m", freq_mhz: 14.175, min_mhz: 14, max_mhz: 14.35 }],
  default_freq: 14.175,
  has_design_freq: false,
  meas_freq_range_mhz: [14, 14.35],
  sweep_range: { lo: 14, hi: 14.35, spacing: "lin", step: 0.025, source: "file" },
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

const UI_DEFAULTS = {
  path: "/x/settings.toml",
  exists: false,
  writable: true,
  switches: {
    live: true,
    freq_sweep: true,
    convergence_sweep: true,
    pattern_renorm: false,
    refine: false,
    heatmap_currents: true,
    current_waveforms: false,
    wire_labels: false,
    feed_labels: true,
  },
  switches_set: ["refine"],
  antenna_view: { orientation: "iso" },
  ground: null,
  problems: [],
};

type SweepBody = Record<string, unknown> & { freqs_mhz: number[] };

async function mount() {
  const sweeps: SweepBody[] = [];
  const r = await mountReady({
    examples: [DECK],
    pinned: ["antenna", "zparam"],
    uiDefaults: UI_DEFAULTS,
    routes: {
      "/sweep": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}")) as SweepBody;
        sweeps.push(body);
        const lines = body.freqs_mhz.map((f) =>
          JSON.stringify({ freq_mhz: f, z_re: 40 + 100 * Math.abs(f - 14.2), z_im: 0 }),
        );
        lines.push(JSON.stringify({ done: true }));
        return ndjson(lines);
      },
    },
  });
  return { ...r, sweeps };
}

// The stage chart's plot runs from x = 26 to size − 8 (chart scale 1 in
// jsdom), over the window it shows.
function xAt(chart: HTMLElement, f: number): number {
  const size = parseFloat((chart.parentElement as HTMLElement).style.width);
  const lo = Number(chart.dataset.viewLo);
  const hi = Number(chart.dataset.viewHi);
  return 26 + ((f - lo) / (hi - lo)) * (size - 34);
}

const pointer = (type: "pointerDown" | "pointerMove" | "pointerUp", el: Element, x: number) =>
  fireEvent[type](el, { clientX: x, clientY: 100, pointerId: 1, pointerType: "mouse", button: 0 });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Sweep this span", () => {
  it("re-sweeps the zoomed window as the chart's own range, at the same point count", async () => {
    const r = await mount();
    fireEvent.click(r.container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
    const view = await untilDom(() => screen.queryByRole("combobox", { name: "Chart view" }) as HTMLSelectElement | null);
    fireEvent.change(view, { target: { value: "Swr" } });
    const chart = await untilDom(() => {
      const c = stageChart("canvas.sweep-vswr");
      return c && c.dataset.points === "15" ? c : null;
    });
    await sweepIdle(chart);
    const before = r.sweeps.length;
    expect((screen.getByLabelText("from MHz") as HTMLInputElement).value).toBe("14");

    // A drag from 14.1 to 14.25 MHz: a view, no solve.
    const x0 = xAt(chart, 14.1);
    const x1 = xAt(chart, 14.25);
    pointer("pointerDown", chart, x0);
    pointer("pointerMove", chart, x1);
    pointer("pointerUp", chart, x1);
    expect(chart.dataset.zoomed).toBe("1");
    expect(Number(chart.dataset.viewLo)).toBeCloseTo(14.1, 9);
    expect(Number(chart.dataset.viewHi)).toBeCloseTo(14.25, 9);
    expect(r.sweeps.length).toBe(before);

    fireEvent.click(screen.getByRole("button", { name: "Sweep this span" }));
    const sent = await untilDom(() => r.sweeps.slice(before).find((b) => b.freqs_mhz.length > 0));
    expect(sent.freqs_mhz).toHaveLength(15);
    expect(sent.freqs_mhz[0]).toBeCloseTo(14.1, 9);
    expect(sent.freqs_mhz[14]).toBeCloseTo(14.25, 9);
    await untilDom(() => (screen.getByLabelText("from MHz") as HTMLInputElement).value === "14.1" || null);
    expect((screen.getByLabelText("to MHz") as HTMLInputElement).value).toBe("14.25");
    // The new sweep fills the chart, whole.
    await untilDom(() => (chart.dataset.viewLo === "14.1" && chart.dataset.points === "15" ? true : null));
    expect(chart.dataset.zoomed).toBe("0");
    expect(chart.dataset.viewHi).toBe("14.25");
    // ↺ is the chart's: back to the design's own range.
    fireEvent.click(screen.getByTitle("Back to the analysis's own range"));
    await untilDom(() => (screen.getByLabelText("from MHz") as HTMLInputElement).value === "14" || null);
  });
});
