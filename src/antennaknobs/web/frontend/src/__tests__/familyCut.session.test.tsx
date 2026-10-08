// A pattern family's cut angle (AK#1950), through a real <DesignSession>.
// Dan AC6LA (QRZ 1005128 #61): "Sweep a knob → Elevation / Azimuth" offered
// only "Elevation @ 0° az" and "Azimuth @ 10° el", so a family could not be
// cut through the elevation of a design's peak. The link half is in
// deepLink.session.test.tsx, the React-free rules in familyCut.test.ts, the
// keep's Python half in tests/test_family_cut_angle_1950.py.
//
// What is pinned: on an Elevation / Azimuth view an angle box sits beside
// the view menu; a committed angle relabels the menu and the chart, re-cuts
// the solves in hand at it (POST /cuts carries it; the angles are exempt from
// a cell's signature, so it never re-solves), and rides every later cell
// request; an elevation of 0 is refused in place; "copy" sends the views the
// family drew, angle and all; "at peak" cuts through the live design's 3-D
// maximum (/pattern_metrics), its bearing for an elevation cut and its
// take-off angle for an azimuth cut.
//
// Mutation notes (run by hand, 2026-10-07; each reverted after):
//   - PatternChartControls never rendering CutAngle (`cut` ignored): all four
//     tests here fail at the missing box or button;
//   - the session's onCut a no-op: the first three fail (the menu still
//     reads "Elevation @ 0° az"; the copy sends az 0);
//   - the keep body without `views`: "copy sends the views" fails;
//   - onPeak taking takeoff_deg for an elevation cut (the angles swapped):
//     "at peak" fails (the menu reads "Elevation @ 23° az", not 47°).
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { invveeShape } from "./fixtures/solveShapes";
import { HARNESS_EXAMPLE, mountReady, untilDom } from "./designSessionHarness";

vi.setConfig({ testTimeout: 30_000 });

const DESIGN: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  bands: [{ key: "28.47 MHz", label: "28.47 MHz", freq_mhz: 28.47, min_mhz: 28, max_mhz: 29.7 }],
  default_freq: 28.47,
  has_design_freq: false,
  meas_freq_range_mhz: [28, 29.7],
  param_schema: [
    {
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
    } satisfies SchemaParamSpec,
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
  // A solve is answered; a cuts ask is not, so it falls back to POST /cuts
  // (charts/cuts.ts), which the test reads.
  send(payload: string) {
    const req = JSON.parse(payload) as Record<string, unknown>;
    if (!("geometry" in req) || typeof req._seq !== "number") return;
    const reply = { ...invveeShape, feeds: undefined, geometry: req.geometry, _seq: req._seq, z0_ohms: 50 };
    setTimeout(() => this.onmessage?.({ data: JSON.stringify(reply) } as MessageEvent), 0);
  }
  close() {}
}

type Body = Record<string, unknown>;

const lobe = (n: number, size: number) =>
  Array.from({ length: n }, (_, i) => size - 10 * Math.abs(Math.sin((Math.PI * i) / n)));
const cuts = (body: Body, size: number) => ({
  az_elev_deg: body.az_elev_deg,
  elev_az_deg: body.elev_az_deg,
  n_dir: 72,
  floor_dbi: -40,
  azimuth: lobe(72, size),
  elevation: lobe(72, size),
  diffraction: false,
});

function cell(body: Body) {
  const size = Number(body.base);
  return {
    available: true,
    solve: { ...invveeShape, feeds: undefined, geometry: body.geometry, solve_id: `cell-${size}`, cuts: cuts(body, size) },
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

// The live design's 3-D maximum: bearing 47°, take-off 23°.
const PEAK = {
  peak_gain_dbi: 8,
  takeoff_deg: 23.4,
  azimuth_deg: 46.6,
  front_to_back_db: 0,
  az_beamwidth_deg: 360,
  el_beamwidth_deg: 30,
  rdf_db: 6,
};

async function mount() {
  const cells: Body[] = [];
  const recuts: Body[] = [];
  const keeps: Body[] = [];
  const peaks: Body[] = [];
  const json = (b: unknown) => ({ ok: true, status: 200, json: async () => b }) as unknown as Response;
  const r = await mountReady({
    examples: [DESIGN],
    pinned: ["antenna", "zparam"],
    routes: {
      "/pattern_cell": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}")) as Body;
        cells.push(body);
        return json(cell(body));
      },
      "/cuts": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}")) as Body;
        recuts.push(body);
        return json(cuts(body, 5));
      },
      "/pattern_metrics": (_url: string, init?: RequestInit) => {
        peaks.push(JSON.parse(String(init?.body ?? "{}")) as Body);
        return json({ available: true, metrics: PEAK });
      },
      "/analyses": () => json({ analyses: [] }),
      "/keep": (_url: string, init?: RequestInit) => {
        keeps.push(JSON.parse(String(init?.body ?? "{}")) as Body);
        return json({ code: "an.patterns(...)", name: "patterns over base", problems: [], study_refusal: null });
      },
      "/param_sweep": () => ({ ok: false, status: 500, json: async () => ({}) }) as unknown as Response,
    },
  });
  // The chart on the stage, "Sweep a knob", then the family's `view`.
  // eslint-disable-next-line testing-library/no-node-access -- the thumbnail is a bare canvas
  fireEvent.click(r.container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
  const picker = await untilDom(() => {
    const b = screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null;
    return b && [...b.options].some((o) => o.textContent === "Sweep a knob") ? b : null;
  });
  const entry = [...picker.options].find((o) => o.textContent === "Sweep a knob")!.value;
  fireEvent.change(picker, { target: { value: entry } });
  await untilDom(() => screen.getByRole("group", { name: "Analysis chart" }).dataset.chartKind === "knob" || null);
  return { ...r, cells, recuts, keeps, peaks };
}

