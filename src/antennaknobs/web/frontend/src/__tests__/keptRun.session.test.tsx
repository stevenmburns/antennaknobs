// A kept band run in the workbench (AK#1906), through the real app shell on
// an opened deck (UR0GT's four SY knobs, the /deck stub's record): /analyses
// lists the kept run under Studies; picking it jumps the knobs to its stored
// answer, marks its knobs over its ranges and shows its stored table; "Run
// again from its start" puts the knobs back at its start and sends ONE
// /optimize with its bands, knobs and ranges; the run's result offers Keep,
// whose /keep body is the run (origin "optimize").
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import type { ExampleDescriptor } from "../lib/params";
import { clearDecks } from "../lib/decks";
import { invveeShape } from "./fixtures/solveShapes";
import UR0GT from "./fixtures/ur0gtDeckExample.json";
import { HARNESS_EXAMPLE, mountDesignSession, sessionReady, untilDom } from "./designSessionHarness";

vi.setConfig({ testTimeout: 30_000 });

const DECK = UR0GT as unknown as ExampleDescriptor;
const KEY = DECK.name;
const START: Record<string, number> = { sy_w5hgt: 12, sy_w6len: 61.22, sy_cap1: 340, sy_cap2: 41 };
const STORED = { sy_w5hgt: 12.5, sy_cap1: 480 };
const BANDS = [1.83, 3.7, 7.1];

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
  ({ ok: status < 400, status, headers: { get: () => "application/json" }, json: async () => body }) as unknown as Response;

// The kept run as /analyses serves it on the deck's tab.
const KEPT = {
  name: "ur0gt/three:UR0GT 160/80/40",
  group: "General",
  summary: "optimize sy_w5hgt, sy_cap1 across 1.83/3.7/7.1 MHz (minimax, balance 0.5)",
  code: "an.Optimize(...)",
  problems: [],
  study: { source: "ur0gt/three", name: "UR0GT 160/80/40" },
  workbench: {
    runs: true,
    kind: "optimize",
    state: {},
    free: [
      { name: "sy_w5hgt", min: 8, max: 16 },
      { name: "sy_cap1", min: 100, max: 1000 },
    ],
    bands: BANDS.map((freq) => ({ freq, objective: "swr", feed: 0, z0: null })),
    mode: "minimax",
    mean_weight: 0.5,
    z0: 50,
    result: {
      knobs: STORED,
      bands: BANDS.map((freq, i) => ({ freq, swr_before: [1.5, 15.3, 11.1][i], swr_after: [1.4, 2.1, 1.9][i] })),
    },
    note: null,
  },
};

const band = (index: number, freq: number, swr: number) => ({
  index,
  freq_mhz: freq,
  objective: "swr",
  feed: 0,
  z0_ohms: 50,
  z_re: 50 + swr,
  z_im: 0,
  swr,
  residual: null,
  value: swr,
});

const RESULT = {
  objective: "bands",
  form: "minimax",
  params: STORED,
  params_before: { sy_w5hgt: 12, sy_cap1: 340 },
  bands_before: BANDS.map((f, i) => band(i, f, [1.5, 15.3, 11.1][i])),
  bands_after: BANDS.map((f, i) => band(i, f, [1.4, 2.1, 1.9][i])),
  objective_before: 12,
  objective_after: 2,
  worst_swr_before: 15.3,
  worst_swr_after: 2.1,
  metrics_before: { z_in_re: 30, z_in_im: 0, z0_ohms: 50, swr: 15.3 },
  metrics_after: { z_in_re: 52, z_in_im: 0, z0_ohms: 50, swr: 2.1 },
  n_evals: 30,
  improved: true,
};

function optimizeRoute(bodies: Body[]) {
  return (_u: string, init?: RequestInit) => {
    bodies.push(JSON.parse(String(init?.body ?? "{}")) as Body);
    const enc = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(enc.encode("event: result\ndata: " + JSON.stringify(RESULT) + "\n\n"));
        c.close();
      },
    });
    return {
      ok: true,
      status: 200,
      headers: { get: (h: string) => (h.toLowerCase() === "content-type" ? "text/event-stream" : null) },
      body,
    } as unknown as Response;
  };
}

const knob = (name: string) =>
  screen.getByRole("slider", { name: new RegExp(`^${name.replace(/^sy_/, "")}`) });
const valueOf = (name: string) => Number(knob(name).getAttribute("aria-valuenow"));
const ready = () => document.querySelector<HTMLElement>(".app[data-ready]")?.dataset.ready ?? "";

