// AK#1757 step 5 unit 3 through a real <DesignSession>: the standalone Smith,
// VSWR and S11 views folded into the analysis chart.
//   - the default workbench: the chart pinned where the Smith view was,
//     opening on the design's own frequency sweep on the Smith chart, its
//     dwell switch on, its views and the measured overlay on the chart;
//   - a viewer's stored grid of the old views becomes one chart cell, on the
//     view the first of them named, the other pins kept;
//   - settings.toml's [switches] freq_sweep and convergence_sweep seed the
//     dwell switch of a new frequency and knob chart, and a save writes the
//     file's values back, never a chart's flip;
//   - stale: with the switch off a knob change dims only the swept trace
//     (the canvas's data-stale), not the chart, and the live point still
//     follows.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ExampleDescriptor } from "../lib/params";
import { invveeShape } from "./fixtures/solveShapes";
import { HARNESS_EXAMPLE, mountReady, stageChart, untilDom } from "./designSessionHarness";
import { VIEW_PREFS_KEY } from "../components/session/useViewPrefs";
import type { LegacyChartView, View } from "../lib/view";

vi.setConfig({ testTimeout: 20_000 });

const DESIGN: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  bands: [
    { key: "14.175 MHz", label: "14.175 MHz", freq_mhz: 14.175, min_mhz: 14, max_mhz: 14.35 },
  ],
  default_freq: 14.175,
  has_design_freq: false,
  meas_freq_range_mhz: [14, 14.35],
  sweep_range: { lo: 14, hi: 14.35, spacing: "lin", step: 0.025, source: "file" },
  param_schema: [
    {
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
    },
  ],
};

// R = 40 + 2·base at the measurement frequency: the live point's SWR moves
// with every Height step.
class EchoWebSocket {
  static OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    setTimeout(() => {
      this.readyState = EchoWebSocket.OPEN;
      this.onopen?.();
    }, 0);
  }
  send(payload: string) {
    const req = JSON.parse(payload) as Record<string, unknown>;
    if (!("geometry" in req) || typeof req._seq !== "number") return;
    const base = typeof req.base === "number" ? req.base : 7;
    const reply = {
      ...invveeShape,
      feeds: undefined,
      geometry: req.geometry,
      _seq: req._seq,
      z_in_re: 40 + 2 * base,
      z_in_im: 0,
      z0_ohms: 50,
    };
    setTimeout(() => this.onmessage?.({ data: JSON.stringify(reply) } as MessageEvent), 0);
  }
  close() {}
}

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

const SWITCHES = {
  live: true,
  freq_sweep: true,
  convergence_sweep: false,
  pattern_renorm: false,
  refine: false,
  heatmap_currents: true,
  current_waveforms: false,
  wire_labels: false,
  feed_labels: true,
};

async function mount(opts: {
  pinned?: (View | LegacyChartView)[];
  layout?: "rail" | "grid";
  switches?: Partial<typeof SWITCHES>;
  switchesSet?: string[];
} = {}) {
  const sweeps: number[][] = [];
  const paramSweeps: unknown[] = [];
  const saves: { switches: Record<string, boolean> }[] = [];
  const r = await mountReady({
    examples: [DESIGN],
    ...(opts.pinned ? { pinned: opts.pinned } : {}),
    ...(opts.layout ? { layout: opts.layout } : {}),
    uiDefaults: {
      path: "/x/settings.toml",
      exists: true,
      writable: true,
      switches: { ...SWITCHES, ...opts.switches },
      switches_set: opts.switchesSet ?? [],
      antenna_view: { orientation: "iso" },
      ground: null,
      problems: [],
    },
    routes: {
      "/sweep": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}"));
        const freqs = body.freqs_mhz as number[];
        if (!body._refine) sweeps.push(freqs);
        const lines = freqs.map((f) =>
          JSON.stringify({ freq_mhz: f, z_re: 50 * (1 + 20 * Math.abs(f - 14.2)), z_im: 0 }),
        );
        lines.push(JSON.stringify({ done: true }));
        return ndjson(lines);
      },
      "/param_sweep": (_url: string, init?: RequestInit) => {
        paramSweeps.push(JSON.parse(String(init?.body ?? "{}")));
        return ndjson([JSON.stringify({ done: true })]);
      },
      "/settings": (_url: string, init?: RequestInit) => {
        saves.push(JSON.parse(String(init?.body ?? "{}")));
        return {
          ok: true,
          status: 200,
          json: async () => ({ ok: true, ui_defaults: { path: "/x/settings.toml", writable: true } }),
        } as unknown as Response;
      },
    },
  });
  return { ...r, sweeps, paramSweeps, saves };
}

