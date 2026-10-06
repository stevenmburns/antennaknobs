// A knob's family of patterns on the "Sweep a knob" chart (AK#1935), through
// a real <DesignSession>. Steve (2026-10-06): "'sweep' any knob … you specify
// which knob you want with the starting and ending values and step size
// (linear) or number of points (linear/log)". The Python half (the served
// frequency step, the keep's to_code round trip, an opened deck's SY knob)
// is tests/test_patterns_any_knob_1935.py.
//
// What is pinned: the knob chart's view menu offers the pattern views;
// picking one asks POST /pattern_cell once per value of the chart's knob
// range, each request the session's with that knob set (and, for the
// measurement frequency, its own field), on a lane stream of its own; the
// cut draws one trace per value, labelled as the CLI's `step_label` labels
// it; a range over the cap is clamped on the way in; with
// [workbench.run_on_pick] pattern off the pick alone sends nothing; the
// step box moves `to` onto the last value; and "copy" sends the family.
//
// Mutation notes (run by hand, 2026-10-06; each reverted after):
//   - DesignSession's listedFor returning chartListed alone (no family): a
//     single cell, no `base` on any request; "one per value" fails;
//   - buildRequestFor not setting measurement_freq_mhz on a freq step: the
//     frequency test's measurement_freq_mhz check fails;
//   - onChartView ignoring runOnPick (always runPicked): the "waits for Run"
//     test sees six requests before Run (it survived a 300 ms settle, which
//     is why the settle is 1.5 s).
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { invveeShape } from "./fixtures/solveShapes";
import { HARNESS_EXAMPLE, mountReady, untilDom } from "./designSessionHarness";

vi.setConfig({ testTimeout: 30_000 });

const knob = (over: Partial<SchemaParamSpec>): SchemaParamSpec => ({
  name: "base",
  label: "Base",
  default: 7,
  kind: "float",
  min: 4,
  max: 14,
  step: 0.5,
  precision: 1,
  unit: "m",
  visible_when: null,
  ...over,
});

const DESIGN: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  bands: [{ key: "28.47 MHz", label: "28.47 MHz", freq_mhz: 28.47, min_mhz: 28, max_mhz: 29.7 }],
  default_freq: 28.47,
  has_design_freq: false,
  meas_freq_range_mhz: [28, 29.7],
  param_schema: [knob({})],
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

// A cell's pattern: a lobe whose size is its mast height (or its frequency),
// so each value's trace is its own.
function cell(body: Body) {
  const size = Number(body.base) + Number(body.measurement_freq_mhz) / 10;
  const lobe = (n: number) => Array.from({ length: n }, (_, i) => size - 10 * Math.abs(Math.sin((Math.PI * i) / n)));
  return {
    available: true,
    solve: {
      ...invveeShape,
      feeds: undefined,
      geometry: body.geometry,
      solve_id: `cell-${size}`,
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
      peak_gain_dbi: size,
      takeoff_deg: 20,
      azimuth_deg: 0,
      front_to_back_db: 0.5,
      az_beamwidth_deg: 80,
      el_beamwidth_deg: 20,
      rdf_db: 9.1,
    },
  };
}

async function mount(opts: { patternOnPick?: boolean } = {}) {
  const cells: Body[] = [];
  const keeps: Body[] = [];
  const r = await mountReady({
    examples: [DESIGN],
    pinned: ["antenna", "zparam"],
    ...(opts.patternOnPick === false ? { uiDefaults: { workbench: { run_on_pick: { pattern: false } } } } : {}),
    routes: {
      "/pattern_cell": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}")) as Body;
        cells.push(body);
        return { ok: true, status: 200, json: async () => cell(body) } as unknown as Response;
      },
      "/analyses": () => ({ ok: true, status: 200, json: async () => ({ analyses: [] }) }) as unknown as Response,
      "/keep": (_url: string, init?: RequestInit) => {
        keeps.push(JSON.parse(String(init?.body ?? "{}")) as Body);
        return {
          ok: true,
          status: 200,
          json: async () => ({ code: "an.patterns(...)", name: "patterns over base", problems: [], study_refusal: null }),
        } as unknown as Response;
      },
      // The knob sweep is never run here (a knob pick waits for Run).
      "/param_sweep": () => ({ ok: false, status: 500, json: async () => ({}) }) as unknown as Response,
    },
  });
  // The chart on the stage, then "Sweep a knob".
  // eslint-disable-next-line testing-library/no-node-access -- the thumbnail is a bare canvas
  fireEvent.click(r.container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
  const picker = await untilDom(() => {
    const b = screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null;
    return b && [...b.options].some((o) => o.textContent === "Sweep a knob") ? b : null;
  });
  const entry = [...picker.options].find((o) => o.textContent === "Sweep a knob")!.value;
  fireEvent.change(picker, { target: { value: entry } });
  await untilDom(() => screen.getByRole("group", { name: "Analysis chart" }).dataset.chartKind === "knob" || null);
  return { ...r, cells, keeps };
}

const viewMenu = () => screen.getByRole("combobox", { name: "Chart view" }) as HTMLSelectElement;
const optionValue = (select: HTMLSelectElement, text: string) =>
  [...select.options].find((o) => o.textContent === text)!.value;

const traces = (name: string) => {
  const c = screen.queryByRole("img", { name });
  return c ? (JSON.parse(c.dataset.traces ?? "[]") as string[]) : null;
};

// Commit a number box: type, then blur (CommitNumber commits on blur).
function commit(label: string, value: string) {
  const box = screen.getByRole("textbox", { name: label });
  fireEvent.change(box, { target: { value } });
  fireEvent.blur(box);
}

beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a knob's family of patterns on the 'Sweep a knob' chart", () => {
  it("offers the pattern views, and Elevation solves one pattern per value, labelled by value", async () => {
    const r = await mount();
    expect([...viewMenu().options].map((o) => o.textContent)).toEqual([
      "R / X",
      "Smith",
      "Table",
      "Elevation @ 0° az",
      "Azimuth @ 10° el",
      "Pattern table",
    ]);
    fireEvent.change(viewMenu(), { target: { value: optionValue(viewMenu(), "Elevation @ 0° az") } });
    await untilDom(() => screen.getByRole("group", { name: "Analysis chart" }).dataset.chartKind === "pattern" || null);
    // The knob's own range, 4…14 over 11 points, clamped to the cap of 6.
    expect((screen.getByRole("textbox", { name: "values" }) as HTMLInputElement).value).toBe("6");
    const sent = await untilDom(() => (r.cells.length >= 6 ? r.cells : null));
    expect(sent.map((b) => b.base)).toEqual([4, 6, 8, 10, 12, 14]);
    // Each value on a lane stream of its own; the chart's cut angles.
    expect(sent.map((b) => b._stream)).toEqual([undefined, "c0r1", "c0r2", "c0r3", "c0r4", "c0r5"]);
    for (const b of sent) expect([b.elev_az_deg, b.az_elev_deg]).toEqual([0, 10]);
    const drawn = await untilDom(() => {
      const t = traces("Elevation cut at 0° azimuth");
      return t && t.length === 6 ? t : null;
    });
    expect(drawn).toEqual(["base = 4", "base = 6", "base = 8", "base = 10", "base = 12", "base = 14"]);
    // The picker still reads "Sweep a knob": a family is that chart's.
    const picker = screen.getByRole("combobox", { name: "Analysis" }) as HTMLSelectElement;
    expect(picker.selectedOptions[0].textContent).toBe("Sweep a knob");
    // Back to R / X: the knob sweep of the same knob and range.
    fireEvent.change(viewMenu(), { target: { value: "Rx" } });
    await untilDom(() => screen.getByRole("group", { name: "Analysis chart" }).dataset.chartKind === "knob" || null);
  });

  it("with run_on_pick pattern off, the pick alone sends nothing; Run solves the family", async () => {
    const r = await mount({ patternOnPick: false });
    fireEvent.change(viewMenu(), { target: { value: optionValue(viewMenu(), "Elevation @ 0° az") } });
    await untilDom(() => screen.getByRole("group", { name: "Analysis chart" }).dataset.chartKind === "pattern" || null);
    // A settle long enough for a pick that runs to have sent its cells: with
    // the pick forced to run (the mutation below), the first request lands
    // after ~0.5 s here, so 300 ms proved nothing and 1.5 s does.
    await new Promise((res) => setTimeout(res, 1500));
    expect(r.cells).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "run" }));
    await untilDom(() => (r.cells.length >= 6 ? true : null));
  });

  it("the step box moves `to` onto the last value; the points box refuses more than the cap", async () => {
    const r = await mount();
    fireEvent.change(viewMenu(), { target: { value: optionValue(viewMenu(), "Elevation @ 0° az") } });
    await untilDom(() => (r.cells.length >= 6 ? true : null));
    // 4…14 by 3: 4, 7, 10, 13, and `to` reads 13.
    commit("step", "3");
    await untilDom(() => (screen.getByRole("textbox", { name: "to" }) as HTMLInputElement).value === "13" || null);
    expect((screen.getByRole("textbox", { name: "values" }) as HTMLInputElement).value).toBe("4");
    await untilDom(() => (r.cells.some((b) => b.base === 13) ? true : null));
    // A step that would make more than six values is refused, and reverts.
    commit("step", "1");
    expect((screen.getByRole("textbox", { name: "step" }) as HTMLInputElement).value).toBe("3");
    commit("values", "9");
    expect((screen.getByRole("textbox", { name: "values" }) as HTMLInputElement).value).toBe("4");
  });

  it("steps the measurement frequency across the band: each cell's request carries its MHz", async () => {
    const r = await mount();
    fireEvent.change(viewMenu(), { target: { value: optionValue(viewMenu(), "Elevation @ 0° az") } });
    await untilDom(() => (r.cells.length >= 6 ? true : null));
    const before = r.cells.length;
    fireEvent.change(screen.getByRole("combobox", { name: "Parameter" }), { target: { value: "freq" } });
    // The band's bottom, middle and top (28–29.7 MHz).
    const sent = await untilDom(() => (r.cells.length >= before + 3 ? r.cells.slice(before) : null));
    expect(sent.map((b) => b.measurement_freq_mhz)).toEqual([28, 28.85, 29.7]);
    expect(sent.map((b) => b.freq)).toEqual([28, 28.85, 29.7]);
    const drawn = await untilDom(() => {
      const t = traces("Elevation cut at 0° azimuth");
      return t && t.length === 3 ? t : null;
    });
    expect(drawn).toEqual(["freq = 28", "freq = 28.85", "freq = 29.7"]);
  });

  it("copy sends the family it draws, its knob, range and values", async () => {
    const r = await mount();
    fireEvent.change(viewMenu(), { target: { value: optionValue(viewMenu(), "Elevation @ 0° az") } });
    await untilDom(() => (r.cells.length >= 6 ? true : null));
    fireEvent.click(screen.getByRole("button", { name: "Copy this chart as an analysis" }));
    const body = await untilDom(() => r.keeps[0] ?? null);
    expect(body.origin).toBe("chart");
    expect(body.form).toBe("analysis");
    expect(body.spec).toBeNull();
    expect(body.family).toEqual({
      knob: "base",
      lo: 4,
      hi: 14,
      points: 6,
      spacing: "lin",
      values: [4, 6, 8, 10, 12, 14],
    });
  });
});
