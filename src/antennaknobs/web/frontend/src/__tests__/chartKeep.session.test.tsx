// "Keep as study" and "copy as analysis" through a real <DesignSession>
// (AK#1757, sweep-framework step 7 unit 4). The server half, where the text
// is written and the kept study re-runs bit-equal on the CLI, is
// tests/test_keep_1757.py; this is the page's.
//
// The oracle is the request each curve was solved with. A pin keeps THAT
// request (what the server reads its cell from), so the pin's `req` must be
// the /sweep body its curve was drawn from, byte for byte but the lane's
// own metadata; and the kept study, served back as the server serves a
// `cells=` study, must re-solve each cell with that same request: the same
// solve, so the same numbers.
//
// Mutation notes (run by hand, 2026-09-30; each reverted after):
//   - the pin's req taken from the session's request (buildRequest) instead
//     of its cell's (buildCellRequest): "keeps each pin's own request…"
//     fails, the B-slot pin carries slot A's model;
//   - listedPlan putting every cell on the active slot (ignoring its
//     engine): "…and the saved study re-solves exactly those requests"
//     fails, both cells are sent on bspline degree 2;
//   - buildRequestFor dropping the state's variant: the variant test fails,
//     the cell is sent at the default variant.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { fireEvent, screen, within } from "@testing-library/react";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { invveeShape } from "./fixtures/solveShapes";
import { HARNESS_EXAMPLE, mountReady, stageChart, untilDom } from "./designSessionHarness";

vi.setConfig({ testTimeout: 30_000 });

const GAP: SchemaParamSpec = {
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
};

const DECK: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  bands: [{ key: "14.175 MHz", label: "14.175 MHz", freq_mhz: 14.175, min_mhz: 14, max_mhz: 14.35 }],
  default_freq: 14.175,
  has_design_freq: false,
  meas_freq_range_mhz: [14, 14.35],
  sweep_range: { lo: 14, hi: 14.35, spacing: "lin", step: 0.025, source: "file" },
  param_schema: [GAP],
  variants: ["default", "wide"],
  variant_values: { wide: { gap: 0.5 } },
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
    const reply = { ...invveeShape, feeds: undefined, geometry: req.geometry, _seq: req._seq,
                    z_in_re: 50, z_in_im: -10, z0_ohms: 50 }; // prettier-ignore
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
const json = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

type Body = Record<string, unknown>;
const GAP_VALUES = [0.1, 0.2, 0.3];
const SPEC = { an: "Analysis", name: "gap sweep" };
const BAND = {
  name: "band SWR",
  summary: "frequency; 1 curve; views Swr",
  code: "an.band_swr()",
  spec: { an: "Analysis", name: "band SWR" },
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
  },
};
const GAP_SWEEP = {
  name: "gap sweep",
  summary: "gap 0.1..0.3, 3 points; 1 curve; views Rx",
  code: 'an.Analysis("gap sweep", an.Sweep("gap", 0.1, 0.3, points=3))',
  spec: SPEC,
  problems: [],
  workbench: { runs: true, kind: "knob", param: "gap", values: GAP_VALUES, log: false, note: null },
};
const E7 = {
  ...GAP_SWEEP,
  name: "x:peers",
  study: { source: "x", name: "peers" },
  workbench: { ...GAP_SWEEP.workbench, axes: ["designs"], designs: [] },
};

// What the server serves for a kept `cells=` study of `pins` (keep.py and
// analyses_offer._cell_entry): one listed cell per pin, its state naming
// the design (and variant), its engine spec; the pinned frequencies.
function keptStudy(name: string, cells: Body[], freqs: number[], ground: string) {
  return {
    name,
    summary: "kept",
    code: "an.Analysis(...)",
    spec: { an: "Analysis", name },
    problems: [],
    study: { source: name.split(":")[0], name: name.split(":")[1] },
    workbench: {
      runs: true,
      kind: "frequency",
      note: null,
      views: ["Swr", "Rx"],
      range: { lo: freqs[0], hi: freqs[freqs.length - 1], spacing: "lin", source: "design" },
      level: "analysis",
      points: null,
      freqs,
      swr: { scale: null, threshold: null },
      engines: null,
      grounds: [ground],
      axes: ["cells"],
      planes: null,
      designs: null,
      states: null,
      cells,
      step: null,
    },
  };
}