const head = () => screen.getByRole("group", { name: "Analysis chart" });
const dwellBox = () => screen.getByRole("checkbox", { name: "auto re-run" }) as HTMLInputElement;
const chartView = () => screen.getByRole("combobox", { name: "Chart view" }) as HTMLSelectElement;
const railLabels = (c: HTMLElement) =>
  [...c.querySelectorAll(".thumbstrip .thumb-label")].map((l) => l.textContent);

beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the default workbench", () => {
  it("pins the chart where the Smith view was, opening on the frequency sweep on the Smith chart", async () => {
    const { container, sweeps, paramSweeps } = await mount();
    // The founding four, the chart fourth, as the Smith view was.
    expect(railLabels(container)).toEqual(["Azimuth (xy)", "Elevation (yz)", "Sweep"]);
    const thumb = container.querySelector<HTMLElement>(".thumbstrip canvas.smith")!;
    expect(thumb).toBeTruthy();
    // It sweeps from the rail as the Smith view did: the design's own range
    // (the deck's 14–14.35 MHz grid, 15 points), no knob sweep.
    await untilDom(() => sweeps.length > 0 || null);
    expect(sweeps[0]).toHaveLength(15);
    expect(paramSweeps).toEqual([]);

    fireEvent.click(thumb);
    const smith = await untilDom(() => stageChart("canvas.smith"));
    expect(smith.closest(".zparam-plot")).not.toBeNull();
    expect(head().dataset.chartKind).toBe("frequency");
    expect(head().dataset.dwell).toBe("1");
    expect(dwellBox().checked).toBe(true);
    // No analysis picked: the picker says what the chart shows.
    const picker = screen.getByRole("combobox", { name: "Analysis" }) as HTMLSelectElement;
    expect(picker.value).toBe("");
    expect(picker.selectedOptions[0].textContent).toBe("freq sweep");
    // The old views are the chart's views; the Smith view's measured overlay
    // is on the chart while it shows Smith.
    expect(chartView().value).toBe("Smith");
    expect([...chartView().options].map((o) => o.value)).toEqual(["Smith", "Swr", "S11"]);
    expect(screen.getByText("measured .s1p…")).toBeTruthy();
    // The readout is open on the chart's Smith view, as on the Smith view.
    expect(screen.queryByRole("button", { name: "Show the full solve readout" })).toBeNull();
    fireEvent.change(chartView(), { target: { value: "Swr" } });
    await untilDom(() => stageChart('canvas.sweep[data-mode="vswr"]'));
    expect(screen.queryByText("measured .s1p…")).toBeNull();
    // A view flip is the chart's own: it sends no new sweep.
    expect(sweeps).toHaveLength(1);
  });

  it("a knob drag moves the live point at once and re-sweeps after the dwell", async () => {
    const { container, sweeps } = await mount();
    fireEvent.click(container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
    fireEvent.change(chartView(), { target: { value: "Swr" } });
    const vswr = () => stageChart('canvas.sweep[data-mode="vswr"]')!;
    await untilDom(() => (vswr()?.dataset.points === "15" && vswr().dataset.phase === "idle") || null);
    await untilDom(() => vswr().dataset.current === "1.0800" || null);
    const n = sweeps.length;
    fireEvent.keyDown(screen.getByRole("slider", { name: "Height" }), { key: "ArrowUp" });
    expect(vswr().dataset.phase).toBe("queued");
    await untilDom(() => vswr().dataset.current === "1.1000" || null);
    await untilDom(() => sweeps.length > n || null);
    expect(sweeps[sweeps.length - 1]).toHaveLength(15);
  });
});

