// An analysis chart's engine and ground crosses, its curve cap, its legend
// and its duplicates (AK#1757, sweep-framework step 5 unit 4), through a
// real <DesignSession>.
//
// The oracle for each cross kind: the curve a multi-curve chart draws for
// (slot X, ground N) sends the /sweep request a single-curve chart sends
// with X and N the ACTIVE slots, in a fresh session, byte for byte but the
// lane's own metadata (the session id, the generation and the curve's
// stream). No slot is rewritten to get there.
//
// Mutation notes (run by hand, 2026-09-29; each reverted after):
//   - every cell on the active slot's engine (cellRequest's `slot` replaced
//     by `activeSlot`): "a ticked engine…" fails, the B curve's request
//     carries slot A's n_per_wire and model options;
//   - a ground cell ignoring its slot (buildCellRequest passing the active
//     ground slot instead of `cell.ground`): "a ticked ground…" fails, the
//     slot-Z curve's request is slot X's ground_model;
//   - the cap off by one (chartCells' capRefusal `n <= CURVE_CAP` made
//     `n < CURVE_CAP`): "the cross is capped…" fails, 3 x 2 is refused;
//   - a refused cell dropped from the legend (ChartLegend filtering the
//     refused entries out): the cap test's refusal row and "chartCrosses'
//     NEC-2 declining…" fail.
//
// Mutation notes (run by hand, 2026-10-01; each reverted after), the skip:
//   - the skip reverted to a refusal (chartCells' axis() pushing a refused
//     entry for an unslotted solver spec again): "E1 on Steve's slots…"
//     fails, the legend reads two refused rows beside the B-spline;
//   - the all-skipped fallback off (preselect leaving `[]`): "every listed
//     engine unslotted…" fails, one curve (the active slot) is drawn;
//   - the note dropped (DesignSession passing no `note`): both fail, the
//     legend is absent on the one-curve E1 chart.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { VIEW_PREFS_KEY } from "../components/session/useViewPrefs";
import { invveeShape } from "./fixtures/solveShapes";
import { HARNESS_EXAMPLE, mountReady, stageChart, untilDom } from "./designSessionHarness";

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

const DECK: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  bands: [
    { key: "14.175 MHz", label: "14.175 MHz", freq_mhz: 14.175, min_mhz: 14, max_mhz: 14.35 },
  ],
  default_freq: 14.175,
  has_design_freq: false,
  meas_freq_range_mhz: [14, 14.35],
  sweep_range: { lo: 14, hi: 14.35, spacing: "lin", step: 0.025, source: "file" },
  param_schema: [knob({})],
};

// Frequency analyses listing engines (the harness's slots are Steve's:
// B-spline d=2, B-spline d=1 and PyNEC): E1's three, of which only the
// B-spline is in a slot, and two of which none is.
const listing = (name: string, engines: string[]) => ({
  name,
  summary: `frequency; ${engines.length} curves (${engines.length} engines); views Swr`,
  code: "an.band_swr(cross=an.Cross(engines=(...)))",
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
    engines,
    grounds: null,
  },
});
const ANALYSES = {
  geometry: DECK.name,
  analyses: [
    listing("engines SWR", ["momwire:bspline", "momwire:razor-2p", "nec5"]),
    listing("unslotted SWR", ["momwire:razor-2p", "nec5"]),
  ],
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
  // Refinement off, so every /sweep here is a base sweep.
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

async function mount(opts: { layout?: "rail" | "grid"; mobile?: boolean } = {}) {
  const bodies: Body[] = [];
  const r = await mountReady({
    examples: [DECK],
    pinned: ["antenna", "zparam"],
    uiDefaults: UI_DEFAULTS,
    ...(opts.layout ? { layout: opts.layout } : {}),
    ...(opts.mobile ? { mobile: true } : {}),
    routes: {
      "/sweep": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}")) as Body;
        bodies.push(body);
        // Z moves with the engine's density and the ground, so each curve
        // is its own.
        const n = typeof body.n_per_wire === "number" ? body.n_per_wire : 0;
        const g = body.ground_model === "sommerfeld" ? 7 : body.ground ? 3 : 0;
        const lines = body.freqs_mhz.map((f) =>
          JSON.stringify({ freq_mhz: f, z_re: 30 + n + g + 100 * Math.abs(f - 14.2), z_im: g - n / 2 }),
        );
        lines.push(JSON.stringify({ done: true }));
        return ndjson(lines);
      },
      "/analyses": () =>
        ({ ok: true, status: 200, json: async () => ANALYSES }) as unknown as Response,
    },
  });
  return { ...r, bodies };
}

