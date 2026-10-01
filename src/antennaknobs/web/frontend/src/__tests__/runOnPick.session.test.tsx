// Does picking an analysis start it (AC6LA, QRZ 1003328 #179)? Through the
// real app shell: a pick in the chart's picker runs by settings.toml's
// [workbench.run_on_pick] for the analysis's kind; a kind set false only
// selects, so the chart shows the analysis and waits for Run, even with the
// chart's "auto re-run" switch on; a deep link's run=1 always runs. The
// request counts are of /param_sweep and /sweep as the server would see them.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { BUILTIN_RUN_ON_PICK } from "../lib/settings";
import { invveeShape } from "./fixtures/solveShapes";
import { HARNESS_EXAMPLE, mountDesignSession, sessionReady, untilDom } from "./designSessionHarness";

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
  name: "dipoles.deck",
  label: "Deck",
  param_schema: [
    knob({}),
    knob({ name: "gap", label: "Gap", default: 0.25, min: 0, max: 1, step: 0.05, precision: 2, unit: null }),
  ],
};

const HEIGHT_VALUES = [2, 5, 8, 11];
const knobWorkbench = (param: string, values: number[], hold = false) => ({
  runs: true,
  kind: "knob",
  param,
  values,
  log: false,
  views: hold ? ["Rx", "Knobs"] : ["Rx", "Table"],
  ...(hold
    ? {
        hold: {
          objective: "resonance",
          knobs: ["gap"],
          bounds: { gap: [0, 1] },
          z0: null,
          warm_start: true,
          spec: { an: "Hold", objective: "resonance", adjust: ["gap"], z0: null, warm_start: true },
        },
      }
    : {}),
  note: null,
});
const entry = (name: string, workbench: unknown, study?: string) => ({
  name,
  summary: "",
  code: "",
  problems: [],
  workbench,
  ...(study ? { study: { source: "dipoles.deck_studies", name: study } } : {}),
});
const ANALYSES = {
  analyses: [
    entry("freq sweep", {
      runs: true,
      kind: "frequency",
      // Its own range, not the design's: the pick changes what is swept.
      range: { lo: 7.0, hi: 7.3, spacing: "lin", points: 7, source: "design" },
      level: "analysis",
      points: 7,
      views: ["Swr"],
      swr: { scale: null, threshold: null },
      note: null,
    }),
    entry("height", knobWorkbench("base", HEIGHT_VALUES)),
    entry("convergence", knobWorkbench("n_per_wire", [5, 9, 17, 33])),
    entry("match vs height", knobWorkbench("base", HEIGHT_VALUES, true)),
    entry("dipoles.deck_studies:held study", knobWorkbench("base", [3, 6, 9], true), "held study"),
  ],
};

// A socket that answers every solve at once.
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

const uiDefaults = (runOnPick: Record<string, boolean>, convergenceSweep = false) => ({
  path: "/home/ham/.antennaknobs/settings.toml",
  exists: true,
  writable: true,
  switches: {
    live: true,
    freq_sweep: true,
    convergence_sweep: convergenceSweep,
    pattern_renorm: true,
    refine: false,
    heatmap_currents: true,
    current_waveforms: false,
    wire_labels: false,
    feed_labels: true,
  },
  switches_set: [],
  antenna_view: { orientation: "auto" },
  workbench: { run_on_pick: { ...BUILTIN_RUN_ON_PICK, ...runOnPick } },
  problems: [],
});

async function open(
  url: string,
  opts: { runOnPick?: Record<string, boolean>; convergenceSweep?: boolean; onSave?: (b: Body) => void } = {},
) {
  const paramSweeps: Body[] = [];
  const sweeps: Body[] = [];
  const r = mountDesignSession({
    url,
    examples: [DECK],
    pinned: ["antenna", "zparam"],
    uiDefaults: uiDefaults(opts.runOnPick ?? {}, opts.convergenceSweep),
    routes: {
      "/sweep": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}"));
        sweeps.push(body);
        const lines = (body.freqs_mhz as number[]).map((f) =>
          JSON.stringify({ freq_mhz: f, z_re: 50, z_im: 0 }),
        );
        lines.push(JSON.stringify({ done: true }));
        return ndjson(lines);
      },
      "/param_sweep": (_url: string, init?: RequestInit) => {
        const b = JSON.parse(String(init?.body ?? "{}")) as Body & { param: string; values: number[] };
        paramSweeps.push(b);
        const lines = b.values.map((v) =>
          JSON.stringify({ param: b.param, value: v, z_re: 60 + v, z_im: 1, held: { gap: 0.2 }, converged: true }),
        );
        lines.push(JSON.stringify({ done: true, solver: "momwire" }));
        return ndjson(lines);
      },
      "/analyses": () => ({ ok: true, status: 200, json: async () => ANALYSES }) as unknown as Response,
      "/settings": (_url: string, init?: RequestInit) => {
        const b = JSON.parse(String(init?.body ?? "{}")) as Body;
        opts.onSave?.(b);
        return {
          ok: true,
          status: 200,
          json: async () => uiDefaults((b.workbench as { run_on_pick: Record<string, boolean> }).run_on_pick),
        } as unknown as Response;
      },
    },
  });
  await sessionReady(document.body);
  return { ...r, paramSweeps, sweeps };
}

const head = () => document.querySelector<HTMLElement>("[data-chart-kind]");
const picker = () => screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null;
// The dwell a dwelling sweep would wait out (500 ms), and more: a sweep that
// would start on its own has started by then.
const pastDwell = () => new Promise((r) => setTimeout(r, 900));

