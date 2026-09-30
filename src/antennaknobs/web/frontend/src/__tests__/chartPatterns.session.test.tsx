// An analysis chart showing a PATTERN (AK#1757, sweep-framework step 7 unit
// 3): no sweep, one solve per cell, drawn as the analysis's cuts or its
// metrics table, through a real <DesignSession>. The CLI side is
// tests/test_analyses_patterns_1757.py; this is the chart's half.
//
// What is pinned: picking a pattern asks POST /pattern_cell once per cell,
// each request the cell's (a state set over the design's defaults, on a lane
// stream of its own, with the chart's cut angles); the cut view draws one
// trace per cell, named in the legend by the cell; the table view has one
// row per cell with the compare table's numbers; the view menu offers the
// analysis's views; and a refused state is named in the legend and in the
// table while the others draw.
//
// Mutation notes (run by hand, 2026-09-30; each reverted after):
//   - useChartCells not asking its pattern runners (wanted always false):
//     only the first cell is solved, "one trace per cell" fails;
//   - PatternCellsTable dropping MetricCells: the table rows read "—";
//   - chartRunInputs sending no cut angle (elevAzDeg 0 for every view): the
//     request check on elev_az_deg = 90 fails.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { fireEvent, screen, within } from "@testing-library/react";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { invveeShape } from "./fixtures/solveShapes";
import { HARNESS_EXAMPLE, mountReady, untilDom } from "./designSessionHarness";

vi.setConfig({ testTimeout: 30_000 });

const knob = (over: Partial<SchemaParamSpec>): SchemaParamSpec => ({
  name: "base",
  label: "Base",
  default: 7,
  kind: "float",
  min: 1,
  max: 20,
  step: 0.5,
  precision: 1,
  unit: "m",
  visible_when: null,
  ...over,
});

const DECK: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  bands: [{ key: "28.47 MHz", label: "28.47 MHz", freq_mhz: 28.47, min_mhz: 28, max_mhz: 29.7 }],
  default_freq: 28.47,
  has_design_freq: false,
  meas_freq_range_mhz: [28, 29.7],
  param_schema: [knob({})],
};

const state = (name: string, knobs: Record<string, number>, over: Record<string, unknown> = {}) => ({
  name,
  design: null,
  knobs,
  label: name,
  refused: null,
  param: null,
  values: null,
  range: null,
  freqs: null,
  on: null,
  ...over,
});

const TYPO = "state 'typo' sets hieght, and this design has no knob 'hieght'";

const PATTERN = {
  name: "height patterns",
  summary: "pattern at 28.47 MHz (freq); 3 patterns (3 states)",
  code: "an.patterns(...)",
  problems: [],
  workbench: {
    runs: true,
    kind: "pattern",
    views: [{ view: "Elevation", az: 90 }, { view: "Azimuth", el: 20 }, { view: "PatternTable" }],
    freq: 28.47,
    engines: null,
    grounds: null,
    axes: ["states"],
    planes: null,
    designs: null,
    states: [
      state("as built", {}),
      state("low mast", { base: 5 }),
      state("tall mast", { base: 12 }),
      state("typo", { hieght: 1 }, { refused: TYPO }),
    ],
    step: null,
    note: null,
  },
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
    const reply = { ...invveeShape, feeds: undefined, geometry: req.geometry, _seq: req._seq, z0_ohms: 50 };
    setTimeout(() => this.onmessage?.({ data: JSON.stringify(reply) } as MessageEvent), 0);
  }
  close() {}
}

type Body = Record<string, unknown>;

// A cell's pattern: a lobe whose size is its mast height, so each cell's
// trace and metrics are its own. The cuts are attached at the request's
// angles, as `solve()` attaches them.
function cell(body: Body) {
  const base = Number(body.base);
  const lobe = (n: number) => Array.from({ length: n }, (_, i) => base - 10 * Math.abs(Math.sin((Math.PI * i) / n)));
  return {
    available: true,
    solve: {
      ...invveeShape,
      feeds: undefined,
      geometry: body.geometry,
      solve_id: `cell-${base}`,
      cuts: {
        az_elev_deg: body.az_elev_deg,
        elev_az_deg: body.elev_az_deg,
        n_dir: 72,
        floor_dbi: -40,
        azimuth: lobe(72),
        elevation: lobe(72),
        diffraction: false,
      },
    },
    metrics: {
      peak_gain_dbi: base,
      takeoff_deg: 90 - 5 * base,
      azimuth_deg: 0,
      front_to_back_db: 0.5,
      az_beamwidth_deg: 80,
      el_beamwidth_deg: 20,
      rdf_db: 9.1,
    },
  };
}

