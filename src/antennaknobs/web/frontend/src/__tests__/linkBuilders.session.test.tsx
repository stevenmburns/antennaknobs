// The map and hold builders and Copy link (AK#2045) through the real app
// shell, on the issue's own case: dipoles.two_wire_doublet opened as a NEC-5
// deck link with SY knobs L and M, the catalog's three analyses and its knob
// ranges (fixtures/doubletLink.ts holds what the real server answered).
//
//   - Copy link writes a link carrying the deck, its ranges, the knobs as
//     the panel holds them and the listed analyses as one analyses=, each
//     the Python /keep writes for it; opened in a fresh page, the same deck,
//     ranges and analyses go to /deck and the chart's analysis is picked;
//   - the knob menu's map builder lists a built map and runs it (POST /map),
//     and its hold builder a held sweep (POST /param_sweep with the hold);
//     Copy link then carries those too;
//   - a part over what a link carries is refused by name, and nothing is
//     copied;
//   - a catalog design's link carries analyses= too, sent with /analyses.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { clearDecks, compressDeck, MAX_SHARE_CHARS } from "../lib/decks";
import { parseDeepLink } from "../lib/deepLink";
import { analysesText } from "../lib/buildAnalysis";
import { invveeShape } from "./fixtures/solveShapes";
import {
  DOUBLET_ANALYSES,
  DOUBLET_ENTRIES,
  DOUBLET_EXPRS,
  DOUBLET_RANGES,
  DOUBLET_SCHEMA,
  DOUBLET_Z,
} from "./fixtures/doubletLink";
import { HARNESS_EXAMPLE, mountDesignSession, sessionReady, untilDom } from "./designSessionHarness";

vi.setConfig({ testTimeout: 30_000 });

const KEY = "deck.0123456789ab";
const DECK_EXAMPLE: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  name: KEY,
  label: "two_wire_doublet",
  param_schema: DOUBLET_SCHEMA,
};
const KNOBS = "sy_long_ft:33:15:36,sy_short_ft:33:1:34";
const LINK =
  `/?deck=${DOUBLET_Z}&name=two_wire_doublet.nec&analyses=${DOUBLET_ANALYSES}` +
  `&knobs=${KNOBS}&analysis=resonance%20map&view=Map`;

type Body = Record<string, unknown>;

class StubWebSocket {
  static OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    setTimeout(() => {
      this.readyState = StubWebSocket.OPEN;
      this.onopen?.();
    }, 0);
  }
  send(payload: string) {
    const req = JSON.parse(payload) as Body;
    if (!("geometry" in req) || typeof req._seq !== "number") return;
    const out = { ...invveeShape, feeds: undefined, geometry: req.geometry, _seq: req._seq, z0_ohms: 50 };
    setTimeout(() => this.onmessage?.({ data: JSON.stringify(out) } as MessageEvent), 0);
  }
  close() {}
}

const json = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

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

/** A link's analyses= as text again (deflate-raw, base64url). */
async function inflate(z: string): Promise<string> {
  const b64 = z.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((z.length + 3) % 4);
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const input = new ReadableStream<BufferSource>({
    start(c) {
      c.enqueue(bytes);
      c.close();
    },
  });
  const reader = input.pipeThrough(new DecompressionStream("deflate-raw")).getReader();
  let out = "";
  const dec = new TextDecoder();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    out += dec.decode(value, { stream: true });
  }
  return out + dec.decode();
}

const lin = (lo: number, hi: number, n: number) =>
  Array.from({ length: n }, (_, i) => lo + ((hi - lo) * i) / (n - 1));

type Spec = {
  name: string;
  sweep: { knob: string; lo: number; hi: number; points: number } | { knob: string; lo: number; hi: number; points: number }[];
  hold?: { objective: string; adjust: string[] };
};

/** What the real server lists for a built analysis's text, here from the
 *  spec /keep was sent for it (the stub's `expr` names it). */
