// AK#2292: a design switch neither cancels nor forgets a running optimize.
// A run belongs to its design: switching to another and back shows its live
// progress, or its result table and trial count if it finished, and the
// result is written back to its own design's knobs, never the one on screen
// when it landed. Driven through the real session against a stubbed
// streaming /optimize. Every design, knob and value here is invented.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { invveeShape } from "./fixtures/solveShapes";
import {
  HARNESS_EXAMPLE,
  mountDesignSession,
  sessionReady,
  switchDesign,
} from "./designSessionHarness";

vi.setConfig({ testTimeout: 30_000 });

function knobSpec(name: string, value: number, lo: number, hi: number): SchemaParamSpec {
  return {
    name,
    label: name,
    default: value,
    kind: "float",
    min: lo,
    max: hi,
    step: 0.01,
    precision: 3,
    unit: null,
    visible_when: null,
    enum_options: null,
    range_from_enum_option: null,
    on_change_set: null,
    linked_to_design_freq: false,
    link_meas_freq_to_param: null,
    layout: null,
    description: null,
  } as unknown as SchemaParamSpec;
}

const TOWER: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  name: "verticals.tower_probe",
  label: "Tower probe",
  param_schema: [knobSpec("mast", 9, 5, 13), knobSpec("skirt", 4, 2, 6)],
};
const KNOBS = ["mast", "skirt"] as const;
const START: Record<string, number> = { mast: 9, skirt: 4 };
const AFTER: Record<string, number> = { mast: 10.25, skirt: 3.5 };
const BANDS = [7.1, 3.7];

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

const json = (body: unknown) =>
  ({ ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => body }) as unknown as Response;

const band = (index: number, freq: number, swr: number) => ({
  index,
  freq_mhz: freq,
  objective: "swr",
  feed: 0,
  z0_ohms: 50,
  z_re: 50 + 5 * swr,
  z_im: 10 * swr,
  swr,
  residual: null,
  value: swr,
});

function progressFrame(n: number, total: number): string {
  const t = n / total;
  const params = Object.fromEntries(KNOBS.map((k) => [k, START[k] + t * (AFTER[k] - START[k])]));
  const swrs = BANDS.map((_, i) => 6 - t * (4 - i));
  const worst = Math.max(...swrs);
  return (
    "event: progress\ndata: " +
    JSON.stringify({
      n_evals: n,
      n_solves: n,
      params,
      phase: "least squares",
      form: "minimax",
      bands: BANDS.map((f, i) => band(i, f, swrs[i])),
      objective: worst,
      objective_worst: worst,
      objective_mean: swrs.reduce((a, b) => a + b, 0) / swrs.length,
      mean_weight: 0.5,
      worst_band: swrs.indexOf(worst),
      metrics: { z_in_re: 40, z_in_im: -60, z0_ohms: 50, swr: worst },
      residual: null,
      solve_ms: 30,
    }) +
    "\n\n"
  );
}

const RESULT = {
  objective: "bands",
  form: "minimax",
  params: AFTER,
  params_before: START,
  bands_before: BANDS.map((f, i) => band(i, f, [5.5, 6.0][i])),
  bands_after: BANDS.map((f, i) => band(i, f, [1.4, 1.8][i])),
  objective_before: 6.0,
  objective_after: 1.8,
  objective_worst_before: 6.0,
  objective_worst_after: 1.8,
  objective_mean_before: 5.75,
  objective_mean_after: 1.6,
  mean_weight: 0.5,
  worst_swr_before: 6.0,
  worst_swr_after: 1.8,
  metrics_before: { z_in_re: 40, z_in_im: -60, z0_ohms: 50, swr: 6.0 },
  metrics_after: { z_in_re: 55, z_in_im: 12, z0_ohms: 50, swr: 1.8 },
  n_evals: 37,
  n_solves: 29,
  elapsed_s: 2.4,
  improved: true,
};

const aborted: number[] = [];

