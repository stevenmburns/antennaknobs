// An analysis chart's crosses over measurement planes, designs and a family
// (AK#1757, sweep-framework step 5 unit 4b), through a real <DesignSession>.
//
// The oracle for each kind: the curve a multi-curve chart draws for a cell
// sends the request a single-curve chart sends in a fresh session set up as
// that cell is, byte for byte but the lane's own metadata (the session id,
// the generation and the curve's stream):
//   - planes: the session with that plane picked in the solve readout's
//     measurement-plane selector (the seam the plane cell reuses);
//   - designs: a fresh session with that design loaded, at its defaults;
//   - families: the session with the stepped knob turned to the value.
//
// Mutation notes (run by hand, 2026-09-29; each reverted after):
//   - a plane cell dropping its plane (buildCellRequest not passing
//     `cell.plane`): "a plane cell…" fails, the T1 curve's body has no plane;
//   - a design cell keeping the session's design (buildRequestFor ignoring
//     `over.design`): "a design cell…" fails, the other design's curve is
//     sent as dipoles.probe with the session's knobs;
//   - a family cell ignoring its value (buildRequestFor skipping
//     `over.step`): "a family cell…" fails, gap stays 0.25;
//   - the cap ignoring the new axes (crossPlan's cap over the engine and
//     ground axes only): "the cap…" fails, 4 values x 2 engines draws;
//   - a refused engine cell dropped from the legend (the legend's
//     engineRefusal branch removed): "NEC-2 declining…" fails, the row
//     reads as a drawn curve with an error, not a refused cell.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { invveeShape } from "./fixtures/solveShapes";
import { HARNESS_EXAMPLE, mountReady, untilDom } from "./designSessionHarness";

vi.setConfig({ testTimeout: 30_000 });

const knob = (over: Partial<SchemaParamSpec>): SchemaParamSpec => ({
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
  ...over,
});

const band = (f: number, lo: number, hi: number) => ({
  key: `${f} MHz`,
  label: `${f} MHz`,
  freq_mhz: f,
  min_mhz: lo,
  max_mhz: hi,
});

// The session's design, with two knobs: `gap` (the family's step) and
// `len` (the swept knob).
const DECK: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  bands: [band(14.175, 14, 14.35)],
  default_freq: 14.175,
  has_design_freq: false,
  meas_freq_range_mhz: [14, 14.35],
  sweep_range: { lo: 14, hi: 14.35, spacing: "lin", step: 0.025, source: "file" },
  param_schema: [
    knob({}),
    knob({ name: "len", label: "Length", default: 1, min: 0.5, max: 1.5, step: 0.01 }),
  ],
};

// The other design of a design cross: its own knobs, defaults and band.
const OTHER: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  name: "dipoles.other",
  label: "Other dipole",
  bands: [band(21.2, 21, 21.45)],
  default_freq: 21.2,
  has_design_freq: false,
  meas_freq_range_mhz: [21, 21.45],
  param_schema: [knob({ default: 0.6 }), knob({ name: "arm", label: "Arm", default: 3 })],
};

const knobEntry = (name: string, over: Record<string, unknown>) => ({
  name,
  summary: name,
  code: "an.Analysis(...)",
  problems: [],
  workbench: {
    runs: true,
    kind: "knob",
    log: false,
    engines: null,
    grounds: null,
    axes: [],
    planes: null,
    designs: null,
    step: null,
    note: null,
    ...over,
  },
});

const LADDER = [8, 12, 17];

const ANALYSES = [
  {
    name: "planes SWR",
    summary: "frequency; 3 curves (3 planes)",
    code: "an.band_swr(cross=an.Cross(planes=(...)))",
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
      engines: null,
      grounds: null,
      axes: ["planes"],
      planes: [
        { name: "rig", refused: null },
        { name: "T1", refused: null },
        { name: "nowhere", refused: "no plane 'nowhere' on this design; it offers rig, T1, feed" },
      ],
      designs: null,
      step: null,
    },
  },
  knobEntry("feed spellings", {
    param: "n_per_wire",
    values: LADDER,
    log: true,
    engines: ["momwire:bspline", "pynec"],
    axes: ["designs", "engines"],
    designs: [
      { name: DECK.name, refused: null, param: "n_per_wire", values: LADDER },
      { name: OTHER.name, refused: null, param: "n_per_wire", values: LADDER },
    ],
  }),
  knobEntry("convergence", { param: "n_per_wire", values: LADDER, log: true }),
  knobEntry("len family", {
    param: "len",
    values: [0.9, 1, 1.1],
    axes: ["step"],
    step: { knob: "gap", values: [0.25, 0.5], labels: ["gap = 0.25", "gap = 0.5"] },
  }),
  knobEntry("len sweep", { param: "len", values: [0.9, 1, 1.1] }),
  knobEntry("wide family", {
    param: "len",
    values: [0.9, 1, 1.1],
    axes: ["step"],
    step: { knob: "gap", values: [0.1, 0.2, 0.3, 0.4], labels: ["gap = 0.1", "gap = 0.2", "gap = 0.3", "gap = 0.4"] },
  }),
];

