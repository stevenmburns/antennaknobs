// AK 0.97.1: multi-band Optimize on an OPENED DECK (UR0GT's three-band
// vertical, four flat SY knobs). The hosted Fly log showed POST /optimize at
// 00:08:03, :04 and :05 — a new run about every second. Driven here through
// the real app shell (open the deck, mark the four knobs, set three bands,
// Optimize) against a stubbed streaming /optimize that sends progress frames
// over time and then its result.
//
// What the run itself does — its progress frames, its write-back of the four
// flat knobs, the live solve that follows — never re-triggers it (pinned
// below; it held before 0.97.1 too). What did: the band list is a signature
// input, so with Optimize ON every edit in the gear menu (Bands on, add 3.6,
// add 1.8) started a run and superseded the one before. Now opening the menu
// pauses Optimize and closing it resumes it, with ONE run. A run a genuine new
// input supersedes says "restarted" (AK#1912).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import type { ExampleDescriptor } from "../lib/params";
import { clearDecks } from "../lib/decks";
import { invveeShape } from "./fixtures/solveShapes";
import UR0GT from "./fixtures/ur0gtDeckExample.json";
import { HARNESS_EXAMPLE, mountDesignSession, sessionReady } from "./designSessionHarness";

vi.setConfig({ testTimeout: 30_000 });

const DECK = UR0GT as unknown as ExampleDescriptor;
const KEY = DECK.name;
const KNOBS = ["sy_w5hgt", "sy_w6len", "sy_cap1", "sy_cap2"] as const;
const START: Record<string, number> = { sy_w5hgt: 12, sy_w6len: 61.22, sy_cap1: 340, sy_cap2: 41 };
const AFTER: Record<string, number> = {
  sy_w5hgt: 12.327197014082534,
  sy_w6len: 65.22652334026529,
  sy_cap1: 510,
  sy_cap2: 23.953254447349472,
};
const BANDS = [7.2, 3.6, 1.8];

type Body = Record<string, unknown>;
const solves: Body[] = [];

// A socket that answers every solve, so live solves land during the run as
// they do on the hosted app.
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
    solves.push(req);
    // The answer depends on cap1 (R = cap1 / 10), so the readout shows which
    // knob values it was solved at.
    const r = typeof req.sy_cap1 === "number" ? req.sy_cap1 / 10 : 50;
    const out = { ...invveeShape, feeds: undefined, geometry: req.geometry, _seq: req._seq, z0_ohms: 50, z_in_re: r };
    setTimeout(() => this.onmessage?.({ data: JSON.stringify(out) } as MessageEvent), 0);
  }
  close() {}
}

const json = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, headers: { get: () => "application/json" }, json: async () => body }) as unknown as Response;

const band = (index: number, freq: number, swr: number) => ({
  index,
  freq_mhz: freq,
  objective: "swr",
  feed: 0,
  z0_ohms: 50,
  // The Z moves with the SWR, so each frame's markers move.
  z_re: 50 + 5 * swr,
  z_im: 10 * swr,
  swr,
  residual: null,
  value: swr,
});

function progressFrame(n: number, total: number): string {
  const t = n / total;
  const params = Object.fromEntries(KNOBS.map((k) => [k, START[k] + t * (AFTER[k] - START[k])]));
  const swrs = BANDS.map((_, i) => 15 - t * (11.7 - i));
  const worst = Math.max(...swrs);
  return (
    "event: progress\ndata: " +
    JSON.stringify({
      n_evals: n,
      n_solves: n,
      params,
      phase: n === 1 ? "start" : "least squares",
      form: "minimax",
      bands: BANDS.map((f, i) => band(i, f, swrs[i])),
      objective: worst,
      objective_worst: worst,
      objective_mean: swrs.reduce((a, b) => a + b, 0) / swrs.length,
      mean_weight: 0.5,
      worst_band: swrs.indexOf(worst),
      metrics: { z_in_re: 30, z_in_im: -140, z0_ohms: 50, swr: worst },
      residual: null,
      solve_ms: 40,
    }) +
    "\n\n"
  );
}