const UI_DEFAULTS = {
  path: "/x/settings.toml",
  exists: false,
  writable: true,
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

async function mount(opts: { canSave?: boolean } = {}) {
  const sweeps: Body[] = [];
  const params: Body[] = [];
  const keeps: Body[] = [];
  const saves: Body[] = [];
  const analyses: { extra: unknown[]; asked: number } = { extra: [], asked: 0 };
  const r = await mountReady({
    examples: [DECK],
    pinned: ["antenna", "zparam"],
    uiDefaults: UI_DEFAULTS,
    canSaveStudies: opts.canSave ?? true,
    // The server's own soil ranges, whose default (13 / 0.005) is the CLI's:
    // a finite ground slot on it holds the bare "finite-fast".
    soilRanges: {
      eps_r: { min: 1, max: 81, default: 13 },
      sigma: { min: 0.0001, max: 5, default: 0.005, log: true },
    },
    routes: {
      "/sweep": (_url: string, init?: RequestInit) => {
        const b = JSON.parse(String(init?.body ?? "{}")) as Body & { freqs_mhz: number[] };
        sweeps.push(b);
        const n = typeof b.n_per_wire === "number" ? b.n_per_wire : 0;
        const lines = b.freqs_mhz.map((f) => JSON.stringify({ freq_mhz: f, z_re: 40 + n + 100 * Math.abs(f - 14.2), z_im: -n }));
        lines.push(JSON.stringify({ done: true }));
        return ndjson(lines);
      },
      "/param_sweep": (_url: string, init?: RequestInit) => {
        const b = JSON.parse(String(init?.body ?? "{}")) as Body & { param: string; values: number[] };
        params.push(b);
        const lines = b.values.map((v) => JSON.stringify({ param: b.param, value: v, z_re: 60 + 100 * v, z_im: -30 }));
        lines.push(JSON.stringify({ done: true }));
        return ndjson(lines);
      },
      "/keep": (_url: string, init?: RequestInit) => {
        const b = JSON.parse(String(init?.body ?? "{}")) as Body;
        keeps.push(b);
        return json({ code: `# kept ${String(b.origin)} ${String(b.form)}\n`, name: b.name, problems: [], study_refusal: null });
      },
      "/studies/save": (_url: string, init?: RequestInit) => {
        const b = JSON.parse(String(init?.body ?? "{}")) as Body;
        saves.push(b);
        if (saves.length === 1 && b.path === "taken") return json({ detail: "taken.py is there already" }, 409);
        return json({ path: `/home/u/.antennaknobs/studies/${String(b.path)}.py`, source: b.path, name: `${String(b.path)}:${String(b.name)}` });
      },
      "/analyses": () => {
        analyses.asked++;
        return json({ geometry: DECK.name, analyses: [GAP_SWEEP, BAND, E7, ...analyses.extra] });
      },
    },
  }); // prettier-ignore
  return { ...r, sweeps, params, keeps, saves, analyses };
}

async function chartOnStage() {
  fireEvent.click(screen.getByTitle("Switch to Sweep"));
  await untilDom(() => screen.queryByRole("button", { name: "Engines and grounds" }));
}

async function pick(name: string) {
  const box = await untilDom(() => {
    const b = screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null;
    return b && [...b.options].some((o) => o.value === name) ? b : null;
  });
  fireEvent.change(box, { target: { value: name } });
}

// The --ground spec the server reads off a request (keep.ground_of).
function groundSpec(req: Body): string {
  if (!req.ground) return "free";
  const kind = { fast: "finite-fast", sommerfeld: "finite", mininec: "mininec", pec: "pec" }[
    String(req.ground_model ?? "fast")
  ]!;
  const soil = req.soil as { eps_r: number; sigma: number } | undefined;
  return kind === "pec" || !soil ? kind : `${kind}:${soil.eps_r},${soil.sigma}`;
}

const pinButton = () => screen.getByRole("button", { name: "Pin this chart's curves" }) as HTMLButtonElement;

// What a solve is, without the lane's metadata or what a keep strips: the
// body a pin's `req` must equal (lib/keep.ts keepRequest).
const NOT_THE_SOLVE = new Set(["_session", "_gen", "_stream", "_approved", "_track", "z0_ohms"]);
function solve(b: Body, drop: string[] = []): Body {
  return Object.fromEntries(Object.entries(b).filter(([k]) => !NOT_THE_SOLVE.has(k) && !drop.includes(k)));
}

let clipboard: string[] = [];
beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
  clipboard = [];
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: async (t: string) => void clipboard.push(t) },
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("keep pins as a study", () => {
  it("keeps each pin's own request, saves it, and the saved study re-solves exactly those requests", async () => {
    const r = await mount();
    await chartOnStage();
    fireEvent.change(screen.getByRole("combobox", { name: "Chart view" }), { target: { value: "Swr" } });
    // Two curves, slots A and B: two pins, each solved on its own slot.
    fireEvent.click(screen.getAllByRole("button", { name: "Engines and grounds" })[0]);
    const dlg = screen.getByRole("dialog", { name: "Engines and grounds" });
    fireEvent.click(within(dlg).getByRole("checkbox", { name: /^B: / }));
    fireEvent.keyDown(document.body, { key: "Escape" });
    await untilDom(() => {
      const c = stageChart("canvas.sweep-vswr");
      return c && c.dataset.phase === "idle" && c.dataset.curves === "B|1:15" ? c : null;
    });
    await untilDom(() => !pinButton().disabled || null);
    fireEvent.click(pinButton());

    fireEvent.click(await untilDom(() => screen.queryByRole("button", { name: "Keep the pins drawn here as a study" })));
    const dialog = await untilDom(() => screen.queryByRole("dialog", { name: "Keep pins as study" }));
    const kept = await untilDom(() => r.keeps[0] ?? null);
    expect(kept.origin).toBe("sweep pins");
    const pins = kept.pins as { req: Body; x: Body; xs: number[] }[];
    expect(pins.length).toBe(2);
    // Each pin's request IS its curve's /sweep body (but the frequencies,
    // which the pin carries as xs, and the lane's metadata).
    const drawnOn = (model: Body) =>
      r.sweeps.filter((b) => JSON.stringify(b.model_options) === JSON.stringify(model)).at(-1)!;
    for (const p of pins) {
      const sent = drawnOn(p.req.model_options as Body);
      expect(p.req).toEqual(solve(sent, ["freqs_mhz", "reuse_cached_z"]));
      expect(p.x).toEqual({ kind: "frequency", name: "frequency" });
      expect(p.xs).toEqual(sent.freqs_mhz);
    }
    expect(pins[0].req.model_options).not.toEqual(pins[1].req.model_options);

    // The text the server wrote, then copy and save.
    await untilDom(() => (within(dialog).getByLabelText("Keep pins as study as Python").textContent === "# kept sweep pins study\n" ? true : null));
    fireEvent.click(within(dialog).getByRole("button", { name: "copy" }));
    await untilDom(() => (clipboard.length === 1 ? true : null));
    expect(clipboard[0]).toBe("# kept sweep pins study\n");
    const path = within(dialog).getByRole("textbox", { name: "The study file's path under the studies folder" });
    expect((path as HTMLInputElement).value).toBe("pinned-sweeps");
    fireEvent.change(path, { target: { value: "feeds/mine" } });
    const asked = r.analyses.asked;
    // The server's cells study for those pins, as /analyses would serve it.
    const freqs = pins[0].xs;
    const cellFor = (_p: { req: Body }, engine: string) => ({
      label: `${DECK.name}, as built, ${engine}`,
      state: { name: "as built", design: DECK.name, variant: null, knobs: {}, label: `${DECK.name}, as built` },
      engine,
      ground: null,
      plane: null,
      refused: null,
      param: null,
      values: null,
      range: null,
      freqs,
    });
    r.analyses.extra = [
      keptStudy("feeds/mine:pinned sweeps", [cellFor(pins[0], "momwire:bspline"), cellFor(pins[1], "momwire:bspline-d1")],
                freqs, groundSpec(pins[0].req)),
    ];
    fireEvent.click(within(dialog).getByRole("button", { name: "save as study" }));
    const saved = await untilDom(() => r.saves[0] ?? null);
    expect(saved).toMatchObject({ origin: "sweep pins", form: "study", path: "feeds/mine", overwrite: false, name: "pinned sweeps" });
    expect(saved.pins).toEqual(kept.pins);
    await untilDom(() => within(dialog).queryByRole("status"));
    expect(within(dialog).getByRole("status").textContent).toContain("feeds/mine:pinned sweeps");
    // The tab re-reads its analyses: the study is in the picker's Studies group.
    await untilDom(() => (r.analyses.asked > asked ? true : null));
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));

    // Re-run: picking the kept study re-solves each cell with the pin's own
    // request, on the slot holding its engine, at the pinned frequencies.
    const before = r.sweeps.length;
    await pick("feeds/mine:pinned sweeps");
    const rerun = await untilDom(() => (r.sweeps.length >= before + 2 ? r.sweeps.slice(before) : null));
    for (const p of pins) {
      const again = rerun.find((b) => JSON.stringify(b.model_options) === JSON.stringify(p.req.model_options));
      expect(again).toBeDefined();
      expect(solve(again!, ["freqs_mhz", "reuse_cached_z"])).toEqual(p.req);
      expect(again!.freqs_mhz).toEqual(freqs);
    }
  }); // prettier-ignore

  it("a cell on a variant is solved at that variant's defaults", async () => {
    const r = await mount();
    await chartOnStage();
    const cell = {
      label: `${DECK.name}:wide, as built`,
      state: { name: "as built", design: DECK.name, variant: "wide", knobs: {}, label: `${DECK.name}:wide, as built` },
      engine: null, ground: null, plane: null, refused: null, param: null, values: null, range: null,
      freqs: [14.1, 14.2],
    }; // prettier-ignore
    // Served on the re-read a save triggers (the dialog's own save).
    r.analyses.extra = [keptStudy("v:wide", [cell], [14.1, 14.2], "free")];
    await pick("gap sweep");
    fireEvent.click(screen.getByRole("button", { name: "Keep this chart as a study" }));
    const dialog = await untilDom(() => screen.queryByRole("dialog", { name: "Keep as study" }));
    await untilDom(() => r.keeps[0] ?? null);
    fireEvent.click(within(dialog).getByRole("button", { name: "save as study" }));
    await untilDom(() => within(dialog).queryByRole("status"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    const before = r.sweeps.length;
    await pick("v:wide");
    const sent = await untilDom(() => r.sweeps.slice(before).find((b) => b.variant === "wide") ?? null);
    expect(sent.gap).toBe(0.5);
    expect(sent.freqs_mhz).toEqual([14.1, 14.2]);
  }); // prettier-ignore
});