function builtEntry(spec: Spec) {
  const axis = (s: { knob: string; lo: number; hi: number; points: number }) => ({
    param: s.knob,
    values: lin(s.lo, s.hi, s.points),
    log: false,
    lo: s.lo,
    hi: s.hi,
    points: s.points,
    spacing: "lin",
  });
  const workbench = Array.isArray(spec.sweep)
    ? {
        runs: true,
        kind: "map",
        x: axis(spec.sweep[0]),
        y: axis(spec.sweep[1]),
        refs: { r: [], x: [0], swr: null },
        views: ["Map"],
        limit: null,
        note: null,
      }
    : {
        runs: true,
        kind: "knob",
        param: spec.sweep.knob,
        values: lin(spec.sweep.lo, spec.sweep.hi, spec.sweep.points),
        log: false,
        views: ["Rx", "Knobs"],
        hold: {
          objective: spec.hold!.objective,
          knobs: spec.hold!.adjust,
          bounds: Object.fromEntries(spec.hold!.adjust.map((k) => [k, [15, 36]])),
          z0: null,
          warm_start: true,
          spec: { an: "Hold", ...spec.hold },
        },
        note: null,
      };
  return { name: spec.name, summary: "", code: "", problems: [], origin: "built", spec, workbench };
}

function mount(url: string, over: { exprOf?: (spec: Spec) => string; pinned?: string[] } = {}) {
  const opened: Body[] = [];
  const asked: Body[] = [];
  const keeps: Body[] = [];
  const maps: Body[] = [];
  const sweeps: Body[] = [];
  const builtSpecs = new Map<string, Spec>();
  const r = mountDesignSession({
    url,
    examples: [HARNESS_EXAMPLE],
    pinned: (over.pinned ?? ["antenna"]) as never,
    routes: {
      "/deck": (_u: string, init?: RequestInit) => {
        opened.push(JSON.parse(String(init?.body ?? "{}")) as Body);
        return json({ key: KEY, example: DECK_EXAMPLE, limits: {}, analyses: 3, analyses_refusal: null, ranges_refusal: null });
      },
      "/geometry": () => json({ wires: [] }),
      "/analyses": (_u: string, init?: RequestInit) => {
        const b = JSON.parse(String(init?.body ?? "{}")) as Body;
        asked.push(b);
        if (b.geometry !== KEY) return json({ analyses: [] });
        const built = ((b.built as string[] | undefined) ?? []).map((t) => builtEntry(builtSpecs.get(t)!));
        return json({ analyses: [...DOUBLET_ENTRIES, ...built], analyses_refusal: null, built_refusal: null });
      },
      "/keep": (_u: string, init?: RequestInit) => {
        const b = JSON.parse(String(init?.body ?? "{}")) as Body & { spec: Spec };
        keeps.push(b);
        const name = (b.name as string | undefined) ?? b.spec.name;
        let expr = DOUBLET_EXPRS[b.spec.name];
        if (over.exprOf) expr = over.exprOf(b.spec);
        else if (!expr) {
          expr = `an.Analysis(${JSON.stringify(name)}, built=True)`;
          builtSpecs.set(expr, b.spec);
        }
        return json({ code: `# copied\n${expr}\n`, name, problems: [], study_refusal: null, expr });
      },
      "/map": (_u: string, init?: RequestInit) => {
        const b = JSON.parse(String(init?.body ?? "{}")) as Body & {
          x: { values: number[] };
          y: { values: number[] };
        };
        maps.push(b);
        const lines: string[] = [];
        b.y.values.forEach((_y, j) =>
          b.x.values.forEach((_x, i) => lines.push(JSON.stringify({ i, j, z_re: 50, z_im: i - j, solver: "momwire" }))),
        );
        lines.push(JSON.stringify({ done: true, solver: "momwire", points: lines.length }));
        return ndjson(lines);
      },
      "/param_sweep": (_u: string, init?: RequestInit) => {
        const b = JSON.parse(String(init?.body ?? "{}")) as Body & { param: string; values: number[] };
        sweeps.push(b);
        const lines = b.values.map((v) =>
          JSON.stringify({ param: b.param, value: v, z_re: 60, z_im: 0, held: { sy_long_ft: 33 }, converged: true }),
        );
        lines.push(JSON.stringify({ done: true, solver: "momwire" }));
        return ndjson(lines);
      },
    },
  });
  return { ...r, opened, asked, keeps, maps, sweeps };
}

const ready = () => document.querySelector<HTMLElement>(".app[data-ready]")?.dataset.ready ?? "";
const head = () => document.querySelector<HTMLElement>("[data-chart-kind]");
const notice = () => screen.queryByRole("alert", { name: "Link problems" });
const linkButton = () => screen.getAllByRole("button", { name: "Copy a link to this chart" })[0];

