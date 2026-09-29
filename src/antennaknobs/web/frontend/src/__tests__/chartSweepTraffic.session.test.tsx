// The default workbench's /sweep traffic (AK#1757 step 5 unit 3). Folding the
// standalone Smith view and its freq-sweep checkbox into the analysis chart
// must not change what a fresh session asks the server for: the default
// chart (a frequency sweep on the Smith chart, pinned where the Smith view
// was) sends exactly the requests the Smith view with the checkbox on sent —
// one base sweep over the session's range, the refinement rounds its locus
// earns, and after a knob change one more base sweep once the dwell passes.
// Never a second runner's copy (unit 2's follow-up: a leftover standalone
// runner would double every base sweep).
//
// EXPECTED below was recorded by running this file, unchanged, on the
// integration branch before unit 3 (56f1c33b6), where the default pinned set
// held the standalone Smith view with the checkbox on (its built-in
// default). Mutation (run by hand, 2026-09-28): a second runner sweeping the
// chart's range alongside the session's (unit 2's chartFreq, re-enabled for
// the default chart) doubles every base request and fails here.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import type { ExampleDescriptor } from "../lib/params";
import { invveeShape } from "./fixtures/solveShapes";
import { HARNESS_EXAMPLE, mountReady, untilDom } from "./designSessionHarness";

vi.setConfig({ testTimeout: 20_000 });

const DESIGN: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  param_schema: [
    {
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
    },
  ],
};

// Every solve answered at once, Z moving with the Gap knob.
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
    const gap = typeof req.gap === "number" ? req.gap : 0.25;
    const reply = {
      ...invveeShape,
      feeds: undefined,
      geometry: req.geometry,
      _seq: req._seq,
      z_in_re: 40 + 40 * gap,
      z_in_im: -10,
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

type Sent = { refine: boolean; n: number; lo: string; hi: string };

beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

// The locus: a resonance near the design frequency, so refinement has a
// bend to dig into.
const z = (f: number, f0: number) => ({ re: 50 + 400 * (f / f0 - 1) ** 2, im: 300 * (f / f0 - 1) });

describe("the default workbench's /sweep traffic", () => {
  it("is the Smith view's with its freq-sweep switch on: one base sweep, its refinement, one more after a knob", async () => {
    const sent: Sent[] = [];
    let f0 = 0;
    await mountReady({
      examples: [DESIGN],
      routes: {
        "/sweep": (_url: string, init?: RequestInit) => {
          const body = JSON.parse(String(init?.body ?? "{}"));
          const freqs = body.freqs_mhz as number[];
          if (!f0) f0 = (freqs[0] + freqs[freqs.length - 1]) / 2;
          sent.push({
            refine: !!body._refine,
            n: freqs.length,
            lo: freqs[0].toFixed(4),
            hi: freqs[freqs.length - 1].toFixed(4),
          });
          const lines = freqs.map((f) => {
            const p = z(f, f0);
            return JSON.stringify({ freq_mhz: f, z_re: p.re, z_im: p.im });
          });
          lines.push(JSON.stringify({ done: true }));
          return ndjson(lines);
        },
      },
    });
    // The rail's Smith chart (the default pinned set's fourth): its runner
    // idle means the base sweep and every refinement round are done.
    const smith = () => document.querySelector<HTMLElement>(".thumbstrip canvas.smith");
    await untilDom(() => sent.length > 0 || null);
    await untilDom(() => (smith()?.dataset.phase === "idle" && sent.length > 0) || null);
    const opening = sent.slice();

    fireEvent.keyDown(screen.getByRole("slider", { name: "Gap" }), { key: "ArrowUp" });
    // The runner decided inside the change's act: one sweep, queued.
    expect(smith()!.dataset.phase).toBe("queued");
    await untilDom(() => sent.length > opening.length || null);
    await untilDom(() => smith()?.dataset.phase === "idle" || null);
    const afterKnob = sent.slice(opening.length);

    expect({ opening, afterKnob }).toEqual(EXPECTED);
    // The shape, spelled out: each burst is one base sweep, then only
    // refinement rounds.
    for (const burst of [opening, afterKnob]) {
      expect(burst[0].refine).toBe(false);
      expect(burst.slice(1).every((s) => s.refine)).toBe(true);
    }
  });
});

// Recorded on 56f1c33b6 (the standalone Smith view, its switch on): the
// base grid is 17 log points over the policy's 0.8–1.25 × design frequency
// (adaptive resolution on), and the locus earns one refinement round of 12.
const BURST: Sent[] = [
  { refine: false, n: 17, lo: "11.4400", hi: "17.8750" },
  { refine: true, n: 12, lo: "12.9712", hi: "17.6292" },
];
const EXPECTED = { opening: BURST, afterKnob: BURST };