describe("keep and copy a chart", () => {
  it("sends the served spec, the tab's request and the requests its curves were solved with", async () => {
    const r = await mount();
    await chartOnStage();
    await pick("gap sweep");
    const drawn = await untilDom(() => r.params.find((b) => b.param === "gap") ?? null);
    const keepBtn = await untilDom(() => {
      const b = screen.queryByRole("button", { name: "Keep this chart as a study" }) as HTMLButtonElement | null;
      return b && !b.disabled ? b : null;
    });
    fireEvent.click(keepBtn);
    const study = await untilDom(() => r.keeps[0] ?? null);
    expect(study).toMatchObject({ origin: "chart", form: "study", spec: SPEC, name: "gap sweep" });
    expect((study.tab as Body).geometry).toBe(DECK.name);
    expect(study.cells).toEqual([solve(drawn, ["param", "values", "label"])]);
    expect(study.values).toBeUndefined();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    // Copy as analysis: no slot ticked, so no cells (the analysis stays
    // on the session's engine), and the copy button puts the text on the
    // clipboard.
    fireEvent.click(screen.getByRole("button", { name: "Copy this chart as an analysis" }));
    const copy = await untilDom(() => r.keeps[1] ?? null);
    expect(copy).toMatchObject({ origin: "chart", form: "analysis", spec: SPEC });
    expect(copy.cells).toBeUndefined();
    const dialog = screen.getByRole("dialog", { name: "Copy as analysis" });
    expect(within(dialog).queryByRole("group", { name: "Save to the studies folder" })).toBeNull();
    await untilDom(() => (within(dialog).getByRole("button", { name: "copy" }) as HTMLButtonElement).disabled ? null : true);
    fireEvent.click(within(dialog).getByRole("button", { name: "copy" }));
    await untilDom(() => (clipboard[0] === "# kept chart analysis\n" ? true : null));
  }); // prettier-ignore

  it("copy is refused for a chart of named designs, and keep for a chart with no analysis", async () => {
    await mount();
    await chartOnStage();
    const copyBtn = () => screen.getByRole("button", { name: "Copy this chart as an analysis" }) as HTMLButtonElement;
    const keepBtn = () => screen.getByRole("button", { name: "Keep this chart as a study" }) as HTMLButtonElement;
    // The chart's own sweep is no analysis.
    await untilDom(() => (keepBtn().disabled ? true : null));
    expect(keepBtn().title).toMatch(/Pick an analysis first/);
    await pick("x:peers");
    await untilDom(() => (!keepBtn().disabled && copyBtn().disabled ? true : null));
    expect(copyBtn().title).toBe("This chart compares named designs: keep it as a study");
  });

  it("hosted, the study is copied only: save is off and says why", async () => {
    await mount({ canSave: false });
    await chartOnStage();
    await pick("gap sweep");
    fireEvent.click(await untilDom(() => {
      const b = screen.queryByRole("button", { name: "Keep this chart as a study" }) as HTMLButtonElement | null;
      return b && !b.disabled ? b : null;
    })); // prettier-ignore
    const dialog = await untilDom(() => screen.queryByRole("dialog", { name: "Keep as study" }));
    const save = within(dialog).getByRole("button", { name: "save as study" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    expect(within(dialog).getByText(/a local workbench only/)).toBeTruthy();
  });

  it("a file already there is offered to be replaced", async () => {
    const r = await mount();
    await chartOnStage();
    await pick("gap sweep");
    fireEvent.click(await untilDom(() => {
      const b = screen.queryByRole("button", { name: "Keep this chart as a study" }) as HTMLButtonElement | null;
      return b && !b.disabled ? b : null;
    })); // prettier-ignore
    const dialog = await untilDom(() => screen.queryByRole("dialog", { name: "Keep as study" }));
    await untilDom(() => r.keeps[0] ?? null);
    fireEvent.change(within(dialog).getByRole("textbox", { name: "The study file's path under the studies folder" }), {
      target: { value: "taken" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "save as study" }));
    const replace = await untilDom(() => within(dialog).queryByRole("button", { name: "replace it" }));
    expect(within(dialog).getByRole("alert").textContent).toContain("there already");
    fireEvent.click(replace);
    await untilDom(() => (r.saves.length === 2 ? true : null));
    expect(r.saves[1].overwrite).toBe(true);
  });
});
