// A held analysis in the chart (AK#1757, sweep-framework step 6) through a
// real <DesignSession>: picking it sends its hold with the curve's
// /param_sweep, runs on Run (its switch off by default), draws a
// non-converged point as a gap with its reason and never as a value, draws
// its held knob on the Knobs view and in the Table, and is not staled by a
// drag of the knob it holds (which it re-solves from the design's defaults).
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { invveeShape } from "./fixtures/solveShapes";
import {
  HARNESS_EXAMPLE,
  mountReady,
  stageChart,
  untilDom,
} from "./designSessionHarness";

vi.setConfig({ testTimeout: 20_000 });

const knob = (over: Partial<SchemaParamSpec>): SchemaParamSpec => ({
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
  ...over,
});

const DECK: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  bands: [
    { key: "14.175 MHz", label: "14.175 MHz", freq_mhz: 14.175, min_mhz: 14, max_mhz: 14.35 },
  ],
  default_freq: 14.175,
  has_design_freq: false,
  meas_freq_range_mhz: [14, 14.35],
  sweep_range: { lo: 14, hi: 14.35, spacing: "lin", step: 0.025, source: "file" },
  param_schema: [
    knob({}),
    knob({ name: "gap", label: "Gap", default: 0.25, min: 0, max: 1, step: 0.05, precision: 2, unit: null }),
    knob({ name: "tilt", label: "Tilt", default: 10, min: 0, max: 40, step: 1, precision: 0, unit: "deg" }),
  ],
};

const HEIGHT_VALUES = Array.from({ length: 7 }, (_, i) => 2 + 3 * i);
const HOLD_SPEC = { an: "Hold", objective: "resonance", adjust: ["gap"], z0: null, warm_start: true };

const ANALYSES = {
  geometry: DECK.name,
  analyses: [
    {
      name: "match vs height",
      summary: "height (base) 2..20, 7 points; 1 curve; hold resonance on gap",
      code: 'an.Analysis("match vs height")',
      problems: [],
      spec: { an: "Analysis", name: "match vs height" },
      workbench: {
        runs: true,
        kind: "knob",
        param: "base",
        values: HEIGHT_VALUES,
        log: false,
        views: ["Rx", "Knobs"],
        hold: {
          objective: "resonance",
          knobs: ["gap"],
          bounds: { gap: [0, 1] },
          z0: null,
          warm_start: true,
          spec: HOLD_SPEC,
        },
        note: null,
      },
    },
  ],
};

// The server's held records: a point per value, Z at the optimum and the
// held knob's value there, except at base = 8, which the optimizer did not
// converge at: a gap, with its reason.
const GAP_AT = 8;
const GAP_WHY = "no resonance held (X does not change sign anywhere in the knob's range)";

// A socket that answers every solve at once, Z moving with the Height knob:
// R = 40 + 2·base, so the live point's SWR changes with every Height step.
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

type ParamBody = Record<string, unknown> & { param: string; values: number[]; hold?: unknown };

async function mount() {
  const paramSweeps: ParamBody[] = [];
  const r = await mountReady({
    // A pick starts its analysis, as before [workbench.run_on_pick] (AC6LA #179).
    pickRuns: true,
    examples: [DECK],
    pinned: ["antenna", "zparam"],
    routes: {
      "/sweep": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}"));
        const lines = (body.freqs_mhz as number[]).map((f) =>
          JSON.stringify({ freq_mhz: f, z_re: 50, z_im: 0 }),
        );
        lines.push(JSON.stringify({ done: true }));
        return ndjson(lines);
      },
      "/param_sweep": (_url: string, init?: RequestInit) => {
        const b = JSON.parse(String(init?.body ?? "{}")) as ParamBody;
        paramSweeps.push(b);
        const lines = b.values.map((v) =>
          v === GAP_AT
            ? JSON.stringify({ param: b.param, value: v, gap: GAP_WHY, held: { gap: 1 }, converged: false })
            : JSON.stringify({
                param: b.param,
                value: v,
                z_re: 60 + v,
                z_im: 0.0001,
                held: { gap: 0.1 + 0.01 * v },
                converged: true,
                solver: "momwire",
              }),
        );
        lines.push(JSON.stringify({ done: true, solver: "momwire", held_points: 6, gaps: 1 }));
        return ndjson(lines);
      },
      "/analyses": () =>
        ({ ok: true, status: 200, json: async () => ANALYSES }) as unknown as Response,
    },
  });
  fireEvent.click(r.container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
  const select = await untilDom(
    () => screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null,
  );
  return { ...r, select, paramSweeps };
}

