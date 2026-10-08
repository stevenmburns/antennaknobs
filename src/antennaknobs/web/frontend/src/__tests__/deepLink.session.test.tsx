// Workbench deep links (AK#1838) through the real app shell: the page's
// address opens the first tab on its design and variant, selects its
// analysis (an own one or a study) and view in the chart, runs it only with
// run=1, reports an unknown name by name, and follows the tab's design and
// analysis with replaceState. Mounted as <App> (the harness's `url`), so the
// link is read where production reads it.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { COPY_LINK_TITLE } from "../components/results/AnalysisChartControls";
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

// The catalog's first design, which the session would open on without a
// link (no dipoles.invvee here), so landing on DECK proves the link chose it.
const OTHER: ExampleDescriptor = { ...HARNESS_EXAMPLE, name: "beams.other", label: "Other" };
const DECK: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  name: "dipoles.deck",
  label: "Deck",
  variants: ["default", "tall"],
  variant_values: { default: { base: 7 }, tall: { base: 12 } },
  param_schema: [
    knob({}),
    knob({ name: "gap", label: "Gap", default: 0.25, min: 0, max: 1, step: 0.05, precision: 2, unit: null }),
  ],
};

const HEIGHT_VALUES = [2, 5, 8, 11];
const HOLD_SPEC = { an: "Hold", objective: "resonance", adjust: ["gap"], z0: null, warm_start: true };
const knobWorkbench = (hold: boolean) => ({
  runs: true,
  kind: "knob",
  param: "base",
  values: HEIGHT_VALUES,
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
          spec: HOLD_SPEC,
        },
      }
    : {}),
  note: null,
});
const STUDY = "dipoles.apex_feed_on_deck:feed spelling (E7)";
const ANALYSES = {
  analyses: [
    {
      name: "match vs height",
      summary: "height 2..11; hold resonance on gap",
      code: "",
      problems: [],
      workbench: knobWorkbench(true),
    },
    {
      name: STUDY,
      summary: "height 2..11 on two feeds",
      code: "",
      problems: [],
      study: { source: "dipoles.apex_feed_on_deck", name: "feed spelling (E7)" },
      workbench: knobWorkbench(false),
    },
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

async function open(url: string) {
  const paramSweeps: Body[] = [];
  const analysesAsked: Body[] = [];
  const cells: Body[] = [];
  const r = mountDesignSession({
    url,
    examples: [OTHER, DECK],
    // The chart is not pinned: the link has to bring it on screen.
    pinned: ["antenna"],
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
        const b = JSON.parse(String(init?.body ?? "{}")) as Body & { param: string; values: number[] };
        paramSweeps.push(b);
        const lines = b.values.map((v) =>
          JSON.stringify({ param: b.param, value: v, z_re: 60 + v, z_im: 1, held: { gap: 0.2 }, converged: true }),
        );
        lines.push(JSON.stringify({ done: true, solver: "momwire" }));
        return ndjson(lines);
      },
      // A family's cells: asked for, not drawn (the answer is a refusal).
      "/pattern_cell": (_url: string, init?: RequestInit) => {
        cells.push(JSON.parse(String(init?.body ?? "{}")) as Body);
        return { ok: true, status: 200, json: async () => ({ available: false }) } as unknown as Response;
      },
      "/analyses": (_url: string, init?: RequestInit) => {
        analysesAsked.push(JSON.parse(String(init?.body ?? "{}")) as Body);
        return { ok: true, status: 200, json: async () => ANALYSES } as unknown as Response;
      },
    },
  });
  await sessionReady(document.body);
  return { ...r, paramSweeps, analysesAsked, cells };
}