async function openUr0gt() {
  await sessionReady(document.body);
  const input = screen.getByLabelText("open an antenna model (.nec, .ssn or .maa)") as HTMLInputElement;
  const text = "CM stand-in: the /deck stub answers with the UR0GT record\nCE\nEN\n";
  const file = new File([text], "UR0GT_SY_vert_inv_L.nec");
  if (typeof (file as Blob).text !== "function") {
    Object.defineProperty(file, "text", { value: async () => text });
  }
  fireEvent.change(input, { target: { files: [file] } });
  await waitFor(() => expect(ready().startsWith(`${KEY}#`)).toBe(true), { timeout: 5000 });
}

beforeEach(() => {
  vi.stubGlobal("WebSocket", StubWebSocket);
});
afterEach(() => {
  clearDecks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("a kept band run", () => {
  it("is listed under Studies, jumps to its stored answer, runs again, and keeps", async () => {
    const optimized: Body[] = [];
    const kept: Body[] = [];
    mountDesignSession({
      url: "/",
      examples: [HARNESS_EXAMPLE],
      pinned: ["antenna", "zparam"],
      routes: {
        "/deck": () => json({ key: KEY, example: DECK, limits: {} }),
        "/geometry": () => json({ wires: [] }),
        "/analyses": () => json({ geometry: KEY, analyses: [KEPT] }),
        "/optimize": optimizeRoute(optimized),
        "/keep": (_u: string, init?: RequestInit) => {
          kept.push(JSON.parse(String(init?.body ?? "{}")) as Body);
          return json({ code: "# kept\n", name: "UR0GT 160/80/40", problems: [], study_refusal: null });
        },
      },
    });
    await openUr0gt();
    expect(valueOf("sy_cap1")).toBeCloseTo(START.sy_cap1, 6);

    fireEvent.click(document.querySelector(".thumbstrip canvas.smith") as HTMLElement);
    const select = await untilDom(
      () => screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null,
    );
    const studies = await untilDom(() => select.querySelector('optgroup[label="Studies"]'));
    const option = within(studies as HTMLElement).getByRole("option") as HTMLOptionElement;
    expect(option.textContent).toBe("UR0GT 160/80/40 (jump to)");
    expect(option.disabled).toBe(false);

    // The jump: the stored knobs, nothing searched.
    fireEvent.change(select, { target: { value: KEPT.name } });
    await waitFor(() => expect(valueOf("sy_cap1")).toBeCloseTo(STORED.sy_cap1, 6));
    expect(valueOf("sy_w5hgt")).toBeCloseTo(STORED.sy_w5hgt, 6);
    expect(valueOf("sy_w6len")).toBeCloseTo(START.sy_w6len, 6);
    const panel = await screen.findByRole("group", { name: "Kept run" });
    expect(panel.textContent).toContain("UR0GT 160/80/40");
    const table = within(panel).getByRole("table", { name: "Band results" });
    const worst = within(table).getByRole("row", { name: /worst/ });
    expect(worst.textContent).toBe("worst15.302.10");
    expect(optimized).toHaveLength(0);

    // Run again from its start: the start's knobs, ONE /optimize with the
    // run's knobs, ranges, bands and balance.
    fireEvent.click(within(panel).getByRole("button", { name: "Run again from its start" }));
    await waitFor(() => expect(optimized).toHaveLength(1), { timeout: 5000 });
    const opt = optimized[0].optimize as {
      free: { name: string; min: number; max: number }[];
      bands: { freq: number }[];
      mean_weight: number;
    };
    expect(opt.free).toEqual(KEPT.workbench.free);
    expect(opt.bands.map((b) => b.freq)).toEqual(BANDS);
    expect(opt.mean_weight).toBe(0.5);
    expect(optimized[0].sy_cap1).toBe(START.sy_cap1);

    // The fresh result offers Keep, and keeping sends the run.
    fireEvent.click(await screen.findByRole("button", { name: "Keep…" }, { timeout: 5000 }));
    await waitFor(() => expect(kept.length).toBeGreaterThan(0), { timeout: 5000 });
    const body = kept.at(-1)!;
    expect(body.origin).toBe("optimize");
    expect(body.form).toBe("study");
    expect(body.free).toEqual(KEPT.workbench.free);
    expect(body.bands).toEqual(BANDS.map((freq) => ({ freq })));
    expect((body.result as { params: unknown }).params).toEqual(STORED);
    expect((body.tab as Body).geometry).toBe(KEY);
  });
});
