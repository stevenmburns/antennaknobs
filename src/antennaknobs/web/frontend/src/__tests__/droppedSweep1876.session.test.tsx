// A curve whose stream the server dropped (AK#1876), through a real
// <DesignSession> opened by a deep link (the issue's view=Table&run=1).
//
// The server's lane supersedes a queued or running /param_sweep point when a
// newer generation arrives (any live solve; a deep link's run can go out
// before the session's first one), and ends that stream without its `{done}`
// record. A cell whose request does not follow the live knobs (a state at
// its own setting, here the FIXED reference) keeps its signature, so nothing
// re-issued it: the Table drew the chart's own curve alone, no reference
// row, and every relative value blank. The runner now asks again for a
// stream that ended unclosed, a bounded number of times.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { PARAM_SWEEP_REISSUES } from "../components/session/useParamSweep";
import { invveeShape } from "./fixtures/solveShapes";
import { HARNESS_EXAMPLE, mountDesignSession, sessionReady, untilDom } from "./designSessionHarness";

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
  name: "dipoles.deck",
  bands: [{ key: "14.175 MHz", label: "14.175 MHz", freq_mhz: 14.175, min_mhz: 14, max_mhz: 14.35 }],
  default_freq: 14.175,
  has_design_freq: false,
  meas_freq_range_mhz: [14, 14.35],
  param_schema: [knob({}), knob({ name: "top", label: "Top", default: 0.5, min: 0, max: 1 })],
};

const LEN = [0.9, 1, 1.1];
const state = (name: string, knobs: Record<string, number>, over: Record<string, unknown> = {}) => ({
  name,
  design: "dipoles.deck",
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

const HOLD = {
  objective: "resonance",
  knobs: ["top"],
  bounds: { top: [0, 1] },
  z0: null,
  warm_start: true,
  spec: { an: "Hold", objective: "resonance", adjust: ["top"], z0: null, warm_start: true },
};

const workbench = (over: Record<string, unknown>) => ({
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
  ...over,
});

const ANALYSES = [
  // verticals.m0agp_invl's shape: the swept state held, against a FIXED
  // reference solved once at its own setting (and so never held).
  {
    name: "dx",
    summary: "dx",
    code: "an.Analysis(...)",
    problems: [],
    workbench: workbench({
      views: ["Metric", "Knobs"],
      hold: HOLD,
      metric: {
        name: "DX gain",
        unit: "dBi",
        relative_to: "ref",
        relative_unit: "dB",
        spec: { an: "ElevationWindow", name: "DX gain", lo: 2, hi: 10, step: 0.1 },
      },
      states: [
        state("as built", {}),
        state("ref", { len: 1.3, top: 0 }, { values: [1.3], reference: true, fixed: true }),
      ],
    }),
  },
  // A plain cross with no metric: two states, both swept.
  {
    name: "two states",
    summary: "two states",
    code: "an.Analysis(...)",
    problems: [],
    workbench: workbench({
      views: ["Rx", "Table"],
      states: [state("short", { top: 0.2 }), state("long", { top: 0.8 })],
    }),
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
    const reply = { ...invveeShape, feeds: undefined, geometry: req.geometry, _seq: req._seq, z0_ohms: 50 };
    setTimeout(() => this.onmessage?.({ data: JSON.stringify(reply) } as MessageEvent), 0);
  }
  close() {}
}

function ndjson(lines: string[]): Response {
  const chunks = lines.length > 0 ? [new TextEncoder().encode(lines.join("\n") + "\n")] : [];
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

type SweepBody = { param: string; values: number[]; hold?: unknown; _stream?: string };

/** Opens `url` with the second curve's (stream c0r1) first `drops` streams
 *  ended as the lane ends a superseded job: no record, no `{done}`. */
async function open(url: string, drops: number) {
  const second: SweepBody[] = [];
  mountDesignSession({
    url,
    examples: [DECK],
    pinned: ["antenna"],
    routes: {
      "/param_sweep": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}")) as SweepBody;
        if (body._stream === "c0r1") {
          second.push(body);
          if (second.length <= drops) return ndjson([]);
        }
        // The metric is twice the knob; a held point's top sits at 0.4.
        const lines = body.values.map((v) =>
          JSON.stringify({
            param: body.param,
            value: v,
            z_re: 50 + v,
            z_im: -10,
            metric: 2 * v,
            ...(body.hold ? { held: { top: 0.4 }, converged: true } : {}),
          }),
        );
        lines.push(JSON.stringify({ done: true }));
        return ndjson(lines);
      },
      "/analyses": () =>
        ({ ok: true, status: 200, json: async () => ({ analyses: ANALYSES }) }) as unknown as Response,
    },
  });
  await sessionReady(document.body);
  return second;
}

const table = () => screen.queryByRole("table", { name: "Analysis table" });
// eslint-disable-next-line testing-library/no-node-access -- header cells by row
const groups = (t: HTMLElement) => [...t.querySelectorAll("thead tr:first-child th")].map((th) => th.textContent);
const rows = (t: HTMLElement) =>
  // eslint-disable-next-line testing-library/no-node-access -- body cells by row
  [...t.querySelectorAll("tbody tr")].map((tr) => [...tr.children].map((c) => c.textContent));
// Longer than the dwell a re-issue would wait out, so a sweep that was going
// to be asked for has been.
const pastDwell = () => new Promise((r) => setTimeout(r, 1500));

beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("a curve whose stream the server dropped is asked for again", () => {
  it("fills the metric Table's reference after a view=Table&run=1 link", async () => {
    const second = await open("/?design=dipoles.deck&analysis=dx&view=Table&run=1", 1);
    const t = await untilDom(() => {
      const el = table();
      return el && rows(el).length === 4 ? el : null;
    });
    expect(groups(t)).toEqual(["", "as built", "ref (reference, 0 dB)"]);
    // Held knob, DX gain and its relative value on every swept row; the
    // reference's own row at its fixed setting.
    expect(rows(t).map((r) => [r[0], r[3], r[4], r[5], r[8], r[9]])).toEqual([
      ["0.9", "0.4", "1.800", "-0.800", "", ""],
      ["1", "0.4", "2.000", "-0.600", "", ""],
      ["1.1", "0.4", "2.200", "-0.400", "", ""],
      ["1.3", "", "", "", "2.600", "0.000"],
    ]);
    expect(second.map((b) => b.values)).toEqual([[1.3], [1.3]]);
  });

  it("fills a plain cross's other column group on the Table", async () => {
    const second = await open("/?design=dipoles.deck&analysis=two%20states&view=Table&run=1", 1);
    const t = await untilDom(() => {
      const el = table();
      return el && groups(el).length === 3 && rows(el).every((r) => r[3] !== "") ? el : null;
    });
    expect(groups(t)).toEqual(["", "short", "long"]);
    expect(rows(t).map((r) => [r[0], r[1], r[3]])).toEqual([
      ["0.9", "50.900", "50.900"],
      ["1", "51.000", "51.000"],
      ["1.1", "51.100", "51.100"],
    ]);
    expect(second).toHaveLength(2);
  });

  it("stops asking after a bounded number of drops", async () => {
    const second = await open("/?design=dipoles.deck&analysis=two%20states&view=Table&run=1", 99);
    await untilDom(() => (second.length === 1 + PARAM_SWEEP_REISSUES ? true : null));
    await pastDwell();
    expect(second).toHaveLength(1 + PARAM_SWEEP_REISSUES);
    // The chart's own curve still drew; the dropped one did not.
    const t = table()!;
    expect(groups(t)).toEqual(["", "short"]);
  });
});