// Put the first chart on the rail's stage (a new chart is a frequency
// sweep on the Smith chart, so its thumb is a Smith chart).
async function chartOnStage(r: { container: HTMLElement }) {
  fireEvent.click(r.container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
  await untilDom(() => screen.queryByRole("button", { name: "Engines and grounds" }));
}

// The chart's own first sweep, landed.
const firstSweep = (bodies: Body[]) => untilDom(() => bodies.find((b) => b._stream === undefined));

const openCross = () => fireEvent.click(screen.getAllByRole("button", { name: "Engines and grounds" })[0]);
const crossBox = (prefix: string) => {
  const dlg = screen.getByRole("dialog", { name: "Engines and grounds" });
  const label = within(dlg)
    .getAllByRole("checkbox")
    .find((c) => c.closest("label")?.textContent?.startsWith(prefix));
  if (!label) throw new Error(`no box ${prefix}`);
  return label as HTMLInputElement;
};

// A request as the physics sees it: without the lane's metadata.
const LANE_METADATA = new Set(["_session", "_gen", "_stream"]);
function physics(b: Body): Record<string, unknown> {
  return Object.fromEntries(Object.entries(b).filter(([k]) => !LANE_METADATA.has(k)));
}

beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the engine cross", () => {
  it("a ticked engine's curve is the request a single chart sends with that slot active", async () => {
    const r = await mount();
    await chartOnStage(r);
    const own = await firstSweep(r.bodies);
    // The default is the active slot alone: one curve, no stream, no legend.
    expect(own.n_per_wire).toBe(15);
    expect(document.querySelector(".chart-legend")).toBeNull();

    openCross();
    fireEvent.click(crossBox("B: "));
    const cellB = await untilDom(() => r.bodies.find((b) => b._stream === "c0r1"));
    // Two curves on the chart, named by their slots in the legend.
    await untilDom(() => stageChart("canvas.smith")?.dataset.curves?.endsWith(":15") || null);
    const legend = await untilDom(() => document.querySelector<HTMLElement>(".chart-legend"));
    expect(legend.dataset.curves).toBe("2");
    expect(legend.textContent).toContain("A: B-spline d=2");
    expect(legend.textContent).toContain("B: B-spline d=1");
    // The active slot is untouched: still A, still what the live solve reads.
    expect(
      screen.getByRole("tab", { name: /^Solver slot A/ }).getAttribute("aria-selected"),
    ).toBe("true");

    // The oracle: a fresh session with B active and a one-curve chart.
    cleanup();
    vi.unstubAllGlobals();
    vi.stubGlobal("WebSocket", EchoWebSocket);
    const r2 = await mount();
    fireEvent.click(screen.getByRole("tab", { name: /^Solver slot B/ }));
    await chartOnStage(r2);
    const single = await untilDom(() =>
      r2.bodies.find((b) => b._stream === undefined && b.n_per_wire === 20),
    );
    expect(physics(cellB)).toEqual(physics(single));
  });
});

describe("the ground cross", () => {
  it("a ticked ground's curve is the request a single chart sends with that ground slot active", async () => {
    const r = await mount();
    await chartOnStage(r);
    const own = await firstSweep(r.bodies);
    expect(own.ground_model).toBe("fast");

    openCross();
    fireEvent.click(crossBox("Z: "));
    const cell3 = await untilDom(() => r.bodies.find((b) => b._stream === "c0r1"));
    expect(cell3.ground_model).toBe("sommerfeld");
    // The active ground slot is untouched.
    expect(
      screen.getByRole("tab", { name: /^Ground slot X/ }).getAttribute("aria-selected"),
    ).toBe("true");

    cleanup();
    vi.unstubAllGlobals();
    vi.stubGlobal("WebSocket", EchoWebSocket);
    const r2 = await mount();
    fireEvent.click(screen.getByRole("tab", { name: /^Ground slot Z/ }));
    await chartOnStage(r2);
    const single = await untilDom(() =>
      r2.bodies.find((b) => b._stream === undefined && b.ground_model === "sommerfeld"),
    );
    expect(physics(cell3)).toEqual(physics(single));
  });
});