describe("a stored layout of the removed views", () => {
  it("a grid of smith, vswr, gamma and zparam is the one chart, on Smith", async () => {
    const { container } = await mount({ layout: "grid", pinned: ["smith", "vswr", "gamma", "zparam"] });
    // One chart, not four cells of it. (The session opens on the antenna
    // view, which this grid does not pin, so the pre-existing peek rule,
    // gridFix, leaves grid for the rail here; that is not this unit's.)
    const stored = JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "{}");
    expect(stored.pinned).toEqual(["zparam"]);
    const thumbs = container.querySelectorAll(".grid-cell canvas.smith, .thumbstrip canvas.smith");
    expect(thumbs).toHaveLength(1);
    fireEvent.click(thumbs[0] as HTMLElement);
    await untilDom(() => stageChart("canvas.smith"));
    expect(chartView().value).toBe("Smith");
  });

  it("the same grid with the antenna pinned: two cells, the chart's on Smith", async () => {
    const { container } = await mount({ layout: "grid", pinned: ["smith", "vswr", "gamma", "antenna"] });
    expect(container.querySelectorAll(".grid-cell")).toHaveLength(2);
    expect(container.querySelectorAll(".grid-cell canvas.smith")).toHaveLength(1);
    expect(container.querySelector(".grid-cell canvas.sweep")).toBeNull();
  });

  it("a VSWR pin among others is the chart on its Swr view, in the VSWR pin's place", async () => {
    const { container } = await mount({ pinned: ["antenna", "vswr", "azimuth"] });
    expect(railLabels(container)).toEqual(["Sweep", "Azimuth (xy)"]);
    expect(container.querySelector(".thumbstrip canvas.sweep-vswr")).toBeTruthy();
    const stored = JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "{}");
    // Nothing is written by the read itself: storage says what it said.
    expect(stored.pinned).toEqual(["antenna", "vswr", "azimuth"]);
  });
});

describe("settings.toml's retired sweep switches", () => {
  it("freq_sweep = false seeds a new frequency chart's switch off: nothing sweeps until Run", async () => {
    const user = userEvent.setup();
    const { container, sweeps } = await mount({ switches: { freq_sweep: false }, switchesSet: ["freq_sweep"] });
    fireEvent.click(container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
    await untilDom(() => stageChart("canvas.smith"));
    expect(dwellBox().checked).toBe(false);
    expect(stageChart("canvas.smith")!.dataset.phase).toBe("idle");
    expect(sweeps).toEqual([]);
    await user.click(screen.getByRole("button", { name: /^run/ }));
    await untilDom(() => sweeps.length > 0 || null);
    expect(sweeps[0]).toHaveLength(15);
  });

  it("convergence_sweep = true seeds a knob chart's switch on; a save writes the file's values, not the chart's", async () => {
    const user = userEvent.setup();
    const { saves } = await mount({ switches: { convergence_sweep: true }, switchesSet: ["convergence_sweep"] });
    fireEvent.contextMenu(screen.getByRole("slider", { name: "Height" }));
    await user.click(screen.getByRole("button", { name: "Sweep this knob…" }));
    await untilDom(() => head().dataset.chartKind === "knob" || null);
    expect(dwellBox().checked).toBe(true);
    // On the knob sweep's R/X plot the readout starts minimized, as on the
    // Z-vs-parameter view (its left axis).
    expect(screen.getByRole("button", { name: "Show the full solve readout" })).toBeTruthy();
    // Flip the chart's switch off, then save: the file's own values go back.
    await user.click(dwellBox());
    expect(head().dataset.dwell).toBe("0");
    await user.click(screen.getByRole("button", { name: "Tools menu" }));
    await user.click(screen.getByRole("button", { name: /save as my defaults/i }));
    await untilDom(() => saves.length > 0 || null);
    expect(saves[0].switches.convergence_sweep).toBe(true);
    expect(saves[0].switches.freq_sweep).toBe(true);
  });
});

describe("a stale curve", () => {
  for (const view of ["Smith", "Swr", "S11"] as const) {
    it(`dims only the trace on the ${view} view; the live point still follows`, async () => {
      const user = userEvent.setup();
      const { container, sweeps } = await mount();
      fireEvent.click(container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
      fireEvent.change(chartView(), { target: { value: view } });
      const canvas = () => stageChart(".zparam-plot canvas")!;
      await untilDom(() => (canvas()?.dataset.phase === "idle" && sweeps.length > 0) || null);
      expect(canvas().dataset.stale).toBe("0");
      await user.click(dwellBox());
      const n = sweeps.length;
      fireEvent.keyDown(screen.getByRole("slider", { name: "Height" }), { key: "ArrowUp" });
      expect(canvas().dataset.phase).toBe("idle");
      await untilDom(() => canvas().dataset.stale === "1" || null);
      // The trace dims inside the canvas; no class dims the canvas itself.
      expect(container.querySelector(".is-stale canvas")).toBeNull();
      expect(canvas().closest(".stale")).toBeNull();
      expect(sweeps).toHaveLength(n);
      if (view === "Swr") {
        // The live marker moved with Height while the trace waits.
        await untilDom(() => canvas().dataset.current === "1.1000" || null);
      }
      await user.click(screen.getByRole("button", { name: "run · re-run?" }));
      await untilDom(() => (canvas().dataset.stale === "0" && sweeps.length > n) || null);
    });
  }
});