let writes: string[] = [];
beforeEach(() => {
  writes = [];
  vi.stubGlobal("WebSocket", StubWebSocket);
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText: async (t: string) => void writes.push(t) } });
});
afterEach(() => {
  clearDecks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

async function openDoublet(url = LINK) {
  const r = mount(url);
  await sessionReady(document.body);
  await waitFor(() => expect(ready()).toMatch(/^deck\.0123456789ab#/), { timeout: 5000 });
  return r;
}

describe("Copy link on the doublet deck (the AK#2045 acceptance)", () => {
  it("carries the deck, its ranges, the knobs and the three analyses; a fresh page opens the same", async () => {
    const { opened, keeps } = await openDoublet();
    expect(opened[0]).toEqual({
      name: "two_wire_doublet.nec",
      z: DOUBLET_Z,
      analyses: DOUBLET_ANALYSES,
      ranges: DOUBLET_RANGES,
    });
    await untilDom(() => (head()?.dataset.analysis === "resonance map" ? true : null));
    expect(notice()).toBeNull();
    fireEvent.click(linkButton());
    await untilDom(() => writes.length > 0 || null);
    const status = await screen.findByRole("status", { name: "Copy link" });
    const copied = writes[0];
    expect(status.textContent).toBe(`link copied (${copied.length} characters)`);
    // Each listed analysis was asked of /keep by its spec, as Copy as
    // analysis asks it.
    expect(keeps.map((k) => (k.spec as Spec).name)).toEqual(DOUBLET_ENTRIES.map((e) => e.name));
    expect(keeps.every((k) => k.origin === "chart" && k.form === "analysis")).toBe(true);
    const url = new URL(copied);
    expect(url.origin + url.pathname).toBe(`${window.location.origin}/`);
    const link = parseDeepLink(url.search)!;
    expect(link.deck!.z).toBe(DOUBLET_Z);
    expect(link.deck!.name).toBe("two_wire_doublet.nec");
    expect(link.deck!.ranges).toBe(DOUBLET_RANGES);
    expect(link.knobs).toEqual([
      { name: "sy_long_ft", value: 33, min: 15, max: 36 },
      { name: "sy_short_ft", value: 33, min: 1, max: 34 },
    ]);
    expect(link.analysis).toBe("resonance map");
    expect(link.view).toBe("Map");
    expect(link.run).toBe(false);
    // The same three analyses, as /keep wrote them, in the picker's order.
    const text = await inflate(link.deck!.analyses!);
    expect(text).toBe(analysesText(DOUBLET_ENTRIES.map((e) => DOUBLET_EXPRS[e.name])));
    expect(link.deck!.analyses!.length).toBeLessThanOrEqual(MAX_SHARE_CHARS);
    console.log(
      `AK#2045 copied link: ${copied.length} characters (deck ${DOUBLET_Z.length}, analyses ` +
        `${link.deck!.analyses!.length}, knobs ${KNOBS.length})`,
    );

    // A fresh page on the copied link: the deck opens with the same
    // analyses and ranges, the knobs are set, and the analysis is picked.
    clearDecks();
    window.history.replaceState(null, "", "/");
    const fresh = mount(url.pathname + url.search);
    await sessionReady(document.body);
    await waitFor(() => expect(fresh.opened.length).toBeGreaterThan(0), { timeout: 5000 });
    expect(fresh.opened[fresh.opened.length - 1]).toEqual({
      name: "two_wire_doublet.nec",
      z: DOUBLET_Z,
      analyses: link.deck!.analyses,
      ranges: DOUBLET_RANGES,
    });
    await untilDom(
      () =>
        [...document.querySelectorAll<HTMLElement>("[data-chart-kind]")].some(
          (h) => h.dataset.analysis === "resonance map",
        ) || null,
    );
    const picker = screen.getAllByRole("combobox", { name: "Analysis" }) as HTMLSelectElement[];
    expect(picker.some((p) => p.value === "resonance map")).toBe(true);
  });

  it("the map and hold builders list and run their analyses, and Copy link carries them", async () => {
    const { keeps, maps, sweeps, asked } = await openDoublet(
      `/?deck=${DOUBLET_Z}&name=two_wire_doublet.nec&analyses=${DOUBLET_ANALYSES}&knobs=${KNOBS}`,
    );
    // The map builder, from L's knob menu.
    fireEvent.contextMenu(await screen.findByRole("slider", { name: "long_ft" }));
    fireEvent.click(screen.getByRole("button", { name: "Map against another knob…" }));
    const mapDialog = await screen.findByRole("dialog", { name: "Build a map" });
    const field = (d: HTMLElement, name: string) => within(d).getByRole("spinbutton", { name }) as HTMLInputElement;
    expect((within(mapDialog).getByRole("combobox", { name: "x knob" }) as HTMLSelectElement).value).toBe("sy_long_ft");
    expect((within(mapDialog).getByRole("combobox", { name: "y knob" }) as HTMLSelectElement).value).toBe("sy_short_ft");
    // The knob's own range is the link's.
    expect(field(mapDialog, "x from").value).toBe("15");
    expect(field(mapDialog, "x to").value).toBe("36");
    fireEvent.change(field(mapDialog, "x points"), { target: { value: "5" } });
    fireEvent.change(field(mapDialog, "y points"), { target: { value: "4" } });
    const name = within(mapDialog).getByRole("textbox", { name: "The analysis's name" }) as HTMLInputElement;
    expect(name.value).toBe("map long_ft × short_ft");
    fireEvent.click(within(mapDialog).getByRole("button", { name: "build and run" }));
    await untilDom(() => maps.length > 0 || null);
    expect(screen.queryByRole("dialog", { name: "Build a map" })).toBeNull();
    const mapSpec = keeps.find((k) => (k.spec as Spec).name === "map long_ft × short_ft")!.spec;
    expect(mapSpec).toEqual({
      an: "Analysis",
      name: "map long_ft × short_ft",
      sweep: [
        { an: "Sweep", knob: "sy_long_ft", lo: 15, hi: 36, points: 5 },
        { an: "Sweep", knob: "sy_short_ft", lo: 1, hi: 34, points: 4 },
      ],
      views: [{ an: "Map" }],
      references: { an: "Ref", x: [0] },
    });
    // Listed by sending its text with /analyses, and run as a map runs.
    expect(asked.some((a) => (a.built as string[] | undefined)?.length === 1)).toBe(true);
    expect((maps[0].x as { param: string }).param).toBe("sy_long_ft");
    expect((maps[0].y as { values: number[] }).values).toHaveLength(4);
    await untilDom(() => (head()?.dataset.analysis === "map long_ft × short_ft" ? true : null));

    // The hold builder, from M's: M swept, L held at resonance.
    fireEvent.contextMenu(screen.getByRole("slider", { name: "short_ft" }));
    fireEvent.click(screen.getByRole("button", { name: "Sweep, holding another knob…" }));
    const holdDialog = await screen.findByRole("dialog", { name: "Build a held sweep" });
    expect((within(holdDialog).getByRole("combobox", { name: "held knob 1" }) as HTMLSelectElement).value).toBe(
      "sy_long_ft",
    );
    // The range the hold searches, shown: no Optimize range was set, so L's own.
    expect(within(holdDialog).getByLabelText("long_ft range").textContent).toBe(
      "long_ft searched over 15 to 36 (its own range)",
    );
    fireEvent.change(field(holdDialog, "sweep from"), { target: { value: "33" } });
    fireEvent.change(field(holdDialog, "sweep to"), { target: { value: "3.5" } });
    fireEvent.change(field(holdDialog, "sweep points"), { target: { value: "6" } });
    fireEvent.change(within(holdDialog).getByRole("textbox", { name: "The analysis's name" }), {
      target: { value: "high-R, built" },
    });
    fireEvent.click(within(holdDialog).getByRole("button", { name: "build and run" }));
    await untilDom(() => sweeps.some((s) => s.hold) || null);
    const held = sweeps.find((s) => s.hold)!;
    expect(held.param).toBe("sy_short_ft");
    expect(held.values).toEqual(lin(33, 3.5, 6));
    expect(held.hold).toEqual({ an: "Hold", objective: "resonance", adjust: ["sy_long_ft"] });
    await untilDom(() => (head()?.dataset.analysis === "high-R, built" ? true : null));

    // Copy link: the link's three and the two built here.
    fireEvent.click(linkButton());
    await untilDom(() => writes.length > 0 || null);
    const link = parseDeepLink(new URL(writes[0]).search)!;
    expect(link.analysis).toBe("high-R, built");
    const text = await inflate(link.deck!.analyses!);
    for (const e of DOUBLET_ENTRIES) expect(text).toContain(DOUBLET_EXPRS[e.name].replace(/\n/g, "\n    "));
    expect(text).toContain('an.Analysis("map long_ft × short_ft", built=True)');
    expect(text).toContain('an.Analysis("high-R, built", built=True)');
  });
});

describe("Copy link refuses a link it cannot write", () => {
  it("names analyses over the cap, and copies nothing", async () => {
    // Text that does not compress: each analysis 6000 random characters.
    const noise = () =>
      Array.from({ length: 6000 }, () => String.fromCharCode(33 + Math.floor(Math.random() * 90))).join("");
    const r = mount(LINK, { exprOf: () => noise() });
    await sessionReady(document.body);
    await waitFor(() => expect(ready()).toMatch(/^deck\.0123456789ab#/), { timeout: 5000 });
    await untilDom(() => (head()?.dataset.analysis === "resonance map" ? true : null));
    fireEvent.click(linkButton());
    const why = await screen.findByRole("alert", { name: "Copy link" });
    expect(why.textContent).toMatch(/^No link copied: The analyses are \d+ characters packed, over the 8000 a link carries/);
    expect(writes).toEqual([]);
    expect(linkButton().textContent).toBe("not copied");
    expect(r.keeps.length).toBe(3);
  });

  it("names a deck too long to carry, and copies nothing", async () => {
    // A deck whose packed text is over the cap opens (the page holds it), but
    // no link can carry it.
    const big = "A".repeat(MAX_SHARE_CHARS + 10);
    const r = mount(`/?deck=${big}&name=big.nec`, { pinned: ["antenna", "zparam"] });
    await sessionReady(document.body);
    await waitFor(() => expect(ready()).toMatch(/^deck\.0123456789ab#/), { timeout: 5000 });
    // The chart on the stage, for its link button.
    fireEvent.click(r.container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
    fireEvent.click(linkButton());
    const why = await screen.findByRole("alert", { name: "Copy link" });
    expect(why.textContent).toContain(`The deck is ${big.length} characters packed, over the 8000 a link carries`);
    expect(writes).toEqual([]);
  });
});

describe("a catalog design's link carries analyses= (AK#2045)", () => {
  const knob = (over: Partial<SchemaParamSpec>): SchemaParamSpec => ({
    ...DOUBLET_SCHEMA[0],
    name: "long_ft",
    label: "L",
    ...over,
  });
  const DESIGN: ExampleDescriptor = {
    ...HARNESS_EXAMPLE,
    name: "dipoles.two_wire_doublet",
    label: "Two-wire doublet",
    param_schema: [knob({}), knob({ name: "short_ft", label: "M", min: 1, max: 34 })],
  };

  it("sends them with /analyses, keeps them in the address, and lists them", async () => {
    const z = await compressDeck('[an.Analysis("short sweep", an.Sweep("short_ft", 5, 30, points=6))]');
    const asked: Body[] = [];
    const entry = {
      name: "short sweep",
      summary: "",
      code: "",
      problems: [],
      origin: "link",
      spec: { an: "Analysis", name: "short sweep" },
      workbench: { runs: true, kind: "knob", param: "short_ft", values: lin(5, 30, 6), log: false, note: null },
    };
    mountDesignSession({
      url: `/?design=dipoles.two_wire_doublet&analyses=${z}&analysis=short%20sweep`,
      examples: [HARNESS_EXAMPLE, DESIGN],
      pinned: ["antenna"],
      routes: {
        "/analyses": (_u: string, init?: RequestInit) => {
          const b = JSON.parse(String(init?.body ?? "{}")) as Body;
          asked.push(b);
          return json({ analyses: b.analyses === z ? [entry] : [], analyses_refusal: null, built_refusal: null });
        },
        "/param_sweep": () => ndjson([JSON.stringify({ done: true, solver: "momwire" })]),
      },
    });
    await sessionReady(document.body);
    await untilDom(() => (head()?.dataset.analysis === "short sweep" ? true : null));
    expect(asked.some((a) => a.geometry === "dipoles.two_wire_doublet" && a.analyses === z)).toBe(true);
    await untilDom(() => (new URLSearchParams(window.location.search).get("analyses") === z ? true : null));
    expect(notice()).toBeNull();
  });
});