describe("engines x grounds", () => {
  it("the cross is capped at six curves: 3 x 2 draws, 3 x 3 is refused in the CLI's words", async () => {
    const r = await mount();
    await chartOnStage(r);
    await firstSweep(r.bodies);
    openCross();
    fireEvent.click(crossBox("B: "));
    fireEvent.click(crossBox("C: "));
    fireEvent.click(crossBox("Y: "));
    // Six curves: the chart's own and five streams.
    await untilDom(
      () =>
        ["c0r1", "c0r2", "c0r3", "c0r4", "c0r5"].every((s) => r.bodies.some((b) => b._stream === s)) ||
        null,
    );
    await untilDom(() => document.querySelector<HTMLElement>(".chart-legend")?.dataset.curves === "6" || null);
    // Each of the 3 engines on each of the 2 grounds, once.
    const cells = new Set(
      r.bodies.map((b) => `${b.solver}/${b.n_per_wire ?? ""}/${b.ground_model}/${b.ground}`),
    );
    expect(cells.size).toBe(6);

    const before = r.bodies.length;
    fireEvent.click(crossBox("Z: "));
    const refusal = "REFUSED: 3 engines x 3 grounds = 9 curves, over the cap of 6";
    await untilDom(() => document.querySelector(".chart-legend")?.textContent?.includes(refusal) || null);
    // Refused, not truncated: the popover says so, and nothing more is sent.
    expect(within(screen.getByRole("dialog", { name: "Engines and grounds" })).getByRole("alert").textContent).toBe(
      refusal,
    );
    expect(stageChart("canvas.smith")?.dataset.curves).toBe("");
    expect(r.bodies.length).toBe(before);
  });
});

describe("the legend", () => {
  const pickAnalysis = async (r: { bodies: Body[] }, name: string) => {
    const before = r.bodies.length;
    fireEvent.change(screen.getByRole("combobox", { name: "Analysis" }), { target: { value: name } });
    await untilDom(() => r.bodies.length > before || null);
    return before;
  };

  it("E1 on Steve's slots: one B-spline curve, the unslotted engines skipped in a note, nothing refused", async () => {
    const r = await mount();
    await chartOnStage(r);
    await firstSweep(r.bodies);
    const before = await pickAnalysis(r, "engines SWR");
    const legend = await untilDom(() => document.querySelector<HTMLElement>(".chart-legend"));
    // No refusal anywhere: no refused row, no error ink. (Asserted first, so
    // the mutation check in the header fails HERE, not on the rows below.)
    expect(legend.querySelectorAll('[data-refused="1"]')).toHaveLength(0);
    expect(legend.querySelector(".chart-legend-why")).toBeNull();
    expect(legend.querySelector(".is-refused")).toBeNull();
    const rows = [...legend.querySelectorAll<HTMLElement>(".chart-legend-row")];
    expect(rows.map((row) => [row.textContent, row.dataset.refused])).toEqual([["momwire:bspline", "0"]]);
    expect(legend.querySelector('[role="note"]')?.textContent).toBe(
      "skipped: razor-2p, NEC-5, which no slot holds. Put one in a slot to include it.",
    );
    expect(legend.dataset.curves).toBe("1");
    // One curve, on slot A (B-spline d=2's density), and no other stream.
    const sent = r.bodies.slice(before);
    expect(sent.every((b) => b._stream === undefined && b.n_per_wire === 15)).toBe(true);
  });

  it("every listed engine unslotted: a curve on every slot, and the note says so", async () => {
    const r = await mount();
    await chartOnStage(r);
    await firstSweep(r.bodies);
    await pickAnalysis(r, "unslotted SWR");
    await untilDom(() => (["c0r1", "c0r2"].every((s) => r.bodies.some((b) => b._stream === s)) ? true : null));
    const legend = await untilDom(() =>
      document.querySelector<HTMLElement>(".chart-legend")?.dataset.curves === "3"
        ? document.querySelector<HTMLElement>(".chart-legend")
        : null,
    );
    const rows = [...legend.querySelectorAll<HTMLElement>(".chart-legend-row")];
    expect(rows.map((row) => [row.textContent, row.dataset.refused])).toEqual([
      ["A: B-spline d=2", "0"],
      ["B: B-spline d=1", "0"],
      ["C: PyNEC", "0"],
    ]);
    expect(legend.querySelector('[role="note"]')?.textContent).toBe(
      "skipped: razor-2p, NEC-5, which no slot holds, so the chart draws your slots instead. Put one in a slot to include it.",
    );
    // The three curves are the three slots.
    const last = (stream: string | undefined) => [...r.bodies].reverse().find((b) => b._stream === stream);
    expect(
      [undefined, "c0r1", "c0r2"].map((s) => {
        const b = last(s);
        return [b?.solver, b?.n_per_wire];
      }),
    ).toEqual([
      ["momwire", 15],
      ["momwire", 20],
      ["pynec", 21],
    ]);
  });
});

