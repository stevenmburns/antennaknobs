// The analysis chart (AK#1757, sweep-framework step 5 unit 2) through a real
// <DesignSession>: a chart that owns its picker, Run, a dwell switch and the
// live point, and draws what it picked in place.
//   - Run re-runs the chart's analysis, a knob sweep or a frequency sweep;
//   - the dwell switch: ON, a knob change re-sweeps after the dwell; OFF, it
//     does not (the curve is kept, marked stale). Asserted on the runner's
//     decision (data-phase queued vs idle, inside the change's own act), never
//     by sleeping past the dwell;
//   - the live point (the measurement frequency's marker) follows a knob
//     change whether the switch is on or off;
//   - a greyed (unrunnable) pick does nothing;
//   - nothing about the chart — its pick, switch, range or scale — is written
//     to the browser's storage or to a settings save.
//
// Mutation notes (run by hand, 2026-09-28):
//   - picking stops running (pickAnalysis returns right after its blocked
//     check): every test here that picks fails, waiting on a /sweep or
//     /param_sweep that never comes, and so do analysisPicker.session's and
//     analysisPicker.frequency.session's picks (9 of 10 across the three
//     files; the greyed-pick test, which expects nothing, still passes);
//   - the frequency runner's switch ignored, `auto` pinned true: "with the
//     switch off…" and the live-point test's switch-off step fail at once
//     (data-phase "queued" where "idle" is expected); pinned false: "with the
//     switch on…" fails at once ("idle" where "queued" is expected);
//   - the knob runner's switch ignored (`auto` pinned true, or today's rule
//     `isDensity`): the knob test fails at once on one side or the other.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { invveeShape } from "./fixtures/solveShapes";
import {
  HARNESS_EXAMPLE,
  mountReady,
  stageChart,
  sweepBaseDone,
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
  ],
};

const HEIGHT_VALUES = Array.from({ length: 37 }, (_, i) => 2 + 0.5 * i);
const HOLD_WHY = "hold (optimise at each point): not in the workbench yet (sweep-framework step 6)";

const ANALYSES = {
  geometry: DECK.name,
  analyses: [
    {
      name: "wide SWR",
      summary: "frequency (freq); 1 curve; views Swr",
      code: "an.band_swr()",
      problems: [],
      workbench: {
        runs: true,
        kind: "frequency",
        note: null,
        views: ["Swr", "Smith"],
        range: { lo: 13.9, hi: 14.5, spacing: "lin", points: 25, source: "design" },
        level: "analysis",
        points: 25,
        swr: { scale: "rho", threshold: 1.5 },
      },
    },
    {
      name: "height",
      summary: "height (base) 2..20, 37 points; 1 curve; views Rx",
      code: 'an.Analysis("height", an.Sweep(an.HEIGHT, 2, 20, points=37))',
      problems: [],
      workbench: { runs: true, kind: "knob", param: "base", values: HEIGHT_VALUES, log: false, note: null },
    },
    {
      name: "match vs height",
      summary: "height (base) 2..20, 37 points; 1 curve; hold match_z0",
      code: 'an.Analysis("match vs height")',
      problems: [],
      workbench: { runs: false, why: HOLD_WHY },
    },
  ],
};

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

type ParamBody = Record<string, unknown> & { param: string; values: number[] };

