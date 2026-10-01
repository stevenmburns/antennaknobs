// The views step 5 unit 5 brings to the analysis chart (AK#1757), through a
// real <DesignSession>:
//   - R/X against frequency: a frequency analysis listing Rx draws R and X
//     against frequency on the knob sweep's R/X chart (frequency on x, the
//     guide at the measurement frequency), one curve per cell;
//   - explicit frequencies: a frequency analysis given values sends exactly
//     those frequencies (ascending), refines none between them, and says
//     "3 values"; an edit of from / to makes it a range, the pick kept and
//     read "(edited)", and ↺ brings the list back;
//   - the Table: an analysis listing Table prints one row per x value and a
//     column group per cell, for a knob family and for a frequency sweep over
//     two designs, and "copy" puts it on the clipboard as TSV; on a phone it
//     scrolls inside the chart's square.
//
// Mutation notes (run by hand, 2026-09-29; each reverted after):
//   - ChartFrequency drawing the Rx view as the Smith chart (the `Rx` branch
//     removed): "a frequency analysis listing Rx…" fails, no canvas.zparam;
//   - listRange not marking the list exact (useFreqSweep refines it):
//     "an explicit frequency list…" fails, a `_refine` sweep is sent;
//   - editRange keeping `freqs` on an edit: "…an edit of from…" fails, the
//     edited sweep still sends the three listed values;
//   - chartTable dropping every curve but the first (curves.slice(0, 1)):
//     "the Table…" fails, data-cells is 1.
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { HARNESS_EXAMPLE, mountReady, stageChart, sweepIdle, untilDom } from "./designSessionHarness";

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

const OTHER: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  name: "dipoles.other",
  label: "Other dipole",
  bands: [band(21.2, 21, 21.45)],
  default_freq: 21.2,
  has_design_freq: false,
  meas_freq_range_mhz: [21, 21.45],
  param_schema: [knob({ default: 0.6 })],
};

const NO_CROSS = { engines: null, grounds: null, axes: [], planes: null, designs: null, step: null };

const frequency = (name: string, over: Record<string, unknown>) => ({
  name,
  summary: name,
  code: "an.band_swr(...)",
  problems: [],
  workbench: {
    runs: true,
    kind: "frequency",
    note: null,
    views: ["Swr"],
    range: null,
    level: "default",
    points: null,
    freqs: null,
    swr: { scale: null, threshold: null },
    ...NO_CROSS,
    ...over,
  },
});

const DECK_GRID = [14, 14.05, 14.1, 14.15, 14.2];
const OTHER_GRID = [21, 21.1125, 21.225, 21.3375, 21.45];
const bands = (views: string[]) => ({
  views,
  axes: ["designs"],
  designs: [
    { name: DECK.name, refused: null, param: null, values: null, range: { lo: 14, hi: 14.2, spacing: "lin" }, freqs: DECK_GRID },
    { name: OTHER.name, refused: null, param: null, values: null, range: { lo: 21, hi: 21.45, spacing: "lin" }, freqs: OTHER_GRID },
  ],
});

const ANALYSES = [
  frequency("rx freq", {
    views: ["Rx"],
    range: { lo: 14, hi: 14.35, spacing: "lin", points: 8, source: "design" },
    level: "analysis",
    points: 8,
  }),
  frequency("rx bands", bands(["Rx"])),
  frequency("listed", {
    range: { lo: 14, hi: 14.3, spacing: "lin", points: 3, source: "design" },
    level: "analysis",
    freqs: [14.2, 14, 14.3],
  }),
  frequency("table bands", bands(["Table", "Swr"])),
  {
    name: "len table",
    summary: "len table",
    code: "an.Analysis(...)",
    problems: [],
    workbench: {
      runs: true,
      kind: "knob",
      log: false,
      param: "len",
      values: [0.9, 1, 1.1],
      views: ["Table"],
      note: null,
      ...NO_CROSS,
      axes: ["step"],
      step: { knob: "gap", values: [0.25, 0.5], labels: ["gap = 0.25", "gap = 0.5"] },
    },
  },
];

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

const UI_DEFAULTS = (refine: boolean) => ({
  path: "/x/settings.toml",
  exists: false,
  writable: true,
  switches: {
    live: true,
    freq_sweep: true,
    convergence_sweep: true,
    pattern_renorm: false,
    refine,
    heatmap_currents: true,
    current_waveforms: false,
    wire_labels: false,
    feed_labels: true,
  },
  switches_set: ["refine"],
  antenna_view: { orientation: "iso" },
  ground: null,
  problems: [],
});

type Body = Record<string, unknown>;
const zRe = (f: number) => 40 + 100 * Math.abs(f - 14.2);
const zIm = (f: number) => -5 + 10 * (f - 14);