async function mount() {
  const cells: Body[] = [];
  const r = await mountReady({
    examples: [DECK],
    pinned: ["antenna", "zparam"],
    routes: {
      "/pattern_cell": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}")) as Body;
        cells.push(body);
        return { ok: true, status: 200, json: async () => cell(body) } as unknown as Response;
      },
      "/analyses": () =>
        ({ ok: true, status: 200, json: async () => ({ analyses: [PATTERN] }) }) as unknown as Response,
    },
  });
  return { ...r, cells };
}

async function chartOnStage(r: { container: HTMLElement }) {
  // The thumbnail is a bare canvas with no role to find it by.
  // eslint-disable-next-line testing-library/no-node-access -- see above
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

// The legend's rows carry their refusal as data, which no role exposes.
const legendRows = () =>
  // eslint-disable-next-line testing-library/no-node-access -- see above
  [...document.querySelectorAll<HTMLElement>(".chart-legend .chart-legend-row")].map((row) => [
    row.textContent,
    row.dataset.refused,
  ]);

const traces = (name: string) => {
  const c = screen.queryByRole("img", { name });
  return c ? (JSON.parse(c.dataset.traces ?? "[]") as string[]) : null;
};

beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a pattern analysis on the chart", () => {
  it("solves each cell once and draws one trace per cell, named by the cell", async () => {
    const r = await mount();
    await chartOnStage(r);
    await pick("height patterns");
    // One /pattern_cell per drawable cell, each the cell's own request.
    const sent = (base: number) => untilDom(() => r.cells.find((b) => b.base === base));
    const built = await sent(7);
    const low = await sent(5);
    const tall = await sent(12);
    expect([built._stream, low._stream, tall._stream]).toEqual([undefined, "c0r1", "c0r2"]);
    for (const b of [built, low, tall]) {
      // The chart's first elevation cut's bearing, and its azimuth cut's
      // elevation: the angles the solve ships its cuts at.
      expect([b.elev_az_deg, b.az_elev_deg]).toEqual([90, 20]);
    }
    expect(r.cells.some((b) => "hieght" in b)).toBe(false);
    // The first view: the elevation cut, a trace per cell.
    const drawn = await untilDom(() => {
      const t = traces("Elevation cut at 90° azimuth");
      return t && t.length === 3 ? t : null;
    });
    expect(drawn).toEqual(["as built", "low mast", "tall mast"]);
    expect(legendRows()).toEqual([
      ["as built", "0"],
      ["low mast", "0"],
      ["tall mast", "0"],
      [`typo: ${TYPO}`, "1"],
    ]);
    // The view menu offers the analysis's views, in its order.
    const views = screen.getByRole("combobox", { name: "Chart view" }) as HTMLSelectElement;
    expect([...views.options].map((o) => o.textContent)).toEqual([
      "Elevation @ 90° az",
      "Azimuth @ 20° el",
      "Table",
    ]);
    // The azimuth cut: the same solves, re-cut; nothing solves again.
    const asked = r.cells.length;
    fireEvent.change(views, { target: { value: "pattern:1" } });
    const az = await untilDom(() => {
      const t = traces("Azimuth cut at 20° elevation");
      return t && t.length === 3 ? t : null;
    });
    expect(az).toEqual(["as built", "low mast", "tall mast"]);
    expect(r.cells.length).toBe(asked);
  });

  it("draws the metrics table, a row per cell with the compare table's numbers", async () => {
    const r = await mount();
    await chartOnStage(r);
    await pick("height patterns");
    await untilDom(() => (r.cells.length >= 3 ? true : null));
    const views = (await untilDom(() => screen.queryByRole("combobox", { name: "Chart view" }))) as HTMLSelectElement;
    fireEvent.change(views, { target: { value: "pattern:2" } });
    const table = await untilDom(() => screen.queryByRole("table", { name: "Pattern metrics" }));
    const rows = await untilDom(() => {
      // The header row has no cells, only column headers.
      const got = within(table)
        .getAllByRole("row")
        .map((tr) => within(tr).queryAllByRole("cell").map((td) => td.textContent))
        .filter((cells) => cells.length > 0);
      return got.length === 4 && got[2][1] === "12.0" ? got : null;
    });
    expect(rows).toEqual([
      ["as built", "7.0", "55°", "0.5", "80°", "9.1"],
      ["low mast", "5.0", "65°", "0.5", "80°", "9.1"],
      ["tall mast", "12.0", "30°", "0.5", "80°", "9.1"],
      ["typo", TYPO],
    ]);
  });
});
