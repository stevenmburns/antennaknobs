// Pinned sweeps through a real <DesignSession> (AK#1757 item 1): Pin on the
// chart's header freezes its curves, one pin per curve; a knob change
// re-runs the live curve and the pin stays as it was, both drawn; Pin waits
// while a run is in flight; and a pin, held by the shell, outlives the
// design tab that made it.
//
// Mutation notes (run by hand, 2026-09-30; each reverted after):
//   - chartPins built from every pin, enabled or not: "…hide is global"
//     fails, the hidden pin still draws;
//   - Pin's in-flight gate dropped (pinBlocked ignoring the frequency
//     runners' running / phase): "Pin freezes the curve…" fails, the button
//     never disables through the knob change's re-run.
//   - the harness's provider keyed by session id (pins per tab, not per
//     shell): "a pin outlives its tab" fails, the new tab lists no pin.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { fireEvent, screen, within } from "@testing-library/react";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { invveeShape } from "./fixtures/solveShapes";
import {
  HARNESS_EXAMPLE,
  mountReady,
  sessionReady,
  sessionTree,
  stageChart,
  untilDom,
} from "./designSessionHarness";

vi.setConfig({ testTimeout: 30_000 });

const GAP: SchemaParamSpec = {
  name: "gap",
  label: "Gap",
  default: 0.25,
  kind: "float",
  min: 0,
  max: 1,
  step: 0.05,
  precision: 2,
  unit: null,
  visible_when: null,
};