async function mount() {
  const sweeps: number[][] = [];
  const paramSweeps: ParamBody[] = [];
  const saves: unknown[] = [];
  const r = await mountReady({
    // A pick starts its analysis, as before [workbench.run_on_pick] (AC6LA #179).
    pickRuns: true,
    examples: [DECK],
    pinned: ["antenna", "zparam"],
    uiDefaults: {
      path: "/x/settings.toml",
      exists: false,
      writable: true,
      // The built-in switches: freq_sweep (a frequency chart's dwell switch
      // on, unit 3) and convergence_sweep off (a knob chart's off).
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
      switches_set: [],
      antenna_view: { orientation: "iso" },
      ground: null,
      problems: [],
    },
    routes: {
      "/sweep": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}"));
        const freqs = body.freqs_mhz as number[];
        if (!body._refine) sweeps.push(freqs);
        const lines = freqs.map((f) =>
          JSON.stringify({ freq_mhz: f, z_re: 50 * (1 + 20 * Math.abs(f - 14.2)), z_im: 0 }),
        );
        lines.push(JSON.stringify({ done: true }));
        return ndjson(lines);
      },
      "/param_sweep": (_url: string, init?: RequestInit) => {
        const b = JSON.parse(String(init?.body ?? "{}")) as ParamBody;
        paramSweeps.push(b);
        const lines = b.values.map((v) =>
          JSON.stringify({ param: b.param, value: v, z_re: 60 + v, z_im: -30 + v, solver: "momwire" }),
        );
        lines.push(JSON.stringify({ done: true, solver: "momwire" }));
        return ndjson(lines);
      },
      "/analyses": () =>
        ({ ok: true, status: 200, json: async () => ANALYSES }) as unknown as Response,
      "/settings": (_url: string, init?: RequestInit) => {
        saves.push(JSON.parse(String(init?.body ?? "{}")));
        return {
          ok: true,
          status: 200,
          json: async () => ({ ok: true, ui_defaults: { path: "/x/settings.toml", writable: true } }),
        } as unknown as Response;
      },
    },
  });
  // Put the chart on the stage: a new chart is the design's own frequency
  // sweep on the Smith chart (unit 3), so its thumb is a Smith chart.
  fireEvent.click(r.container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
  const select = await untilDom(
    () => screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null,
  );
  // The design's own sweep the chart opens on lands first (15 points over
  // the deck's 14–14.35 MHz at 25 kHz), and no knob sweep with it.
  await untilDom(() => sweeps.length > 0 || null);
  await untilDom(() => stageChart("canvas.smith")?.dataset.phase === "idle" || null);
  expect(sweeps[0]).toHaveLength(15);
  expect(paramSweeps).toHaveLength(0);
  return { ...r, select, sweeps, paramSweeps, saves };
}

const head = () => screen.getByRole("group", { name: "Analysis chart" });
const dwellBox = () => screen.getByRole("checkbox", { name: "auto re-run" }) as HTMLInputElement;
const vswr = () => stageChart("canvas.sweep-vswr");
const rx = () => stageChart("canvas.zparam");
const heightUp = () =>
  fireEvent.keyDown(screen.getByRole("slider", { name: "Height" }), { key: "ArrowUp" });
const gapUp = () => fireEvent.keyDown(screen.getByRole("slider", { name: "Gap" }), { key: "ArrowUp" });

beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a frequency analysis in the chart", () => {
  it("picking it runs it in the chart, on its first view; Run re-runs it", async () => {
    const user = userEvent.setup();
    const { select, sweeps, paramSweeps } = await mount();
    const knobSweeps = paramSweeps.length;
    fireEvent.change(select, { target: { value: "wide SWR" } });
    await untilDom(() => sweeps.some((f) => f.length === 25) || null);
    const chart = await untilDom(() => vswr());
    expect(rx()).toBeNull();
    expect(head().dataset.chartKind).toBe("frequency");
    expect(head().dataset.analysis).toBe("wide SWR");
    await sweepBaseDone(chart);
    await untilDom(() => chart.dataset.points === "25" || null);
    expect(chart.dataset.axis).toBe("rho");
    expect(paramSweeps).toHaveLength(knobSweeps);

    // Run: the same 25 points again, now.
    const n = sweeps.length;
    await user.click(screen.getByRole("button", { name: "run" }));
    await untilDom(() => sweeps.length > n || null);
    expect(sweeps[sweeps.length - 1]).toHaveLength(25);

    // Its other view, in the same chart and from the same sweep.
    fireEvent.change(screen.getByRole("combobox", { name: "Chart view" }), {
      target: { value: "Smith" },
    });
    const smith = await untilDom(
      () => document.querySelector<HTMLElement>(".zparam-plot canvas.smith"),
    );
    expect(smith).toBeTruthy();
  });

  it("with the switch on (its default) a knob change re-sweeps after the dwell", async () => {
    const { select, sweeps } = await mount();
    fireEvent.change(select, { target: { value: "wide SWR" } });
    const chart = await untilDom(() => vswr());
    await untilDom(() => chart.dataset.points === "25" && chart.dataset.phase === "idle" ? true : null);
    expect(dwellBox().checked).toBe(true);
    expect(head().dataset.dwell).toBe("1");
    const n = sweeps.length;
    gapUp();
    // The runner decided inside the change's act: a sweep is queued.
    expect(vswr()!.dataset.phase).toBe("queued");
    await untilDom(() => sweeps.length > n || null);
    expect(sweeps[sweeps.length - 1]).toHaveLength(25);
  });

  it("with the switch off a knob change runs nothing; the curve stays, stale; Run re-runs", async () => {
    const user = userEvent.setup();
    const { select, sweeps } = await mount();
    fireEvent.change(select, { target: { value: "wide SWR" } });
    const chart = await untilDom(() => vswr());
    await untilDom(() => chart.dataset.points === "25" && chart.dataset.phase === "idle" ? true : null);
    await user.click(dwellBox());
    expect(head().dataset.dwell).toBe("0");
    const n = sweeps.length;
    gapUp();
    expect(vswr()!.dataset.phase).toBe("idle");
    await untilDom(
      () => document.querySelector<HTMLElement>(".analysis-chart-freq")?.dataset.stale === "1" || null,
    );
    expect(vswr()!.dataset.points).toBe("25");
    expect(sweeps.length).toBe(n);
    await user.click(screen.getByRole("button", { name: "run · re-run?" }));
    await untilDom(() => sweeps.length > n || null);
    await untilDom(
      () => document.querySelector<HTMLElement>(".analysis-chart-freq")?.dataset.stale === "0" || null,
    );
  });

  it("the live point follows a knob change with the switch on or off", async () => {
    const user = userEvent.setup();
    const { select } = await mount();
    fireEvent.change(select, { target: { value: "wide SWR" } });
    const chart = await untilDom(() => vswr());
    await untilDom(() => chart.dataset.points === "25" && chart.dataset.phase === "idle" ? true : null);
    // R = 40 + 2·7 = 54 Ω at the measurement frequency: SWR 1.08.
    await untilDom(() => vswr()!.dataset.current === "1.0800" || null);
    // Switch on: the marker moves with Height (R = 55 Ω, SWR 1.1).
    heightUp();
    await untilDom(() => vswr()!.dataset.current === "1.1000" || null);
    // Switch off: the curve waits, the marker still moves (R = 56 Ω).
    await user.click(dwellBox());
    heightUp();
    expect(vswr()!.dataset.phase).toBe("idle");
    await untilDom(() => vswr()!.dataset.current === "1.1200" || null);
  });
});