const PLANES = ["rig", "T1", "feed"];

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
    const reply = {
      ...invveeShape,
      feeds: undefined,
      geometry: req.geometry,
      _seq: req._seq,
      z_in_re: 50,
      z_in_im: -10,
      z0_ohms: 50,
      planes: PLANES,
      plane: typeof req.plane === "string" ? req.plane : "rig",
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

type Body = Record<string, unknown>;

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

// NEC-2 declines the other design's feed, as the server says it: every
// point of the sweep an error record.
const APEX_REFUSAL =
  "this design uses PortAtVertex (a series apex feed at a junction knot), which NEC-2 cannot represent";

async function mount(examples: ExampleDescriptor[] = [DECK, OTHER]) {
  const sweeps: Body[] = [];
  const params: Body[] = [];
  const r = await mountReady({
    examples,
    pinned: ["antenna", "zparam"],
    uiDefaults: UI_DEFAULTS,
    routes: {
      "/sweep": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}")) as Body & { freqs_mhz: number[] };
        sweeps.push(body);
        const lines = body.freqs_mhz.map((f) =>
          JSON.stringify({ freq_mhz: f, z_re: 40 + 100 * Math.abs(f - 14.2), z_im: body.plane === "T1" ? 5 : -5 }),
        );
        lines.push(JSON.stringify({ done: true }));
        return ndjson(lines);
      },
      "/param_sweep": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}")) as Body & { values: number[] };
        params.push(body);
        const refuse = body.solver === "pynec" && body.geometry === OTHER.name;
        const lines = body.values.map((v) =>
          JSON.stringify(
            refuse
              ? { param: body.param, value: v, error: `ValueError: ${APEX_REFUSAL}` }
              : { param: body.param, value: v, z_re: 50 + v, z_im: -10 + Number(body.gap ?? 0) * 10 },
          ),
        );
        lines.push(JSON.stringify({ done: true }));
        return ndjson(lines);
      },
      "/analyses": () =>
        ({ ok: true, status: 200, json: async () => ({ analyses: ANALYSES }) }) as unknown as Response,
    },
  });
  return { ...r, sweeps, params };
}

async function chartOnStage(r: { container: HTMLElement }) {
  fireEvent.click(r.container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
  await untilDom(() => screen.queryByRole("button", { name: "Engines and grounds" }));
}

async function pick(name: string) {
  const box = await untilDom(() => {
    const b = screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null;
    return b && [...b.options].some((o) => o.value === name) ? b : null;
  });
  fireEvent.change(box, { target: { value: name } });
}

const legendRows = () =>
  [...document.querySelectorAll<HTMLElement>(".chart-legend .chart-legend-row")].map((row) => [
    row.textContent,
    row.dataset.refused,
  ]);

const LANE_METADATA = new Set(["_session", "_gen", "_stream"]);
function physics(b: Body): Record<string, unknown> {
  return Object.fromEntries(Object.entries(b).filter(([k]) => !LANE_METADATA.has(k)));
}

async function fresh(examples?: ExampleDescriptor[]) {
  cleanup();
  vi.unstubAllGlobals();
  vi.stubGlobal("WebSocket", EchoWebSocket);
  return mount(examples);
}

beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the plane cross", () => {
  it("a plane cell is the request a single chart sends with that plane picked, and a plane the design lacks is refused", async () => {
    const r = await mount();
    // The solve has landed, so the session knows its natural plane.
    await untilDom(() => screen.queryByLabelText("measurement plane"));
    await chartOnStage(r);
    await pick("planes SWR");
    const t1 = await untilDom(() => r.sweeps.find((b) => b.plane === "T1" && b._stream === "c0r1"));
    // The natural plane's cell is the field's absence, as the picker makes it.
    const rig = await untilDom(() => r.sweeps.find((b) => b._stream === undefined && !("plane" in b)));
    expect(rig.geometry).toBe(DECK.name);
    await untilDom(() => (legendRows().length === 3 ? true : null));
    expect(legendRows()).toEqual([
      ["rig", "0"],
      ["T1", "0"],
      ["nowhere: no plane 'nowhere' on this design; it offers rig, T1, feed", "1"],
    ]);
    // The session's own plane is untouched.
    expect((screen.getByLabelText("measurement plane") as HTMLSelectElement).value).toBe("rig");

    const r2 = await fresh();
    await chartOnStage(r2);
    const plane = await untilDom(() => screen.queryByLabelText("measurement plane") as HTMLSelectElement | null);
    fireEvent.change(plane, { target: { value: "T1" } });
    const single = await untilDom(() => r2.sweeps.find((b) => b._stream === undefined && b.plane === "T1"));
    expect(physics(t1)).toEqual(physics(single));
  });
});