const head = () => screen.getByRole("group", { name: "Analysis chart" });
const rx = () => stageChart("canvas.zparam");
const knobsChart = () => stageChart("canvas.knobs");
const slider = (name: string) => screen.getByRole("slider", { name });

beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a held analysis in the chart", () => {
  it("sends its hold, draws the gap with its reason, the knobs, the table; Run-only", async () => {
    const user = userEvent.setup();
    const { select, paramSweeps } = await mount();
    const before = paramSweeps.length;
    fireEvent.change(select, { target: { value: "match vs height" } });
    await untilDom(() => paramSweeps.length > before || null);
    const sent = paramSweeps[paramSweeps.length - 1];
    expect(sent).toEqual(expect.objectContaining({ param: "base", values: HEIGHT_VALUES, hold: HOLD_SPEC }));
    await untilDom(() => rx()?.dataset.points === "6" && rx()!.dataset.phase === "idle" ? true : null);
    // The non-converged point is NOT a point: it is a gap, with its reason.
    expect(rx()!.dataset.values).toBe("2,5,11,14,17,20");
    expect(rx()!.dataset.gaps).toBe(`8:${GAP_WHY}`);
    expect(rx()!.dataset.held).toBe("1");
    expect(rx()!.dataset.status).toBe("1 point not held — hover the marks");
    // Run-only by default: the chart's switch is off.
    expect(head().dataset.dwell).toBe("0");

    // The Knobs view: the held knob against the swept one, the gap marked.
    const view = screen.getByRole("combobox", { name: "Chart view" }) as HTMLSelectElement;
    expect([...view.options].map((o) => o.value)).toEqual(["Rx", "Smith", "Table", "Knobs"]);
    fireEvent.change(view, { target: { value: "Knobs" } });
    const k = await untilDom(() => knobsChart());
    expect(k.dataset.knobs).toBe("gap");
    expect(k.dataset.values).toBe("2,5,11,14,17,20");
    expect(k.dataset.k1).toBe(["0.120000", "0.150000", "0.210000", "0.240000", "0.270000", "0.300000"].join(","));
    expect(k.dataset.gaps).toBe(`8:${GAP_WHY}`);

    // The Table: the held knob's column, and the gap's row its reason.
    fireEvent.change(view, { target: { value: "Table" } });
    const table = await untilDom(() => document.querySelector<HTMLElement>(".chart-table"));
    expect(table.textContent).toContain("gap");
    expect(table.textContent).toContain(GAP_WHY);

    // A drag of the held knob does not stale it (it starts from the
    // defaults); a drag of another knob does, and runs nothing until Run.
    fireEvent.change(view, { target: { value: "Rx" } });
    await untilDom(() => rx());
    const n = paramSweeps.length;
    fireEvent.keyDown(slider("Gap"), { key: "ArrowUp" });
    expect(rx()!.dataset.phase).toBe("idle");
    expect(rx()!.dataset.stale).toBe("0");
    fireEvent.keyDown(slider("Tilt"), { key: "ArrowUp" });
    expect(rx()!.dataset.phase).toBe("idle");
    await untilDom(() => rx()!.dataset.stale === "1" || null);
    expect(paramSweeps.length).toBe(n);
    await user.click(screen.getByRole("button", { name: "run · re-run?" }));
    await untilDom(() => paramSweeps.length > n || null);
    expect(paramSweeps[paramSweeps.length - 1].hold).toEqual(HOLD_SPEC);
  });
});