describe("the live point", () => {
  it("follows a knob while the curves wait for the dwell", async () => {
    const user = userEvent.setup();
    const r = await mount();
    await chartOnStage(r);
    await firstSweep(r.bodies);
    fireEvent.change(screen.getByRole("combobox", { name: "Chart view" }), { target: { value: "Swr" } });
    openCross();
    fireEvent.click(crossBox("B: "));
    await untilDom(() => r.bodies.some((b) => b._stream === "c0r1") || null);
    fireEvent.keyDown(document.body, { key: "Escape" });
    const swr = await untilDom(() => {
      const c = stageChart("canvas.sweep-vswr");
      return c?.dataset.curves?.endsWith(":15") && c.dataset.phase === "idle" ? c : null;
    });
    await user.click(screen.getByRole("checkbox", { name: "auto re-run" }));
    const before = r.bodies.length;
    // Gap 0.25: Z = 50 − j10 Ω, SWR 1.2210; two steps up, 54 − j10 Ω, SWR
    // 1.2299. (One step, 52 − j10 Ω, is SWR 1.2210 again: the same |Γ|.)
    expect(swr.dataset.current).toBe("1.2210");
    const gap = screen.getByRole("slider", { name: "Gap" });
    fireEvent.keyDown(gap, { key: "ArrowUp" });
    fireEvent.keyDown(gap, { key: "ArrowUp" });
    await untilDom(() => stageChart("canvas.sweep-vswr")?.dataset.current === "1.2299" || null);
    // The marker moved; both curves stay, stale, and nothing re-sweeps.
    expect(stageChart("canvas.sweep-vswr")?.dataset.stale).toBe("1");
    expect(stageChart("canvas.sweep-vswr")?.dataset.curves).toBe("B|X:15");
    expect(stageChart("canvas.sweep-vswr")?.dataset.phase).toBe("idle");
    expect(r.bodies.length).toBe(before);
  });
});

describe("duplicate a chart", () => {
  it("adds a chart of its own, which a close removes; nothing about it is stored", async () => {
    const r = await mount({ layout: "grid" });
    await firstSweep(r.bodies);
    expect(screen.getAllByRole("group", { name: "Analysis chart" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Duplicate this chart" }));
    const heads = await untilDom(() => {
      const h = screen.queryAllByRole("group", { name: "Analysis chart" });
      return h.length === 2 ? h : null;
    });
    // Its own runners: its sweep runs on a stream of its own.
    await untilDom(() => r.bodies.some((b) => b._stream === "c1r0") || null);
    // Its own view: SWR on the copy leaves the first on the Smith chart.
    fireEvent.change(within(heads[1]).getByRole("combobox", { name: "Chart view" }), {
      target: { value: "Swr" },
    });
    await untilDom(() => document.querySelector("canvas.sweep-vswr"));
    expect(document.querySelectorAll("canvas.smith")).toHaveLength(1);
    // Session-only: the stored rail preferences never hold the copy.
    expect(localStorage.getItem(VIEW_PREFS_KEY) ?? "").not.toContain("zparam2");
    fireEvent.click(within(heads[1]).getByRole("button", { name: "Close this chart" }));
    await untilDom(() => screen.queryAllByRole("group", { name: "Analysis chart" }).length === 1 || null);
    // The first chart has no close of its own.
    expect(screen.queryByRole("button", { name: "Close this chart" })).toBeNull();
  });
});

describe("on a phone", () => {
  it("the checkboxes sit behind one header button, in a popover on the page body", async () => {
    await mount({ mobile: true });
    const btn = await untilDom(() => screen.queryByRole("button", { name: "Engines and grounds" }));
    expect(btn.closest(".zparam-controls")).not.toBeNull();
    fireEvent.click(btn);
    const dlg = screen.getByRole("dialog", { name: "Engines and grounds" });
    // Portaled: outside the carousel page, which clips and scrolls.
    expect(dlg.closest(".mobile-carousel")).toBeNull();
    expect(dlg.parentElement).toBe(document.body);
  });
});