describe("the design cross", () => {
  it("a design cell is the request a fresh session sends with that design loaded at its defaults", async () => {
    const r = await mount();
    await chartOnStage(r);
    // The session's own knobs moved off their defaults: a design cell does
    // not carry them (the CLI builds each design at its own defaults).
    const len = screen.getByRole("slider", { name: "Length" });
    fireEvent.keyDown(len, { key: "ArrowUp" });
    await pick("feed spellings");
    const other = await untilDom(() =>
      r.params.find((b) => b.geometry === OTHER.name && b.solver === "momwire"),
    );
    expect(other.design_freq_mhz).toBe(21.2);
    expect(other.gap).toBe(0.6);
    expect(other).not.toHaveProperty("len");
    // The session's design at ITS defaults too, not at the knob just moved.
    const own = await untilDom(() => r.params.find((b) => b.geometry === DECK.name && b.solver === "momwire"));
    expect(own.len).toBe(1);
    // The active design is untouched.
    expect(document.querySelector<HTMLElement>(".app[data-ready]")?.dataset.ready).toMatch(/^dipoles\.probe#/);

    // The oracle: a fresh session opening on the other design, running the
    // same ladder as a one-curve chart.
    const r2 = await fresh([OTHER, DECK]);
    await chartOnStage(r2);
    await pick("convergence");
    const single = await untilDom(() =>
      r2.params.find((b) => b._stream === undefined && b.geometry === OTHER.name && b.solver === "momwire"),
    );
    expect(physics(other)).toEqual(physics(single));
  });

  it("NEC-2 declining a design is a refused cell, named in the server's words, and the rest draw", async () => {
    const r = await mount();
    await chartOnStage(r);
    await pick("feed spellings");
    await untilDom(() => r.params.some((b) => b.solver === "pynec" && b.geometry === OTHER.name) || null);
    await untilDom(() => (legendRows().some(([t]) => t?.startsWith("dipoles.other, pynec:")) ? true : null));
    expect(legendRows()).toEqual([
      ["dipoles.probe, momwire:bspline", "0"],
      ["dipoles.probe, pynec", "0"],
      ["dipoles.other, momwire:bspline", "0"],
      [`dipoles.other, pynec: ${APEX_REFUSAL}`, "1"],
    ]);
    const legend = document.querySelector<HTMLElement>(".chart-legend");
    expect(legend?.dataset.curves).toBe("3");
  });
});

describe("the family cross", () => {
  it("a family cell is the request a single chart sends with the stepped knob at its value", async () => {
    const r = await mount();
    await chartOnStage(r);
    await pick("len family");
    const half = await untilDom(() => r.params.find((b) => b.gap === 0.5 && b.param === "len"));
    expect(half._stream).toBe("c0r1");
    await untilDom(() => (legendRows().length === 2 ? true : null));
    expect(legendRows()).toEqual([
      ["gap = 0.25", "0"],
      ["gap = 0.5", "0"],
    ]);
    // The session's knob is untouched.
    expect(screen.getByRole("slider", { name: "Gap" }).getAttribute("aria-valuenow")).toBe("0.25");

    const r2 = await fresh();
    await chartOnStage(r2);
    const gap = screen.getByRole("slider", { name: "Gap" });
    for (let k = 0; k < 5; k++) fireEvent.keyDown(gap, { key: "ArrowUp" });
    await untilDom(() => (gap.getAttribute("aria-valuenow") === "0.5" ? true : null));
    await pick("len sweep");
    const single = await untilDom(() =>
      r2.params.find((b) => b._stream === undefined && b.param === "len" && b.gap === 0.5),
    );
    expect(physics(half)).toEqual(physics(single));
  });
});

describe("the cap", () => {
  it("multiplies the analysis's crosses with the ticked slots, refused over six in the CLI's words", async () => {
    const r = await mount();
    await chartOnStage(r);
    await pick("wide family");
    await untilDom(() => (legendRows().length === 4 ? true : null));
    const before = r.params.length;
    fireEvent.click(screen.getAllByRole("button", { name: "Engines and grounds" })[0]);
    const dlg = screen.getByRole("dialog", { name: "Engines and grounds" });
    const b = within(dlg)
      .getAllByRole("checkbox")
      .find((c) => c.closest("label")?.textContent?.startsWith("B: ")) as HTMLInputElement;
    fireEvent.click(b);
    const refusal = "REFUSED: 4 values x 2 engines = 8 curves, over the cap of 6";
    await untilDom(() => document.querySelector(".chart-legend")?.textContent?.includes(refusal) || null);
    expect(within(dlg).getByRole("alert").textContent).toBe(refusal);
    expect(r.params.length).toBe(before);
  });
});