const ready = () => document.querySelector<HTMLElement>(".app[data-ready]")?.dataset.ready ?? "";
const head = () => document.querySelector<HTMLElement>("[data-chart-kind]");
const picker = () => screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null;
const chartViewBox = () => screen.queryByRole("combobox", { name: "Chart view" }) as HTMLSelectElement | null;
const notice = () => screen.queryByRole("alert", { name: "Link problems" });
const query = () => new URLSearchParams(window.location.search);
// Settled: the link has been applied and the URL written back (the session
// writes it only once the link is done).
const settled = (analysis: string) =>
  untilDom(() => (head()?.dataset.analysis === analysis && query().get("analysis") === analysis) || null);
// The dwell a dwelling knob sweep would wait out, and more: a sweep that
// would start on its own has started by then.
const pastDwell = () => new Promise((r) => setTimeout(r, 900));

beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("a deep link opens the design and selects the analysis", () => {
  it("selects a held analysis and its view, and runs nothing without run=1", async () => {
    const { paramSweeps } = await open("/?design=dipoles.deck&analysis=match%20vs%20height&view=Knobs");
    expect(ready()).toMatch(/^dipoles\.deck#/);
    await settled("match vs height");
    expect(picker()!.value).toBe("match vs height");
    await untilDom(() => chartViewBox()?.value === "Knobs" || null);
    // Held: its switch is off, and the link only selected it.
    expect(head()!.dataset.dwell).toBe("0");
    await pastDwell();
    expect(paramSweeps).toHaveLength(0);
    expect(notice()).toBeNull();
    expect(query().get("design")).toBe("dipoles.deck");
    expect(query().get("view")).toBe("Knobs");
  });

  it("with run=1 starts exactly one run, the analysis's own", async () => {
    const { paramSweeps } = await open("/?design=dipoles.deck&analysis=match%20vs%20height&run=1");
    await settled("match vs height");
    await untilDom(() => paramSweeps.length > 0 || null);
    await pastDwell();
    expect(paramSweeps).toHaveLength(1);
    expect(paramSweeps[0]).toEqual(
      expect.objectContaining({ param: "base", values: HEIGHT_VALUES, hold: HOLD_SPEC }),
    );
    // run is never written back: a copied link does not spend solves.
    expect(query().get("run")).toBeNull();
  });

  it("selects a study by its bare name, and writes back its full name", async () => {
    const { paramSweeps } = await open("/?design=dipoles.deck&analysis=feed%20spelling%20(E7)");
    await settled(STUDY);
    expect(picker()!.value).toBe(STUDY);
    await pastDwell();
    expect(paramSweeps).toHaveLength(0);
    expect(window.location.search).toContain("analysis=dipoles.apex_feed_on_deck:feed%20spelling%20(E7)");
  });

  it("opens the variant it names, and lists that variant's analyses", async () => {
    const { analysesAsked } = await open("/?design=dipoles.deck:tall&analysis=match%20vs%20height");
    await settled("match vs height");
    expect((screen.getByRole("combobox", { name: "variant" }) as HTMLSelectElement).value).toBe("tall");
    expect(analysesAsked[analysesAsked.length - 1]).toEqual(expect.objectContaining({ variant: "tall" }));
    expect(query().get("design")).toBe("dipoles.deck:tall");
  });
});

describe("an unknown name is reported by name and otherwise ignored", () => {
  it("an unknown design: the session opens on its own default", async () => {
    await open("/?design=dipoles.nope&analysis=match%20vs%20height");
    const n = await untilDom(() => notice());
    expect(n.textContent).toContain(`no design "dipoles.nope"`);
    expect(ready()).toMatch(/^beams\.other#/);
    await untilDom(() => query().get("design") === "beams.other" || null);
  });

  it("an unknown variant: the design opens on its first", async () => {
    await open("/?design=dipoles.deck:short&analysis=match%20vs%20height");
    await settled("match vs height");
    expect(notice()!.textContent).toContain(`has no variant "short"`);
    expect((screen.getByRole("combobox", { name: "variant" }) as HTMLSelectElement).value).toBe("default");
  });

  it("an unknown analysis: the chart keeps its own sweep", async () => {
    await open("/?design=dipoles.deck&analysis=bogus&view=Knobs");
    const n = await untilDom(() => notice());
    expect(n.textContent).toContain(`no analysis "bogus"`);
    expect(ready()).toMatch(/^dipoles\.deck#/);
    expect(head()!.dataset.analysis).toBe("");
    await untilDom(() => (query().get("design") === "dipoles.deck" && query().get("analysis") === null) || null);
  });

  it("an unknown view: the analysis is still selected", async () => {
    await open("/?design=dipoles.deck&analysis=match%20vs%20height&view=Spiral");
    await settled("match vs height");
    const n = await untilDom(() => notice());
    expect(n.textContent).toContain(`no view "Spiral"`);
    expect(chartViewBox()!.value).toBe("Rx");
  });
});

describe("the URL follows the tab", () => {
  it("tracks the analysis and the design with replaceState, adding no history", async () => {
    await open("/?design=dipoles.deck&analysis=match%20vs%20height");
    await settled("match vs height");
    const depth = window.history.length;
    fireEvent.change(picker()!, { target: { value: STUDY } });
    await untilDom(() => query().get("analysis") === STUDY || null);
    fireEvent.change(screen.getByRole("combobox", { name: "variant" }), { target: { value: "tall" } });
    await untilDom(() => query().get("design") === "dipoles.deck:tall" || null);
    expect(window.history.length).toBe(depth);
  });

  it("a plain visit gets its design written, and no analysis", async () => {
    await open("/");
    await untilDom(() => query().get("design") === "beams.other" || null);
    expect(query().get("analysis")).toBeNull();
    expect(notice()).toBeNull();
  });

  it("the chart's link button copies this tab's link, and says it is this tab's only", async () => {
    const writes: string[] = [];
    vi.stubGlobal("navigator", {
      ...navigator,
      clipboard: { writeText: async (t: string) => void writes.push(t) },
    });
    await open("/?design=dipoles.deck&analysis=match%20vs%20height&view=Knobs");
    await settled("match vs height");
    await untilDom(() => chartViewBox()?.value === "Knobs" || null);
    const btn = screen.getAllByRole("button", { name: "Copy a link to this chart" })[0];
    expect(btn.getAttribute("title")).toBe(COPY_LINK_TITLE);
    expect(COPY_LINK_TITLE).toContain("this tab only");
    fireEvent.click(btn);
    await untilDom(() => writes.length > 0 || null);
    expect(writes[0]).toBe(
      `${window.location.origin}/?design=dipoles.deck&analysis=match%20vs%20height&view=Knobs`,
    );
    await untilDom(() => btn.textContent === "copied" || null);
  });
});

describe("a link carries a pattern family (AK#1935)", () => {
  const FAMILY_LINK = "/?design=dipoles.deck&family=base:4:14:3&view=pattern:1";
  const box = (name: string) => (screen.getByRole("textbox", { name }) as HTMLInputElement).value;

  it("opens the family on its knob, range and view, and asks one cell per value", async () => {
    const { cells } = await open(FAMILY_LINK);
    await untilDom(() => (head()?.dataset.chartKind === "pattern" && query().get("family") ? true : null));
    expect(chartViewBox()!.value).toBe("pattern:1");
    expect([box("from"), box("to"), box("values")]).toEqual(["4", "14", "3"]);
    expect((screen.getByRole("combobox", { name: "Parameter" }) as HTMLSelectElement).value).toBe("base");
    await untilDom(() => (cells.length >= 3 ? true : null));
    expect(cells.map((b) => b.base)).toEqual([4, 9, 14]);
    expect(notice()).toBeNull();
  });

  it("the copied link is the one that opens it, and an edited range rides in the next copy", async () => {
    const writes: string[] = [];
    vi.stubGlobal("navigator", {
      ...navigator,
      clipboard: { writeText: async (t: string) => void writes.push(t) },
    });
    await open(FAMILY_LINK);
    await untilDom(() => (head()?.dataset.chartKind === "pattern" && query().get("family") ? true : null));
    // The URL follows the tab: the family is in it, with its view.
    expect(query().get("family")).toBe("base:4:14:3");
    expect(query().get("view")).toBe("pattern:1");
    const to = screen.getByRole("textbox", { name: "to" });
    fireEvent.change(to, { target: { value: "12" } });
    fireEvent.blur(to);
    await untilDom(() => query().get("family") === "base:4:12:3" || null);
    fireEvent.click(screen.getAllByRole("button", { name: "Copy a link to this chart" })[0]);
    await untilDom(() => writes.length > 0 || null);
    expect(writes[0]).toBe(
      `${window.location.origin}/?design=dipoles.deck&family=base:4:12:3&view=pattern:1`,
    );
  });

  // AK#1950: the family's cut angle rides as cut=. Mutation notes (run by
  // hand, 2026-10-07; each reverted after): the session's view stage not
  // applying deepLink.cut fails "opens at the link's cut" (the menu reads
  // "Azimuth @ 10° el", the cells ask at 10); linkStateOf not writing `cut`
  // fails "the URL follows a cut" and "opens at the link's cut" (no cut= in
  // the address).
  it("opens at the link's cut: the menu names it and every cell asks at it", async () => {
    const { cells } = await open(`${FAMILY_LINK}&cut=22`);
    await untilDom(() => (head()?.dataset.chartKind === "pattern" && query().get("family") ? true : null));
    expect(chartViewBox()!.selectedOptions[0].textContent).toBe("Azimuth @ 22° el");
    expect(box("cut elevation")).toBe("22");
    await untilDom(() => (cells.length >= 3 ? true : null));
    expect(cells.map((b) => b.az_elev_deg)).toEqual([22, 22, 22]);
    expect(query().get("cut")).toBe("22");
    expect(notice()).toBeNull();
  });

  it("an old link (no cut=) opens at the view's own angle and stays without one", async () => {
    const { cells } = await open(FAMILY_LINK);
    await untilDom(() => (head()?.dataset.chartKind === "pattern" && query().get("family") ? true : null));
    expect(chartViewBox()!.selectedOptions[0].textContent).toBe("Azimuth @ 10° el");
    await untilDom(() => (cells.length >= 3 ? true : null));
    expect(cells.map((b) => b.az_elev_deg)).toEqual([10, 10, 10]);
    expect(query().has("cut")).toBe(false);
  });

  it("the URL follows a cut set on the chart, and drops it back at the view's own", async () => {
    await open(FAMILY_LINK);
    await untilDom(() => (head()?.dataset.chartKind === "pattern" && query().get("family") ? true : null));
    const cut = screen.getByRole("textbox", { name: "cut elevation" });
    fireEvent.change(cut, { target: { value: "30" } });
    fireEvent.blur(cut);
    await untilDom(() => query().get("cut") === "30" || null);
    fireEvent.change(cut, { target: { value: "10" } });
    fireEvent.blur(cut);
    await untilDom(() => !query().has("cut") || null);
  });

  it("a cut the view refuses is named, and the view's own angle stays", async () => {
    await open(`${FAMILY_LINK}&cut=0`);
    await untilDom(() => notice() || null);
    expect(notice()!.textContent).toContain("cut 0°");
    expect(chartViewBox()!.selectedOptions[0].textContent).toBe("Azimuth @ 10° el");
  });

  it("names a knob the design does not have, and leaves the chart as it was", async () => {
    await open("/?design=dipoles.deck&family=nope:1:2:3&view=pattern:0");
    await untilDom(() => notice() || null);
    expect(notice()!.textContent).toContain('"nope"');
    expect(head()!.dataset.chartKind).not.toBe("pattern");
  });
});