const RESULT = {
  objective: "bands",
  form: "minimax",
  params: AFTER,
  params_before: START,
  bands_before: BANDS.map((f, i) => band(i, f, [1.5, 15.3, 11.1][i])),
  bands_after: BANDS.map((f, i) => band(i, f, 3.2742)),
  objective_before: 12.3,
  objective_after: 3.2742,
  objective_worst_before: 15.3,
  objective_worst_after: 3.2742,
  objective_mean_before: 9.3,
  objective_mean_after: 3.2742,
  mean_weight: 0.5,
  worst_swr_before: 15.3,
  worst_swr_after: 3.2742,
  metrics_before: { z_in_re: 30.7, z_in_im: -141.9, z0_ohms: 50, swr: 15.3 },
  metrics_after: { z_in_re: 121.1, z_in_im: 67.2, z0_ohms: 50, swr: 3.2742 },
  n_evals: 151,
  improved: true,
};

// A streamed /optimize: `frames` progress frames `gapMs` apart, then the
// result. Aborting the request cancels the stream (the client cancels its
// reader on abort, which is what ends a superseded run).
// Which /optimize requests (by index) the client aborted: an abort is what
// cancels the request, and the server stops a run whose client has gone.
const aborted: number[] = [];

function streamingOptimize(optimizeBodies: Body[], frames = 20, gapMs = 60) {
  return (_u: string, init?: RequestInit) => {
    const n = optimizeBodies.length;
    optimizeBodies.push(JSON.parse(String(init?.body ?? "{}")) as Body);
    init?.signal?.addEventListener("abort", () => aborted.push(n));
    const enc = new TextEncoder();
    let timer: ReturnType<typeof setTimeout> | null = null;
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        let n = 0;
        const tick = () => {
          n += 1;
          if (n <= frames) {
            c.enqueue(enc.encode(progressFrame(n, frames)));
            timer = setTimeout(tick, gapMs);
          } else {
            c.enqueue(enc.encode("event: result\ndata: " + JSON.stringify(RESULT) + "\n\n"));
            c.close();
          }
        };
        timer = setTimeout(tick, gapMs);
      },
      cancel() {
        if (timer) clearTimeout(timer);
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

function mount(optimizeBodies: Body[], frames?: number, gapMs?: number) {
  mountDesignSession({
    url: "/",
    examples: [HARNESS_EXAMPLE],
    routes: {
      "/deck": () => json({ key: KEY, example: DECK, limits: {} }),
      "/geometry": () => json({ wires: [] }),
      "/optimize": streamingOptimize(optimizeBodies, frames, gapMs),
    },
  });
}

const ready = () => document.querySelector<HTMLElement>(".app[data-ready]")?.dataset.ready ?? "";

async function openUr0gt() {
  await sessionReady(document.body);
  const input = screen.getByLabelText("open an antenna model (.nec, .ssn, .maa or .ez)") as HTMLInputElement;
  const text = "CM stand-in: the /deck stub answers with the UR0GT record\nCE\nEN\n";
  const file = new File([text], "UR0GT_SY_vert_inv_L.nec");
  if (typeof (file as Blob).text !== "function") {
    Object.defineProperty(file, "text", { value: async () => text });
  }
  fireEvent.change(input, { target: { files: [file] } });
  await waitFor(() => expect(ready().startsWith(`${KEY}#`)).toBe(true), { timeout: 5000 });
}

const knob = (name: string) =>
  screen.getByRole("slider", { name: new RegExp(`^${name.replace(/^sy_/, "")}`) });

function markAll() {
  for (const k of KNOBS) fireEvent.keyDown(knob(k), { key: "o" });
}

const pause = (ms: number) =>
  act(async () => {
    await new Promise((r) => setTimeout(r, ms));
  });

// The gear menu's Bands section, edited the way a person does it: one edit
// at a time, `gapMs` apart (Steve's were about a second; anything over the
// re-tune's 400 ms debounce is a separate edit).
async function setBands(gapMs = 0) {
  fireEvent.click(screen.getByLabelText("Optimisation method"));
  fireEvent.click(screen.getByRole("menuitemcheckbox", { name: /Several bands at once/ }));
  const add = screen.getByLabelText("Add a band, MHz");
  for (const f of BANDS.slice(1)) {
    if (gapMs) await pause(gapMs);
    fireEvent.change(add, { target: { value: String(f) } });
    fireEvent.keyDown(add, { key: "Enter" });
  }
  if (gapMs) await pause(gapMs);
  const list = screen.getByRole("list", { name: "Band frequencies" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(3);
  // Close the popover the way a user does.
  fireEvent.click(screen.getByLabelText("Optimisation method"));
}

const optimizeButton = () => screen.getByRole("button", { name: /^Optimize/ });

// What differs between two /optimize bodies, the free knobs' values aside
// (the run writes those): the input that started the newer run.
function changedInputs(a: Body, b: Body): string[] {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  return [...keys]
    .filter((k) => !(KNOBS as readonly string[]).includes(k))
    .filter((k) => JSON.stringify(a[k]) !== JSON.stringify(b[k]))
    .map((k) => `${k}: ${JSON.stringify(a[k])} -> ${JSON.stringify(b[k])}`);
}

beforeEach(() => {
  solves.length = 0;
  aborted.length = 0;
  vi.stubGlobal("WebSocket", StubWebSocket);
});
afterEach(() => {
  clearDecks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("a band run on an opened deck's flat knobs", () => {
  it("sends exactly one /optimize for one press of Optimize, and finishes", async () => {
    const bodies: Body[] = [];
    mount(bodies);
    await openUr0gt();
    markAll();
    await setBands();
    fireEvent.click(optimizeButton());
    // The run streams 20 frames over ~1.2 s, then its result; wait for the
    // finished table, then a further second for any late re-trigger.
    await screen.findByRole("table", { name: "Band results" }, { timeout: 10_000 });
    await pause(1500);
    const diffs = bodies.slice(1).map((b, i) => changedInputs(bodies[i], b));
    expect({ requests: bodies.length, diffs }).toEqual({ requests: 1, diffs: [] });
    const opt = bodies[0].optimize as { free: { name: string }[]; bands: { freq: number }[] };
    expect(opt.free.map((f) => f.name)).toEqual([...KNOBS]);
    expect(opt.bands.map((b) => b.freq)).toEqual(BANDS);
    // The knobs carry the run's answer.
    expect(Number(knob("sy_cap1").getAttribute("aria-valuenow"))).toBeCloseTo(510, 3);
  });
});


const finished = () => screen.findByRole("table", { name: "Band results" }, { timeout: 10_000 });

describe("a run superseded by a newer input", () => {
  it("a run superseded by a newer input says 'restarted'", async () => {
    const bodies: Body[] = [];
    mount(bodies, 40, 100);
    await openUr0gt();
    markAll();
    await setBands();
    fireEvent.click(optimizeButton());
    await waitFor(() => expect(bodies).toHaveLength(1), { timeout: 5000 });
    await screen.findByLabelText("Band progress", undefined, { timeout: 5000 });
    // A genuine user change mid-run: unmark cap2 (a new free set).
    fireEvent.keyDown(knob("sy_cap2"), { key: "o" });
    await waitFor(() => expect(bodies).toHaveLength(2), { timeout: 5000 });
    expect((await screen.findAllByText(/restarted/, undefined, { timeout: 5000 })).length).toBeGreaterThan(0);
  });
});

describe("after a band run writes the knobs back", () => {
  it("the main readout is solved at the written-back values", async () => {
    const bodies: Body[] = [];
    mount(bodies);
    await openUr0gt();
    // Before: solved at cap1 = 340 pF -> R 34.00.
    await screen.findAllByText(/34\.00 Ω/, undefined, { timeout: 5000 });
    markAll();
    await setBands();
    fireEvent.click(optimizeButton());
    await finished();
    // After: the live solve at cap1 = 510 pF -> R 51.00, not the pre-run 34.00.
    await waitFor(() => expect(solves.at(-1)?.sy_cap1).toBe(510), { timeout: 5000 });
    await screen.findAllByText(/51\.00 Ω/, undefined, { timeout: 5000 });
    expect(screen.queryAllByText(/34\.00 Ω/)).toHaveLength(0);
  });
});

const toggle = () => optimizeButton().getAttribute("aria-pressed");
const bandsOf = (b: Body) => (b.optimize as { bands?: { freq: number }[] }).bands?.map((x) => x.freq);

describe("the gear menu pauses Optimize while its settings are edited", () => {
  it("Steve's sequence: Optimize on, then three band edits a second apart, is ONE run", async () => {
    const bodies: Body[] = [];
    mount(bodies);
    await openUr0gt();
    markAll();
    fireEvent.click(optimizeButton());
    await waitFor(() => expect(bodies).toHaveLength(1), { timeout: 5000 });
    await pause(2500); // the measurement-frequency run streams and settles
    const before = bodies.length;
    // Bands on, add 3.6, add 1.8 — a second apart, as on the hosted app.
    await setBands(1000);
    await finished();
    await pause(1500);
    // Before 0.97.1: [7.2], [7.2, 3.6], [7.2, 3.6, 1.8] — three runs.
    expect(bodies.slice(before).map(bandsOf)).toEqual([BANDS]);
    expect(toggle()).toBe("true");
  });

  it("opening the menu mid-run aborts it and turns Optimize off; closing resumes with one run", async () => {
    const bodies: Body[] = [];
    mount(bodies, 60, 100); // a 6 s run
    await openUr0gt();
    markAll();
    fireEvent.click(optimizeButton());
    await waitFor(() => expect(bodies).toHaveLength(1), { timeout: 5000 });
    await screen.findByText(/^#\d+ (worst )?SWR/, undefined, { timeout: 5000 });
    fireEvent.click(screen.getByLabelText("Optimisation method"));
    expect(aborted).toEqual([0]);
    expect(toggle()).toBe("false");
    expect(screen.getByRole("status").textContent).toBe("paused while editing optimize settings");
    // Edit everything the menu has, slowly: nothing runs while it is open.
    fireEvent.click(screen.getByRole("menuitemcheckbox", { name: /Several bands at once/ }));
    await pause(700);
    const add = screen.getByLabelText("Add a band, MHz");
    for (const f of BANDS.slice(1)) {
      fireEvent.change(add, { target: { value: String(f) } });
      fireEvent.keyDown(add, { key: "Enter" });
      await pause(700);
    }
    fireEvent.change(screen.getByLabelText("Balance between the worst band and the average"), {
      target: { value: "0.3" },
    });
    await pause(700);
    expect(bodies).toHaveLength(1);
    // Close: Optimize is back on, and exactly one run starts with the edits.
    fireEvent.click(screen.getByLabelText("Optimisation method"));
    expect(toggle()).toBe("true");
    await waitFor(() => expect(bodies).toHaveLength(2), { timeout: 5000 });
    await pause(1000);
    expect(bodies).toHaveLength(2);
    expect(bandsOf(bodies[1])).toEqual(BANDS);
    expect((bodies[1].optimize as { mean_weight: number }).mean_weight).toBe(0.3);
    expect(screen.queryByText(/restarted/)).toBeNull();
  });

  it("with Optimize off, opening, editing and closing the menu starts nothing", async () => {
    const bodies: Body[] = [];
    mount(bodies);
    await openUr0gt();
    markAll();
    await setBands(500);
    await pause(1000);
    expect(bodies).toHaveLength(0);
    expect(toggle()).toBe("false");
  });
});

describe("the Smith chart during and after a band run", () => {
  const smithBands = () =>
    [...document.querySelectorAll<HTMLCanvasElement>("canvas.smith")].map((c) => c.dataset.bands ?? "");

  it("shows one marker per band from the progress frames, and keeps them after the run", async () => {
    const bodies: Body[] = [];
    mount(bodies, 30, 80);
    await openUr0gt();
    expect(smithBands().length).toBeGreaterThan(0);
    markAll();
    await setBands();
    fireEvent.click(optimizeButton());
    // Mid-run: three bands, each with a trail, the worst (stub: band 0) marked.
    await waitFor(
      () => expect(smithBands()).toContainEqual(expect.stringMatching(/^7\.2:[2-6],3\.6:[2-6],1\.8:[2-6]\*$/)),
      { timeout: 5000 },
    );
    await finished();
    await pause(800);
    // After: the markers stay where the run left them (the write-back's solve
    // does not clear them).
    expect(smithBands()).toContainEqual("7.2:6,3.6:6,1.8:6*");
    // An edit clears them (Optimize off first, so the edit starts no run).
    fireEvent.click(optimizeButton());
    fireEvent.keyDown(knob("sy_w5hgt"), { key: "ArrowUp" });
    await waitFor(() => expect(smithBands().every((b) => b === "")).toBe(true), { timeout: 5000 });
    expect(bodies).toHaveLength(1);
  });
});
