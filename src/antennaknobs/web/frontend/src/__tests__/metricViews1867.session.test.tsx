// A metric analysis through a real <DesignSession> (AK#1867): the session's
// half of what metricViews1867.test.tsx pins on the views alone. The legend
// names a relative plot's reference as one, the Metric view's guide sits at
// the live knob value, and the Table view carries the metric, all three
// off the session's own wiring (the captions, the zparam settings and the
// chart's MetricPlot handed to the Table), which no view-level mount runs.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { invveeShape } from "./fixtures/solveShapes";
import { HARNESS_EXAMPLE, mountReady, stageChart, untilDom } from "./designSessionHarness";

vi.setConfig({ testTimeout: 30_000 });

const knob = (over: Partial<SchemaParamSpec>): SchemaParamSpec => ({
  name: "len",
  label: "Length",
  default: 1,
  kind: "float",
  min: 0.5,
  max: 1.5,
  step: 0.01,
  precision: 2,
  unit: null,
  visible_when: null,
  ...over,
});

const DECK: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  bands: [{ key: "14.175 MHz", label: "14.175 MHz", freq_mhz: 14.175, min_mhz: 14, max_mhz: 14.35 }],
  default_freq: 14.175,
  has_design_freq: false,
  meas_freq_range_mhz: [14, 14.35],
  param_schema: [knob({})],
};

const LEN = [0.9, 1, 1.1];
const state = (name: string, knobs: Record<string, number>, over: Record<string, unknown> = {}) => ({
  name,
  design: null,
  knobs,
  label: name,
  refused: null,
  param: "len",
  values: LEN,
  range: null,
  freqs: null,
  on: null,
  reference: false,
  fixed: false,
  ...over,
});

// The M0AGP study's shape: the swept state against a FIXED reference
// solved once at its own setting.
const ANALYSES = [
  {
    name: "dx",
    summary: "dx",
    code: "an.Analysis(...)",
    problems: [],
    workbench: {
      runs: true,
      kind: "knob",
      log: false,
      engines: null,
      grounds: null,
      axes: ["states"],
      planes: null,
      designs: null,
      step: null,
      note: null,
      param: "len",
      values: LEN,
      views: ["Metric", "Table", "Rx"],
      metric: {
        name: "DX gain",
        unit: "dBi",
        relative_to: "ref",
        relative_unit: "dB",
        spec: { an: "ElevationWindow", name: "DX gain", lo: 2, hi: 10, step: 0.1 },
      },
      states: [
        state("as built", {}),
        state("ref", { len: 1.3 }, { values: [1.3], reference: true, fixed: true }),
      ],
    },
  },
];

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

async function mount() {
  return mountReady({
    pickRuns: true,
    examples: [DECK],
    pinned: ["antenna", "zparam"],
    routes: {
      // The metric is twice the knob: "as built" reads 1.8, 2, 2.2 and the
      // reference, solved once at 1.3, 2.6.
      "/param_sweep": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}")) as { param: string; values: number[] };
        const lines = body.values.map((v) =>
          JSON.stringify({ param: body.param, value: v, z_re: 50 + v, z_im: -10, metric: 2 * v }),
        );
        lines.push(JSON.stringify({ done: true }));
        return ndjson(lines);
      },
      "/analyses": () =>
        ({ ok: true, status: 200, json: async () => ({ analyses: ANALYSES }) }) as unknown as Response,
    },
  });
}

async function pick(name: string) {
  const box = await untilDom(() => {
    const b = screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null;
    return b && [...b.options].some((o) => o.value === name) ? b : null;
  });
  fireEvent.change(box, { target: { value: name } });
}

// The legend's rows, which no role exposes.
const legendRows = () =>
  // eslint-disable-next-line testing-library/no-node-access -- see above
  [...document.querySelectorAll<HTMLElement>(".chart-legend .chart-legend-row")].map((row) => row.textContent);

beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a relative metric analysis in the session", () => {
  it("names its reference, marks the live knob, and tabulates the metric", async () => {
    const r = await mount();
    // eslint-disable-next-line testing-library/no-node-access -- the thumbnail is a bare canvas
    fireEvent.click(r.container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
    await pick("dx");
    const plot = await untilDom(() => {
      const p = stageChart(".metric-plot");
      return p && p.getAttribute("data-series")?.includes("1.1") ? p : null;
    });
    await untilDom(() => (legendRows().length === 2 ? true : null));
    expect(legendRows()).toEqual(["as built", "ref (reference, 0 dB)"]);
    // The Length knob sits at its default, 1: the R/X chart's guide there.
    expect(plot.getAttribute("data-guide")).toBe("1");
    expect(plot.getAttribute("data-guide-label")).toBe("Length = 1 (now)");

    fireEvent.change(screen.getByRole("combobox", { name: "Chart view" }), { target: { value: "Table" } });
    const table = await untilDom(() => screen.queryByRole("table", { name: "Analysis table" }));
    // eslint-disable-next-line testing-library/no-node-access -- header cells by row
    const groups = [...table.querySelectorAll("thead tr:first-child th")].map((th) => th.textContent);
    expect(groups).toEqual(["", "as built", "ref (reference, 0 dB)"]);
    // eslint-disable-next-line testing-library/no-node-access -- header cells by row
    const heads = [...table.querySelectorAll("thead tr:last-child th")].map((th) => th.textContent);
    expect(heads.slice(1, 5)).toEqual(["R (Ω)", "X (Ω)", "DX gain (dBi)", "DX gain vs ref (dB)"]);
    // eslint-disable-next-line testing-library/no-node-access -- body cells by row
    const rows = [...table.querySelectorAll("tbody tr")].map((tr) => [...tr.children].map((c) => c.textContent));
    expect(rows.map((row) => [row[0], row[3], row[4], row[7], row[8]])).toEqual([
      ["0.9", "1.800", "-0.800", "", ""],
      ["1", "2.000", "-0.600", "", ""],
      ["1.1", "2.200", "-0.400", "", ""],
      ["1.3", "", "", "2.600", "0.000"],
    ]);
  });
});