function streamingOptimize(bodies: Body[], frames: number, gapMs: number) {
  return (_u: string, init?: RequestInit) => {
    const n = bodies.length;
    bodies.push(JSON.parse(String(init?.body ?? "{}")) as Body);
    init?.signal?.addEventListener("abort", () => aborted.push(n));
    const enc = new TextEncoder();
    let timer: ReturnType<typeof setTimeout> | null = null;
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        let k = 0;
        const tick = () => {
          k += 1;
          if (k <= frames) {
            c.enqueue(enc.encode(progressFrame(k, frames)));
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

async function mount(bodies: Body[], frames: number, gapMs: number) {
  mountDesignSession({
    url: "/",
    examples: [HARNESS_EXAMPLE, TOWER],
    routes: {
      "/geometry": () => json({ wires: [] }),
      "/optimize": streamingOptimize(bodies, frames, gapMs),
    },
  });
  await sessionReady(document.body);
}

const user = () => userEvent.setup({ delay: null });
const toTower = () => switchDesign(user(), "Tower probe", TOWER.name);
const toProbe = () => switchDesign(user(), "Probe dipole", HARNESS_EXAMPLE.name);

const knob = (name: string) => screen.getByRole("slider", { name: new RegExp(`^${name}`) });
const optimizeButton = () => screen.getByRole("button", { name: /^Optimize/ });
const toggle = () => optimizeButton().getAttribute("aria-pressed");
const pause = (ms: number) =>
  act(async () => {
    await new Promise((r) => setTimeout(r, ms));
  });

async function startBandRun() {
  await toTower();
  for (const k of KNOBS) fireEvent.keyDown(knob(k), { key: "o" });
  fireEvent.click(screen.getByLabelText("Optimisation method"));
  fireEvent.click(screen.getByRole("menuitemcheckbox", { name: /Several bands at once/ }));
  const add = screen.getByLabelText("Add a band, MHz");
  fireEvent.change(add, { target: { value: String(BANDS[1]) } });
  fireEvent.keyDown(add, { key: "Enter" });
  // The design opens at 7.1 MHz, so the list starts with it.
  const list = screen.getByRole("list", { name: "Band frequencies" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  fireEvent.click(screen.getByLabelText("Optimisation method"));
  fireEvent.click(optimizeButton());
}

const progressEval = () => {
  const el = screen.queryByLabelText("Band progress");
  const m = el?.textContent?.match(/#(\d+)/);
  return m ? Number(m[1]) : null;
};
const finished = () => screen.findByRole("table", { name: "Band results" }, { timeout: 10_000 });

beforeEach(() => {
  aborted.length = 0;
  vi.stubGlobal("WebSocket", StubWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("a design switch keeps the design's optimize run (AK#2292)", () => {
  it("a run in flight keeps streaming while another design is shown, and shows its progress on return", async () => {
    const bodies: Body[] = [];
    await mount(bodies, 50, 80); // a 4 s run
    await startBandRun();
    await screen.findByLabelText("Band progress", undefined, { timeout: 5000 });
    const before = progressEval()!;
    await toProbe();
    // The other design has no run of its own and Optimize is off there.
    expect(screen.queryByLabelText("Band progress")).toBeNull();
    expect(toggle()).toBe("false");
    await pause(800);
    expect(aborted).toEqual([]);
    await toTower();
    // The same run, further along: not reset, not restarted.
    await waitFor(() => expect(progressEval()).toBeGreaterThan(before + 3), { timeout: 5000 });
    expect(toggle()).toBe("true");
    expect(screen.queryByText(/restarted/)).toBeNull();
    await finished();
    expect(screen.getByText(/37 trials \(29 solved\), 2\.4 s/)).toBeTruthy();
    expect(Number(knob("mast").getAttribute("aria-valuenow"))).toBeCloseTo(AFTER.mast, 3);
    expect({ requests: bodies.length, aborted }).toEqual({ requests: 1, aborted: [] });
  });

  it("a run that finishes while another design is shown is written back to its own knobs on return", async () => {
    const bodies: Body[] = [];
    await mount(bodies, 12, 60);
    await startBandRun();
    await screen.findByLabelText("Band progress", undefined, { timeout: 5000 });
    await toProbe();
    // Long enough for the whole run to finish off screen.
    await pause(1500);
    expect(screen.queryByRole("table", { name: "Band results" })).toBeNull();
    await toTower();
    await finished();
    expect(screen.getByText(/37 trials \(29 solved\), 2\.4 s/)).toBeTruthy();
    await waitFor(() =>
      expect(Number(knob("mast").getAttribute("aria-valuenow"))).toBeCloseTo(AFTER.mast, 3),
    );
    expect(Number(knob("skirt").getAttribute("aria-valuenow"))).toBeCloseTo(AFTER.skirt, 3);
    await pause(800);
    expect({ requests: bodies.length, aborted }).toEqual({ requests: 1, aborted: [] });
  });

  it("a finished result survives a design switch, with no new run", async () => {
    const bodies: Body[] = [];
    await mount(bodies, 8, 40);
    await startBandRun();
    await finished();
    await toProbe();
    expect(screen.queryByRole("table", { name: "Band results" })).toBeNull();
    await toTower();
    await finished();
    expect(screen.getByText(/37 trials \(29 solved\), 2\.4 s/)).toBeTruthy();
    await pause(800);
    expect(bodies).toHaveLength(1);
  });

  it("Optimize off after a round trip still stops the design's run", async () => {
    const bodies: Body[] = [];
    await mount(bodies, 60, 80);
    await startBandRun();
    await screen.findByLabelText("Band progress", undefined, { timeout: 5000 });
    await toProbe();
    await toTower();
    await screen.findByLabelText("Band progress", undefined, { timeout: 5000 });
    fireEvent.click(optimizeButton());
    expect(aborted).toEqual([0]);
    expect(toggle()).toBe("false");
  });
});