const viewMenu = () => screen.getByRole("combobox", { name: "Chart view" }) as HTMLSelectElement;
const shown = () => viewMenu().selectedOptions[0].textContent;
const toView = async (v: string) => {
  fireEvent.change(viewMenu(), { target: { value: v } });
  await untilDom(() => screen.getByRole("group", { name: "Analysis chart" }).dataset.chartKind === "pattern" || null);
};
const traces = (name: string) => {
  const c = screen.queryByRole("img", { name });
  return c ? (JSON.parse(c.dataset.traces ?? "[]") as string[]) : null;
};
function commit(label: string, value: string) {
  const box = screen.getByRole("textbox", { name: label });
  fireEvent.change(box, { target: { value } });
  fireEvent.blur(box);
}
const boxValue = (label: string) => (screen.getByRole("textbox", { name: label }) as HTMLInputElement).value;

beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a family's cut angle (AK#1950)", () => {
  it("an elevation cut's bearing relabels the menu, re-cuts at it, and rides the next cells", async () => {
    const r = await mount();
    await toView("pattern:0");
    expect(boxValue("cut azimuth")).toBe("0");
    await untilDom(() => (r.cells.length >= 6 ? true : null));
    for (const b of r.cells) expect(b.elev_az_deg).toBe(0);
    await untilDom(() => (traces("Elevation cut at 0° azimuth")?.length === 6 ? true : null));
    commit("cut azimuth", "35");
    // The menu and the chart follow; no table or other view moves.
    await untilDom(() => (shown() === "Elevation @ 35° az" ? true : null));
    expect([...viewMenu().options].map((o) => o.textContent)).toContain("Azimuth @ 10° el");
    await untilDom(() => (traces("Elevation cut at 35° azimuth") ? true : null));
    // The solves in hand are re-cut at 35°, not re-solved. (A request is no
    // DOM change, so this waits by polling; the cuts ask falls back from
    // the socket to POST /cuts after charts/cuts.ts's 1.5 s.)
    await vi.waitFor(() => expect(r.recuts.some((b) => b.elev_az_deg === 35)).toBe(true), { timeout: 5000 });
    expect(r.cells.length).toBe(6);
    // The next run's cells ask at 35°.
    fireEvent.click(screen.getByRole("button", { name: "run" }));
    await vi.waitFor(() => expect(r.cells.length).toBeGreaterThanOrEqual(12), { timeout: 5000 });
    for (const b of r.cells.slice(6)) expect(b.elev_az_deg).toBe(35);
  });

  it("an azimuth cut's elevation is 1–89: 0 is refused in place, 22 relabels it", async () => {
    const r = await mount();
    await toView("pattern:1");
    expect(boxValue("cut elevation")).toBe("10");
    commit("cut elevation", "0");
    expect(boxValue("cut elevation")).toBe("10");
    expect(screen.getByRole("status").textContent).toBe("1–89");
    expect(shown()).toBe("Azimuth @ 10° el");
    commit("cut elevation", "22");
    await untilDom(() => (shown() === "Azimuth @ 22° el" ? true : null));
    await vi.waitFor(() => expect(r.recuts.some((b) => b.az_elev_deg === 22)).toBe(true), { timeout: 5000 });
    // The table has no cut: no box.
    await toView("pattern:2");
    expect(screen.queryByRole("textbox", { name: "cut elevation" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "cut azimuth" })).toBeNull();
  });

  it("copy sends the views the family drew, its cut angle and all", async () => {
    const r = await mount();
    await toView("pattern:0");
    await untilDom(() => (r.cells.length >= 6 ? true : null));
    commit("cut azimuth", "35");
    await untilDom(() => (shown() === "Elevation @ 35° az" ? true : null));
    fireEvent.click(screen.getByRole("button", { name: "Copy this chart as an analysis" }));
    const body = await untilDom(() => r.keeps[0] ?? null);
    expect((body.family as Body).views).toEqual([
      { view: "Elevation", az: 35 },
      { view: "Azimuth", el: 10 },
      { view: "PatternTable" },
    ]);
  });

  it("at peak cuts through the live design's maximum: its bearing, or its take-off angle", async () => {
    const r = await mount();
    await toView("pattern:0");
    const peak = await untilDom(() => {
      const b = screen.queryByRole("button", { name: "at peak" }) as HTMLButtonElement | null;
      return b && !b.disabled ? b : null;
    });
    fireEvent.click(peak);
    await untilDom(() => (shown() === "Elevation @ 47° az" ? true : null));
    expect(r.peaks.length).toBe(1);
    // The azimuth cut takes the take-off angle, rounded.
    fireEvent.change(viewMenu(), { target: { value: "pattern:1" } });
    await untilDom(() => (shown() === "Azimuth @ 10° el" ? true : null));
    fireEvent.click(screen.getByRole("button", { name: "at peak" }));
    await untilDom(() => (shown() === "Azimuth @ 23° el" ? true : null));
  });
});
