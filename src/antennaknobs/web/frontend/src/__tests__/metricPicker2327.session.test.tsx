// The metric picker through a real <DesignSession> (AK#2327): an analysis
// declaring several MetricPlots names its Metric view by the metric drawn,
// lists each as its own entry, draws a pick off the sweep it already has (no
// second /param_sweep), and names the rest in its note.
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

const metric = (name: string, unit: string) => ({
  name,
  unit,
  relative_to: null,
  relative_unit: unit,
  spec: { an: "FillMetric", quantity: name },
});
const METRICS = [metric("fill compression", "×"), metric("fill time", "s")];

const ANALYSES = [
  {
    name: "two metrics",
    summary: "two metrics",
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
      param: "len",
      values: LEN,
      views: ["Rx", "Metric"],
      metric: METRICS[0],
      metrics: METRICS,
      states: null,
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

let sweeps: { metric?: unknown; metrics?: unknown[] | undefined }[] = [];

async function mount() {
  return mountReady({
    pickRuns: true,
    examples: [DECK],
    pinned: ["antenna", "zparam"],
    routes: {
      // Compression is absent (reuse off) at every point, the fill time is
      // a tenth of the knob: each metric with its own values and reason.
      "/param_sweep": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}")) as {
          param: string;
          values: number[];
          metric?: unknown;
          metrics?: unknown[];
        };
        sweeps.push({ metric: body.metric, metrics: body.metrics });
        const lines = body.values.map((v) =>
          JSON.stringify({
            param: body.param,
            value: v,
            z_re: 50 + v,
            z_im: -10,
            metrics: [null, v / 10],
            metric_errors: ["fill reuse is off for this solve", null],
          }),
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

const viewBox = () => screen.getByRole("combobox", { name: "Chart view" }) as HTMLSelectElement;
const optionTexts = () => [...viewBox().options].map((o) => o.textContent);
const optionValue = (text: string) => [...viewBox().options].find((o) => o.textContent === text)!.value;

beforeEach(() => {
  sweeps = [];
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("an analysis with several metrics in the session", () => {
  it("lists each by name, draws a pick without sweeping again, and keeps its reasons apart", async () => {
    const r = await mount();
    // eslint-disable-next-line testing-library/no-node-access -- the thumbnail is a bare canvas
    fireEvent.click(r.container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
    await pick("two metrics");
    await untilDom(() => (sweeps.length > 0 ? true : null));
    // Both metrics asked for at once.
    expect(sweeps[0].metrics).toEqual(METRICS.map((m) => m.spec));
    expect(sweeps[0].metric).toBeUndefined();
    await untilDom(() => (optionTexts().includes("Fill time") ? true : null));
    expect(optionTexts()).toEqual(["R / X", "Smith", "Table", "Fill compression", "Fill time"]);

    // The first: absent at every point, and it says why.
    fireEvent.change(viewBox(), { target: { value: optionValue("Fill compression") } });
    await untilDom(() => (screen.queryByText("fill reuse is off for this solve") ? true : null));

    // The second, off the same sweep: drawn, and no second request.
    const before = sweeps.length;
    fireEvent.change(viewBox(), { target: { value: optionValue("Fill time") } });
    const plot = await untilDom(() => {
      const p = stageChart(".metric-plot");
      return p && p.getAttribute("data-series")?.includes("0.11") ? p : null;
    });
    expect(plot).not.toBeNull();
    expect(viewBox().selectedOptions[0].textContent).toBe("Fill time");
    expect(screen.queryByText("fill reuse is off for this solve")).toBeNull();
    expect(sweeps.length).toBe(before);

    // Away and back: the pick holds.
    fireEvent.change(viewBox(), { target: { value: "Rx" } });
    fireEvent.change(viewBox(), { target: { value: optionValue("Fill time") } });
    expect(viewBox().selectedOptions[0].textContent).toBe("Fill time");
  });
});
