// An analysis chart's states (AK#1757, sweep-framework step 7 unit 2): a
// cross over named knob settings, through a real <DesignSession>. The CLI
// side is tests/test_analyses_states_1757.py; this is the chart's half.
//
// The oracle: a state cell sends the request a single-curve chart sends in
// a FRESH session with those knobs turned by hand, byte for byte but the
// lane's own metadata. So a state is set over the design's defaults, never
// over this session's live knobs, and the legend names each curve by its
// state.
//
// Mutation notes (run by hand, 2026-09-30; each reverted after):
//   - buildRequestFor ignoring `over.state` (no knobs set): "one curve per
//     state…" fails, every cell is sent with gap 0.25;
//   - a state cell on the live knobs (buildRequestFor's state branch not
//     taking designAtDefaults): "one curve per state…" fails, "as built" is
//     sent with the dragged len;
//   - crossPlan leaving states out of the axes: the legend has one row.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
// `fresh` unmounts one session to mount the oracle's in the same test.
// eslint-disable-next-line testing-library/no-manual-cleanup -- see above
import { cleanup, fireEvent, screen } from "@testing-library/react";
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
    states: null,
    step: null,
    note: null,
    ...over,
  },
});

const LEN = [0.9, 1, 1.1];
// A served state: the cell's sweep as /analyses serves it (the knob sweep's
// values on the state's design at its defaults, with its knobs set).
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
  ...over,
});

const ANALYSES = [
  knobEntry("gap states", {
    param: "len",
    values: LEN,
    axes: ["states"],
    states: [state("as built", {}), state("wide", { gap: 0.5 }), state("narrow", { gap: 0.1 })],
  }),
  knobEntry("len sweep", { param: "len", values: LEN }),
  knobEntry("across designs", {
    param: "len",
    values: LEN,
    axes: ["states"],
    states: [
      state("mine, wide", { gap: 0.5 }),
      state("other, long arm", { arm: 5 }, {
        design: "dipoles.other",
        label: "dipoles.other, other, long arm",
      }),
      state("other, typo", { hieght: 1 }, {
        design: "dipoles.other",
        label: "dipoles.other, other, typo",
        refused: "state 'other, typo' sets hieght, and this design has no knob 'hieght'",
        param: null,
        values: null,
      }),
    ],
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

async function mount(examples: ExampleDescriptor[] = [DECK, OTHER], opts: { mobile?: boolean } = {}) {
  const sweeps: Body[] = [];
  const params: Body[] = [];
  const r = await mountReady({
    // A pick starts its analysis, as before [workbench.run_on_pick] (AC6LA #179).
    pickRuns: true,
    examples,
    ...(opts.mobile ? { mobile: true } : {}),
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

const LANE_METADATA = new Set(["_session", "_gen", "_stream"]);
function physics(b: Body): Record<string, unknown> {
  return Object.fromEntries(Object.entries(b).filter(([k]) => !LANE_METADATA.has(k)));
}

async function fresh(examples?: ExampleDescriptor[]) {
  // The oracle is a second session in the same test: the first unmounts.
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

describe("a cross over states", () => {
  it("draws one curve per state, named by the state, each set over the defaults", async () => {
    const r = await mount();
    await chartOnStage(r);
    // The session's own knobs move off their defaults: no state carries
    // them (a state means the same curve every session).
    const len = screen.getByRole("slider", { name: "Length" });
    fireEvent.keyDown(len, { key: "ArrowUp" });
    const gapSlider = screen.getByRole("slider", { name: "Gap" });
    fireEvent.keyDown(gapSlider, { key: "ArrowUp" });
    await untilDom(() => (gapSlider.getAttribute("aria-valuenow") === "0.3" ? true : null));
    await pick("gap states");
    await untilDom(() => (legendRows().length === 3 ? true : null));
    expect(legendRows()).toEqual([
      ["as built", "0"],
      ["wide", "0"],
      ["narrow", "0"],
    ]);
    const sent = (gap: number) =>
      untilDom(() => r.params.find((b) => b.param === "len" && b.gap === gap && b.geometry === DECK.name));
    const built = await sent(0.25);
    const wide = await sent(0.5);
    const narrow = await sent(0.1);
    expect([built._stream, wide._stream, narrow._stream]).toEqual([undefined, "c0r1", "c0r2"]);
    for (const b of [built, wide, narrow]) {
      expect(b.values).toEqual(LEN);
      // Not the dragged Length: the default.
      expect(b.len).toBe(1);
    }
    // The session's knobs are untouched.
    expect(gapSlider.getAttribute("aria-valuenow")).toBe("0.3");

    // The oracle: a fresh session with the gap turned to 0.5 by hand,
    // running the same sweep as a one-curve chart.
    const r2 = await fresh();
    await chartOnStage(r2);
    const gap2 = screen.getByRole("slider", { name: "Gap" });
    for (let k = 0; k < 5; k++) fireEvent.keyDown(gap2, { key: "ArrowUp" });
    await untilDom(() => (gap2.getAttribute("aria-valuenow") === "0.5" ? true : null));
    await pick("len sweep");
    const single = await untilDom(() =>
      r2.params.find((b) => b._stream === undefined && b.param === "len" && b.gap === 0.5),
    );
    expect(physics(wide)).toEqual(physics(single));
  });

  it("a state naming a design is that design's curve at its defaults, and a refused one is named", async () => {
    const r = await mount();
    await chartOnStage(r);
    await pick("across designs");
    const why = "state 'other, typo' sets hieght, and this design has no knob 'hieght'";
    await untilDom(() => (legendRows().length === 3 ? true : null));
    expect(legendRows()).toEqual([
      ["mine, wide", "0"],
      ["dipoles.other, other, long arm", "0"],
      [`dipoles.other, other, typo: ${why}`, "1"],
    ]);
    const other = await untilDom(() => r.params.find((b) => b.geometry === OTHER.name));
    // The other design's own defaults (gap 0.6, its band), the state's arm.
    expect([other.arm, other.gap, other.design_freq_mhz]).toEqual([5, 0.6, 21.2]);
    expect(other).not.toHaveProperty("hieght");
    expect(r.params.filter((b) => b.geometry === OTHER.name)).toHaveLength(1);
  });
});