async function mount(opts: { refine?: boolean; mobile?: boolean } = {}) {
  const sweeps: (Body & { freqs_mhz: number[] })[] = [];
  const params: Body[] = [];
  const r = await mountReady({
    // A pick starts its analysis, as before [workbench.run_on_pick] (AC6LA #179).
    pickRuns: true,
    examples: [DECK, OTHER],
    ...(opts.mobile ? { mobile: true } : {}),
    pinned: ["antenna", "zparam"],
    uiDefaults: UI_DEFAULTS(opts.refine ?? false),
    routes: {
      "/sweep": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}")) as Body & { freqs_mhz: number[] };
        sweeps.push(body);
        const lines = body.freqs_mhz.map((f) => JSON.stringify({ freq_mhz: f, z_re: zRe(f), z_im: zIm(f) }));
        lines.push(JSON.stringify({ done: true }));
        return ndjson(lines);
      },
      "/param_sweep": (_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}")) as Body & { values: number[] };
        params.push(body);
        const lines = body.values.map((v) =>
          JSON.stringify({ param: body.param, value: v, z_re: 50 + v, z_im: -10 + Number(body.gap ?? 0) * 10 }),
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
  fireEvent.click(r.container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
  await untilDom(() => screen.queryByRole("combobox", { name: "Analysis" }));
}

async function pick(name: string) {
  const box = await untilDom(() => {
    const b = screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null;
    return b && [...b.options].some((o) => o.value === name) ? b : null;
  });
  fireEvent.change(box, { target: { value: name } });
}

const analysisBox = () => screen.getByRole("combobox", { name: "Analysis" }) as HTMLSelectElement;
const optionText = () => analysisBox().selectedOptions[0]?.textContent ?? "";
const same = (a: number[], b: number[]) => a.length === b.length && a.every((v, i) => Math.abs(v - b[i]) < 1e-12);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("R/X against frequency", () => {
  it("a frequency analysis listing Rx draws R and X against frequency, the guide at the measurement frequency", async () => {
    const r = await mount();
    await chartOnStage(r);
    await pick("rx freq");
    const chart = await untilDom(() => {
      const c = stageChart("canvas.zparam");
      return c && c.dataset.param === "frequency" && c.dataset.points === "8" ? c : null;
    });
    expect((screen.getByRole("combobox", { name: "Chart view" }) as HTMLSelectElement).value).toBe("Rx");
    const sent = r.sweeps.find((b) => b.freqs_mhz.length === 8)!.freqs_mhz;
    expect(sent[0]).toBeCloseTo(14, 12);
    expect(sent[7]).toBeCloseTo(14.35, 12);
    // What the plot holds: the swept frequencies on x, R and X from them.
    expect(chart.dataset.r).toBe(sent.map((f) => zRe(f).toFixed(3)).join(","));
    expect(chart.dataset.x).toBe(sent.map((f) => zIm(f).toFixed(3)).join(","));
    expect(chart.dataset.values!.split(",").map(Number)).toEqual(sent.map((f) => Number(f.toPrecision(4))));
    expect(chart.dataset.guide).toBe("14.18");
    expect(chart.dataset.refR).not.toBe("");
    // No knob sweep ran for it.
    expect(r.params).toHaveLength(0);
  });

  it("one curve per cell: two designs on their own bands", async () => {
    const r = await mount();
    await chartOnStage(r);
    await pick("rx bands");
    const chart = await untilDom(() => {
      const c = stageChart("canvas.zparam");
      return c && c.dataset.points === "5" && /:5$/.test(c.dataset.curves ?? "") ? c : null;
    });
    expect(chart.dataset.param).toBe("frequency");
    expect(r.sweeps.some((b) => b.geometry === OTHER.name && same(b.freqs_mhz, OTHER_GRID))).toBe(true);
  });
});

describe("an explicit frequency list", () => {
  it("sends exactly its values, ascending, refines none between them, and says how many", async () => {
    const r = await mount({ refine: true });
    await chartOnStage(r);
    await pick("listed");
    const chart = await untilDom(() => stageChart("canvas.sweep-vswr"));
    await untilDom(() => r.sweeps.find((b) => same(b.freqs_mhz, [14, 14.2, 14.3])));
    await sweepIdle(chart);
    await untilDom(() => (chart.dataset.settled === "1" ? true : null));
    expect(r.sweeps.filter((b) => b._refine)).toHaveLength(0);
    const badge = document.querySelector<HTMLElement>(".chart-freq-list")!;
    expect(badge.textContent).toBe("3 values");
    expect(badge.dataset.values).toBe("14,14.2,14.3");
  });

  it("an edit of from makes it a range, the pick kept (edited), and ↺ brings the list back", async () => {
    const r = await mount();
    await chartOnStage(r);
    await pick("listed");
    await untilDom(() => r.sweeps.find((b) => same(b.freqs_mhz, [14, 14.2, 14.3])));
    const from = screen.getByLabelText("from MHz") as HTMLInputElement;
    fireEvent.change(from, { target: { value: "14.1" } });
    fireEvent.blur(from);
    // A range over the new ends with as many points: 14.1, 14.2, 14.3.
    await untilDom(() => r.sweeps.find((b) => same(b.freqs_mhz, [14.1, 14.2, 14.3])));
    expect(document.querySelector(".chart-freq-list")).toBeNull();
    expect(analysisBox().value).toBe("listed");
    expect(optionText()).toBe("listed (edited)");
    const before = r.sweeps.filter((b) => same(b.freqs_mhz, [14, 14.2, 14.3])).length;
    fireEvent.click(screen.getByTitle("Back to the analysis's own range"));
    await untilDom(() => r.sweeps.filter((b) => same(b.freqs_mhz, [14, 14.2, 14.3])).length > before || null);
    expect(document.querySelector(".chart-freq-list")?.textContent).toBe("3 values");
    expect(optionText()).toBe("listed");
  });
});

describe("the Table", () => {
  it("a knob family: a row per value, a column group per cell, copied as TSV", async () => {
    const writeText = vi.fn<(t: string) => Promise<void>>(async () => {});
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const r = await mount();
    await chartOnStage(r);
    await pick("len table");
    const table = await untilDom(() => {
      const t = stageChart(".chart-table");
      return t && t.dataset.rows === "3" && t.dataset.cells === "2" ? t : null;
    });
    expect((screen.getByRole("combobox", { name: "Chart view" }) as HTMLSelectElement).value).toBe("Table");
    const heads = [...table.querySelectorAll("thead tr:last-child th")].map((th) => th.textContent);
    expect(heads).toEqual(["len", "R (Ω)", "X (Ω)", "R (Ω)", "X (Ω)"]);
    const groups = [...table.querySelectorAll("thead .chart-table-group")].map((th) => th.textContent);
    expect(groups).toEqual(["gap = 0.25", "gap = 0.5"]);
    const rows = [...table.querySelectorAll("tbody tr")].map((tr) =>
      [...tr.children].map((c) => c.textContent),
    );
    expect(rows[1]).toEqual(["1", "51.000", "-7.500", "51.000", "-5.000"]);
    fireEvent.click(screen.getByRole("button", { name: "copy" }));
    await untilDom(() => (writeText.mock.calls.length > 0 ? true : null));
    const tsv = writeText.mock.calls[0][0].trimEnd().split("\n");
    expect(tsv[0]).toBe("len\tgap = 0.25 R (Ω)\tgap = 0.25 X (Ω)\tgap = 0.5 R (Ω)\tgap = 0.5 X (Ω)");
    expect(tsv[2]).toBe("1\t51.000\t-7.500\t51.000\t-5.000");
    expect(tsv).toHaveLength(4);
  });

  it("a frequency sweep over two designs: MHz, R, X and SWR per design, the union of their frequencies", async () => {
    const r = await mount();
    await chartOnStage(r);
    await pick("table bands");
    const table = await untilDom(() => {
      const t = stageChart(".chart-table");
      return t && t.dataset.rows === "10" && t.dataset.cells === "2" ? t : null;
    });
    const first = [...table.querySelectorAll("tbody tr")][0];
    const cells = [...first.children].map((c) => c.textContent);
    // The session design's point at 14 MHz; the other design has none there.
    expect(cells.slice(0, 3)).toEqual(["14", "60.000", "-5.000"]);
    expect(cells.slice(4)).toEqual(["", "", ""]);
    // SWR is against the session's Z0 (50 Ω): (1 + |Γ|)/(1 − |Γ|).
    const z = { re: 60, im: -5 };
    const gr = ((z.re - 50) * (z.re + 50) + z.im * z.im) / ((z.re + 50) ** 2 + z.im ** 2);
    const gi = (z.im * (z.re + 50) - (z.re - 50) * z.im) / ((z.re + 50) ** 2 + z.im ** 2);
    const rho = Math.hypot(gr, gi);
    expect(first.children[3].textContent).toBe(((1 + rho) / (1 - rho)).toFixed(3));
    const heads = [...table.querySelectorAll("thead tr:last-child th")].map((th) => th.textContent);
    expect(heads).toEqual(["MHz", "R (Ω)", "X (Ω)", "SWR", "R (Ω)", "X (Ω)", "SWR"]);
  });

  it("on a phone the table scrolls inside the chart's square", async () => {
    const r = await mount({ mobile: true });
    const thumb = await untilDom(() => r.container.querySelector<HTMLElement>("canvas.smith"));
    fireEvent.click(thumb);
    await pick("len table");
    const table = await untilDom(() => {
      const t = document.querySelector<HTMLElement>(".chart-table");
      return t && t.dataset.rows === "3" ? t : null;
    });
    const size = Number.parseFloat(table.style.width);
    expect(size).toBeGreaterThan(0);
    expect(table.style.height).toBe(table.style.width);
    // The <table> sits in the scroller, not in the page flow.
    expect(table.querySelector(".chart-table-scroll > table")).not.toBeNull();
  });
});
