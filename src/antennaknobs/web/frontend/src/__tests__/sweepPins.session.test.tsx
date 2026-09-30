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
type ParamBody = Record<string, unknown> & { param: string; values: number[] };

const GAP_VALUES = [0.1, 0.2, 0.3, 0.4, 0.5];
// A knob analysis on the gap, and a frequency one, for the chart's picker.
const ANALYSES = {
  geometry: DECK.name,
  analyses: [
    {
      name: "gap sweep",
      summary: "gap 0.1..0.5, 5 points; 1 curve; views Rx",
      code: 'an.Analysis("gap sweep", an.Sweep("gap", 0.1, 0.5, points=5))',
      problems: [],
      workbench: { runs: true, kind: "knob", param: "gap", values: GAP_VALUES, log: false, note: null },
    },
    {
      name: "band SWR",
      summary: "frequency; 1 curve; views Swr",
      code: "an.band_swr()",
      problems: [],
      workbench: {
        runs: true,
        kind: "frequency",
        note: null,
        views: ["Swr"],
        range: null,
        level: "default",
        points: null,
        swr: { scale: null, threshold: null },
      },
    },
  ],
};

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
      "/param_sweep": (_url: string, init?: RequestInit) => {
        const b = JSON.parse(String(init?.body ?? "{}")) as ParamBody;
        const lines = b.values.map((v) =>
          JSON.stringify({ param: b.param, value: v, z_re: 60 + 100 * v, z_im: -30 + 10 * v, solver: "momwire" }),
        );
        lines.push(JSON.stringify({ done: true, solver: "momwire" }));
        return ndjson(lines);
      },
      "/analyses": () =>
        ({ ok: true, status: 200, json: async () => ANALYSES }) as unknown as Response,
    },
  });
  return { ...r, bodies };
}

// Put the chart on the rail's stage: its thumb is the "Sweep" view's.
async function chartOnStage() {
  fireEvent.click(screen.getByTitle("Switch to Sweep"));
  await untilDom(() => screen.queryByRole("button", { name: "Engines and grounds" }));
}

// The legend's pin rows, by role: the "Pinned sweeps" group's list items.
const pinRows = (): HTMLElement[] => {
  const g = screen.queryByRole("group", { name: "Pinned sweeps" });
  return g ? within(g).queryAllByRole("listitem") : [];
};
const pinRowsOf = (n: number) => untilDom(() => (pinRows().length === n ? pinRows() : null));

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
    await chartOnStage();
    fireEvent.change(screen.getByRole("combobox", { name: "Chart view" }), { target: { value: "Swr" } });
    const before = await swrSettled();
    const liveBefore = before.dataset.yValues;
    await untilDom(() => !pinButton().disabled || null);
    fireEvent.click(pinButton());

    // The pin draws on the chart, all 15 points, and is listed in the
    // legend (which a one-curve chart shows now that there is a pin).
    await untilDom(() => stageChart("canvas.sweep-vswr")?.dataset.pins?.endsWith(":15") || null);
    const [row] = await pinRowsOf(1);
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
    const rows = await pinRowsOf(2);
    // The second pin names the knob it was taken at.
    expect(rows[1].textContent).toContain("gap 0.35");
    expect(rows[0].dataset.color).not.toBe(rows[1].dataset.color);
  });

  it("the pin draws on every view but the Table, where it is greyed with why; hide is global", async () => {
    await mount();
    await chartOnStage();
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
    const [row] = pinRows();
    expect(row.dataset.enabled).toBe("0");
    fireEvent.click(within(row).getByRole("checkbox"));
    await untilDom(() => stageChart("canvas.sweep-gamma")?.dataset.pins?.endsWith(":15") || null);

    // Delete removes it from the list and the chart.
    fireEvent.click(within(row).getByRole("button", { name: /^Delete pin / }));
    await pinRowsOf(0);
    expect(stageChart("canvas.sweep-gamma")?.dataset.pins).toBe("");
  });
});

describe("a crossed chart", () => {
  it("makes one pin per drawn curve, each labelled by its cell's engine", async () => {
    await mount();
    await chartOnStage();
    fireEvent.change(screen.getByRole("combobox", { name: "Chart view" }), { target: { value: "Swr" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Engines and grounds" })[0]);
    const dlg = screen.getByRole("dialog", { name: "Engines and grounds" });
    fireEvent.click(within(dlg).getByRole("checkbox", { name: /^B: / }));
    fireEvent.keyDown(document.body, { key: "Escape" });
    await swrSettled("B|1:15");
    await untilDom(() => !pinButton().disabled || null);
    fireEvent.click(pinButton());
    const rows = await pinRowsOf(2);
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
    await chartOnStage();
    await untilDom(() => stageChart("canvas.smith")?.dataset.phase === "idle" || null);
    await untilDom(() => !pinButton().disabled || null);
    fireEvent.click(pinButton());
    await pinRowsOf(1);

    // The tab closes (its session unmounts) and another opens: the shell's
    // provider, and its pins, stay.
    r.rerender(sessionTree(2));
    await sessionReady(document.body);
    await chartOnStage();
    const [row] = await pinRowsOf(1);
    expect(row.dataset.drawable).toBe("1");
    await untilDom(() => stageChart("canvas.smith")?.dataset.pins?.endsWith(":15") || null);
  });
});

describe("a knob pin", () => {
  it("draws on a chart sweeping the same knob and is greyed with why on a frequency chart", async () => {
    await mount();
    await chartOnStage();
    await untilDom(() => stageChart("canvas.smith")?.dataset.phase === "idle" || null);
    // The header is another component per kind: query the picker afresh.
    const pick = (name: string) =>
      fireEvent.change(screen.getByRole("combobox", { name: "Analysis" }), { target: { value: name } });
    pick("gap sweep");
    await untilDom(() => {
      const c = stageChart("canvas.zparam");
      return c?.dataset.points === "5" && c.dataset.phase === "idle" ? c : null;
    });
    await untilDom(() => !pinButton().disabled || null);
    fireEvent.click(pinButton());
    await untilDom(() => stageChart("canvas.zparam")?.dataset.pins?.endsWith(":5") || null);
    const [row] = await pinRowsOf(1);
    // The swept knob varies along x: the label does not name it.
    expect(row.textContent).not.toContain("gap");

    // On a frequency chart it cannot draw, and says why.
    pick("band SWR");
    await untilDom(() => stageChart("canvas.sweep-vswr"));
    await untilDom(() => pinRows()[0]?.dataset.drawable === "0" || null);
    expect(pinRows()[0].textContent).toContain(
      "sweeps gap; this chart sweeps frequency",
    );
    expect(stageChart("canvas.sweep-vswr")?.dataset.pins).toBe("");
  });
});