// The page on the design with its analyses listed, and the chart's own
// frequency sweep (the design's band, which a new chart runs) settled, so
// what follows a pick is the pick's.
async function ready(sweeps: Body[]) {
  // Put the chart on the stage: a new chart is the design's own frequency
  // sweep on the Smith chart, so its thumb is a Smith chart.
  const thumb = await untilDom(() => document.querySelector<HTMLElement>(".thumbstrip canvas.smith"));
  fireEvent.click(thumb);
  await untilDom(() => (picker() && [...picker()!.options].some((o) => o.value === "height")) || null);
  await untilDom(() => sweeps.length > 0 || null);
  await pastDwell();
}

async function pick(name: string) {
  fireEvent.change(picker()!, { target: { value: name } });
  await untilDom(() => head()?.dataset.analysis === name || null);
  await pastDwell();
}

const runButton = () =>
  screen.getAllByRole("button").find((b) => /^run( · re-run\?)?$/.test(b.textContent ?? "")) ?? null;

beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("with the built-in [workbench.run_on_pick]", () => {
  it.each(["convergence", "height", "match vs height", "dipoles.deck_studies:held study"])(
    "picking %s only selects it: no /param_sweep, and Run starts it",
    async (name) => {
      const { paramSweeps, sweeps } = await open("/?design=dipoles.deck");
      await ready(sweeps);
      await pick(name);
      expect(head()!.dataset.chartKind).toBe("knob");
      expect(paramSweeps).toHaveLength(0);
      // Ready, with its Run button: one press is one run, of the pick.
      fireEvent.click(runButton()!);
      await untilDom(() => paramSweeps.length > 0 || null);
      await pastDwell();
      expect(paramSweeps).toHaveLength(1);
      const want = ANALYSES.analyses.find((a) => a.name === name)!.workbench as { param: string; values: number[] };
      expect(paramSweeps[0]).toEqual(expect.objectContaining({ param: want.param, values: want.values }));
    },
  );

  it("picking a frequency sweep runs it", async () => {
    const { paramSweeps, sweeps } = await open("/?design=dipoles.deck");
    await ready(sweeps);
    const before = sweeps.length;
    await pick("freq sweep");
    await untilDom(() => sweeps.length > before || null);
    const last = sweeps[sweeps.length - 1].freqs_mhz as number[];
    expect(Math.min(...last)).toBeCloseTo(7.0);
    expect(Math.max(...last)).toBeCloseTo(7.3);
    expect(paramSweeps).toHaveLength(0);
  });

  it("a pick waits for Run even when the chart's auto re-run switch is on", async () => {
    // convergence_sweep seeds a knob chart's switch on: the pick still only
    // selects; the switch governs what happens after it.
    const { paramSweeps, sweeps } = await open("/?design=dipoles.deck", { convergenceSweep: true });
    await ready(sweeps);
    await pick("height");
    expect(head()!.dataset.dwell).toBe("1");
    expect(paramSweeps).toHaveLength(0);
  });
});

describe("a kind set true", () => {
  it("with knob = true served, a knob pick runs once", async () => {
    const { paramSweeps, sweeps } = await open("/?design=dipoles.deck", { runOnPick: { knob: true } });
    await ready(sweeps);
    await pick("height");
    await untilDom(() => paramSweeps.length > 0 || null);
    await pastDwell();
    expect(paramSweeps).toHaveLength(1);
    expect(paramSweeps[0]).toEqual(expect.objectContaining({ param: "base", values: HEIGHT_VALUES }));
    // Only that kind: a convergence pick still waits.
    await pick("convergence");
    expect(paramSweeps).toHaveLength(1);
  });

  it("the gear menu's switch applies to the next pick, and saves every kind", async () => {
    const user = userEvent.setup();
    let posted: Body | null = null;
    const { paramSweeps, sweeps } = await open("/?design=dipoles.deck", { onSave: (b) => (posted = b) });
    await ready(sweeps);
    await user.click(screen.getByRole("button", { name: "Tools menu" }));
    const box = screen.getByRole("checkbox", { name: "picking runs density ladders" }) as HTMLInputElement;
    expect(box.checked).toBe(false);
    await user.click(box);
    await user.click(screen.getByRole("button", { name: "save as my defaults" }));
    await untilDom(() => screen.queryByRole("status"));
    // Every kind is posted; the server writes only what differs.
    expect((posted as unknown as { workbench: unknown }).workbench).toEqual({
      run_on_pick: { ...BUILTIN_RUN_ON_PICK, convergence: true },
    });
    await pick("convergence");
    await untilDom(() => paramSweeps.length > 0 || null);
    expect(paramSweeps[0]).toEqual(expect.objectContaining({ param: "n_per_wire" }));
  });
});

describe("a deep link", () => {
  it("run=1 runs even with knob = false", async () => {
    const { paramSweeps } = await open("/?design=dipoles.deck&analysis=height&run=1");
    await untilDom(() => paramSweeps.length > 0 || null);
    await pastDwell();
    expect(paramSweeps).toHaveLength(1);
    expect(paramSweeps[0]).toEqual(expect.objectContaining({ param: "base", values: HEIGHT_VALUES }));
  });

  it("without run=1 follows the setting: knob = true runs", async () => {
    const { paramSweeps } = await open("/?design=dipoles.deck&analysis=height", { runOnPick: { knob: true } });
    await untilDom(() => paramSweeps.length > 0 || null);
    await pastDwell();
    expect(paramSweeps).toHaveLength(1);
  });

  it("without run=1 and knob = false only selects", async () => {
    const { paramSweeps } = await open("/?design=dipoles.deck&analysis=height");
    await untilDom(() => head()?.dataset.analysis === "height" || null);
    await pastDwell();
    expect(paramSweeps).toHaveLength(0);
  });
});