describe("a knob analysis in the chart", () => {
  it("draws R/X in the chart; switch off (its default) a change waits; on, it re-sweeps", async () => {
    const user = userEvent.setup();
    const { select, paramSweeps } = await mount();
    const before = paramSweeps.length;
    fireEvent.change(select, { target: { value: "height" } });
    await untilDom(() => paramSweeps.length > before || null);
    expect(paramSweeps[paramSweeps.length - 1]).toEqual(
      expect.objectContaining({ param: "base", values: HEIGHT_VALUES }),
    );
    await untilDom(() => rx()?.dataset.points === "37" && rx()!.dataset.phase === "idle" ? true : null);
    expect(head().dataset.chartKind).toBe("knob");
    expect(head().dataset.dwell).toBe("0");

    // Off: another knob marks it stale and runs nothing; the guide (the live
    // point on this chart) does not wait either.
    let n = paramSweeps.length;
    gapUp();
    expect(rx()!.dataset.phase).toBe("idle");
    await untilDom(() => rx()!.dataset.stale === "1" || null);
    expect(paramSweeps.length).toBe(n);
    heightUp();
    await untilDom(() => rx()!.dataset.guide === "7.5" || null);
    expect(paramSweeps.length).toBe(n);

    // Run re-runs it.
    await user.click(screen.getByRole("button", { name: "run · re-run?" }));
    await untilDom(() => paramSweeps.length > n || null);
    await untilDom(() => rx()!.dataset.phase === "idle" && rx()!.dataset.stale === "0" ? true : null);

    // On: the next change re-sweeps after the dwell.
    await user.click(dwellBox());
    expect(head().dataset.dwell).toBe("1");
    n = paramSweeps.length;
    gapUp();
    expect(rx()!.dataset.phase).toBe("queued");
    await untilDom(() => paramSweeps.length > n || null);
    expect(paramSweeps[paramSweeps.length - 1].param).toBe("base");

    // And a finished sweep's Run re-runs it too.
    await untilDom(() => rx()!.dataset.phase === "idle" && rx()!.dataset.points === "37" ? true : null);
    n = paramSweeps.length;
    await user.click(screen.getByRole("button", { name: "37/37 · run" }));
    await untilDom(() => paramSweeps.length > n || null);
  });
});

describe("a greyed pick", () => {
  it("does nothing: no sweep, no change of kind", async () => {
    const { select, sweeps, paramSweeps } = await mount();
    const hold = [...select.options].find((o) => o.value === "match vs height")!;
    expect(hold.disabled).toBe(true);
    expect(hold.title).toBe(HOLD_WHY);
    const [s, p] = [sweeps.length, paramSweeps.length];
    fireEvent.change(select, { target: { value: "match vs height" } });
    expect(stageChart("canvas.smith")!.dataset.phase).toBe("idle");
    expect(head().dataset.chartKind).toBe("frequency");
    expect(head().dataset.analysis).not.toBe("match vs height");
    expect(sweeps.length).toBe(s);
    expect(paramSweeps.length).toBe(p);
  });
});

describe("a chart is session-only", () => {
  it("its pick, switch, range and scale reach neither the browser's storage nor a settings save", async () => {
    const user = userEvent.setup();
    const { select, saves } = await mount();
    const stored = () => JSON.stringify({ ...localStorage });
    const storedBefore = stored();
    fireEvent.change(select, { target: { value: "wide SWR" } });
    const chart = await untilDom(() => vswr());
    await sweepBaseDone(chart);
    await user.click(dwellBox());
    const to = screen.getByLabelText("to MHz") as HTMLInputElement;
    await user.clear(to);
    await user.type(to, "14.6{Enter}");
    // The chart has them...
    expect(head().dataset.analysis).toBe("wide SWR");
    expect(head().dataset.dwell).toBe("0");
    expect(chart.dataset.axis).toBe("rho");
    // ...the browser does not: storage is as it was (the pick's ρ scale and
    // 1.5:1 threshold were not written to the viewer's preferences).
    expect(stored()).toBe(storedBefore);
    for (const word of ["wide SWR", "rho", "14.6", "1.5"]) expect(stored()).not.toContain(word);

    // A settings save carries the session's switches, not the chart's.
    await user.click(screen.getByRole("button", { name: "Tools menu" }));
    await user.click(screen.getByRole("button", { name: /save as my defaults/i }));
    await untilDom(() => saves.length > 0 || null);
    const body = JSON.stringify(saves[0]);
    for (const word of ["wide SWR", "rho", "14.6", "dwell", "analysis"]) {
      expect(body).not.toContain(word);
    }
  });
});