const DECK: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  bands: [
    { key: "14.175 MHz", label: "14.175 MHz", freq_mhz: 14.175, min_mhz: 14, max_mhz: 14.35 },
  ],
  default_freq: 14.175,
  has_design_freq: false,
  meas_freq_range_mhz: [14, 14.35],
  sweep_range: { lo: 14, hi: 14.35, spacing: "lin", step: 0.025, source: "file" },
  param_schema: [GAP],
};

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
    const gap = typeof req.gap === "number" ? req.gap : 0.25;
    const reply = {
      ...invveeShape,
      feeds: undefined,
      geometry: req.geometry,
      _seq: req._seq,
      z_in_re: 40 + 40 * gap,
      z_in_im: -10,
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

type Body = Record<string, unknown> & { freqs_mhz: number[] };

const UI_DEFAULTS = {
  path: "/x/settings.toml",
  exists: false,
  writable: true,
  // Refinement off, so every /sweep is one base sweep of 15 points.
  switches: {
    live: true,
    freq_sweep: true,
    convergence_sweep: false,
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

// Z moves with the gap knob and the engine's density, so a knob change and
// a crossed engine each draw a curve of their own.
async function mount() {
  const bodies: Body[] = [];
  const r = await mountReady({
    examples: [DECK],
    pinned: ["antenna", "zparam"],
    uiDefaults: UI_DEFAULTS,
    routes: {
      "/sweep": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}")) as Body;
        bodies.push(body);
        const gap = typeof body.gap === "number" ? body.gap : 0.25;
        const n = typeof body.n_per_wire === "number" ? body.n_per_wire : 0;
        const lines = body.freqs_mhz.map((f) =>
          JSON.stringify({ freq_mhz: f, z_re: 20 + 100 * gap + n + 100 * Math.abs(f - 14.2), z_im: -n / 2 }),
        );
        lines.push(JSON.stringify({ done: true }));
        return ndjson(lines);
      },
    },
  });
  return { ...r, bodies };
}

async function chartOnStage(r: { container: HTMLElement }) {
  fireEvent.click(r.container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
  await untilDom(() => screen.queryByRole("button", { name: "Engines and grounds" }));
}

// The stage's SWR chart once every curve has landed: `curves` other curves
// (as data-curves counts them) and the chart's own, all idle.
async function swrSettled(curves = "") {
  return untilDom(() => {
    const c = stageChart("canvas.sweep-vswr");
    return c && c.dataset.phase === "idle" && c.dataset.points === "15" && c.dataset.curves === curves
      ? c
      : null;
  });
}

const pinButton = () => screen.getByRole("button", { name: "Pin this chart's curves" }) as HTMLButtonElement;

beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("pinning a frequency sweep", () => {
  it("Pin freezes the curve; a knob change re-runs the live one and both draw", async () => {
    const r = await mount();
    await chartOnStage(r);
    fireEvent.change(screen.getByRole("combobox", { name: "Chart view" }), { target: { value: "Swr" } });
    const before = await swrSettled();
    const liveBefore = before.dataset.yValues;
    await untilDom(() => !pinButton().disabled || null);
    fireEvent.click(pinButton());

    // The pin draws on the chart, all 15 points, and is listed in the
    // legend (which a one-curve chart shows now that there is a pin).
    await untilDom(() => stageChart("canvas.sweep-vswr")?.dataset.pins?.endsWith(":15") || null);
    const row = await untilDom(() => document.querySelector<HTMLElement>(".chart-legend-pin"));
    expect(row.dataset.drawable).toBe("1");
    expect(row.textContent).toContain("B-spline d=2");
    // The live SWR curve and the pin agree until something changes.
    expect(stageChart("canvas.sweep-vswr")?.dataset.pinY).toBe(liveBefore);

    // A knob change: the dwell switch is on, so the chart re-runs; Pin waits
    // while the run is in flight.
    const sent = r.bodies.length;
    const gap = screen.getByRole("slider", { name: "Gap" });
    fireEvent.keyDown(gap, { key: "ArrowUp" });
    fireEvent.keyDown(gap, { key: "ArrowUp" });
    await untilDom(() => pinButton().disabled || null);
    expect(pinButton().title).toMatch(/in flight/);
    await untilDom(() => r.bodies.length > sent || null);
    expect(r.bodies[r.bodies.length - 1].gap).toBeCloseTo(0.35, 9);
    const after = await untilDom(() => {
      const c = stageChart("canvas.sweep-vswr");
      return c && c.dataset.phase === "idle" && c.dataset.yValues !== liveBefore ? c : null;
    });

    // Both drawn: the live curve moved, the pin did not.
    expect(after.dataset.points).toBe("15");
    expect(after.dataset.pins).toMatch(/^sweep-pin-\d+:15$/);
    expect(after.dataset.pinY).toBe(liveBefore);
    expect(after.dataset.yValues).not.toBe(liveBefore);
    // Pin is available again, and a second pin takes the next colour.
    await untilDom(() => !pinButton().disabled || null);
    expect(row.textContent).not.toContain("gap");
    fireEvent.click(pinButton());
    const rows = await untilDom(() => {
      const all = document.querySelectorAll<HTMLElement>(".chart-legend-pin");
      return all.length === 2 ? [...all] : null;
    });
    // The second pin names the knob it was taken at.
    expect(rows[1].textContent).toContain("gap 0.35");
    const swatch = (el: HTMLElement) =>
      el.querySelector<HTMLElement>(".chart-legend-pin-swatch")!.style.borderColor;
    expect(swatch(rows[0])).not.toBe(swatch(rows[1]));
  });

  it("the pin draws on every view but the Table, where it is greyed with why; hide is global", async () => {
    const r = await mount();
    await chartOnStage(r);
    await untilDom(() => {
      const c = stageChart("canvas.smith");
      return c?.dataset.phase === "idle" || null;
    });
    await untilDom(() => !pinButton().disabled || null);
    fireEvent.click(pinButton());
    await untilDom(() => stageChart("canvas.smith")?.dataset.pins?.endsWith(":15") || null);
    const view = (v: string) =>
      fireEvent.change(screen.getByRole("combobox", { name: "Chart view" }), { target: { value: v } });
    view("Rx");
    await untilDom(() => stageChart("canvas.zparam")?.dataset.pins?.endsWith(":15") || null);
    view("S11");
    await untilDom(() => stageChart("canvas.sweep-gamma")?.dataset.pins?.endsWith(":15") || null);

    // Hide: the one global flag; the pin stays listed and stops drawing.
    fireEvent.click(screen.getByRole("checkbox", { name: /^Show pin / }));
    await untilDom(() => stageChart("canvas.sweep-gamma")?.dataset.pins === "" || null);
    const row = document.querySelector<HTMLElement>(".chart-legend-pin")!;
    expect(row.dataset.enabled).toBe("0");
    fireEvent.click(within(row).getByRole("checkbox"));
    await untilDom(() => stageChart("canvas.sweep-gamma")?.dataset.pins?.endsWith(":15") || null);

    // Delete removes it from the list and the chart.
    fireEvent.click(within(row).getByRole("button", { name: /^Delete pin / }));
    await untilDom(() => (document.querySelector(".chart-legend-pin") === null ? true : null));
    expect(stageChart("canvas.sweep-gamma")?.dataset.pins).toBe("");
  });
});

describe("a crossed chart", () => {
  it("makes one pin per drawn curve, each labelled by its cell's engine", async () => {
    const r = await mount();
    await chartOnStage(r);
    fireEvent.change(screen.getByRole("combobox", { name: "Chart view" }), { target: { value: "Swr" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Engines and grounds" })[0]);
    const dlg = screen.getByRole("dialog", { name: "Engines and grounds" });
    const boxB = within(dlg)
      .getAllByRole("checkbox")
      .find((c) => c.closest("label")?.textContent?.startsWith("B: "))!;
    fireEvent.click(boxB);
    fireEvent.keyDown(document.body, { key: "Escape" });
    await swrSettled("B|1:15");
    await untilDom(() => !pinButton().disabled || null);
    fireEvent.click(pinButton());
    const rows = await untilDom(() => {
      const all = document.querySelectorAll<HTMLElement>(".chart-legend-pin");
      return all.length === 2 ? [...all] : null;
    });
    expect(rows[0].textContent).toContain("B-spline d=2");
    expect(rows[1].textContent).toContain("B-spline d=1");
    expect(rows[1].title).toContain("B: B-spline d=1");
    // Pins sit outside the curve cap: both draw beside the two live curves.
    await untilDom(() => (stageChart("canvas.sweep-vswr")?.dataset.pins?.split(";").length === 2 ? true : null));
    expect(stageChart("canvas.sweep-vswr")?.dataset.curves).toBe("B|1:15");
  });
});

describe("a pin outlives its tab", () => {
  it("closing the design tab keeps the pin; a new tab's chart lists and draws it", async () => {
    const r = await mount();
    await chartOnStage(r);
    await untilDom(() => stageChart("canvas.smith")?.dataset.phase === "idle" || null);
    await untilDom(() => !pinButton().disabled || null);
    fireEvent.click(pinButton());
    await untilDom(() => document.querySelector(".chart-legend-pin"));

    // The tab closes (its session unmounts) and another opens: the shell's
    // provider, and its pins, stay.
    r.rerender(sessionTree(2));
    await sessionReady(document.body);
    await chartOnStage(r);
    const row = await untilDom(() => document.querySelector<HTMLElement>(".chart-legend-pin"));
    expect(row.dataset.drawable).toBe("1");
    await untilDom(() => stageChart("canvas.smith")?.dataset.pins?.endsWith(":15") || null);
  });
});
