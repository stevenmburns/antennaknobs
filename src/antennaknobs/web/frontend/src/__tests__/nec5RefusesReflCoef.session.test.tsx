// AK#1856 part 2 through a real <DesignSession>: NEC-5 has no
// reflection-coefficient ground, so the workbench refuses NEC-5 on a
// refl-coef slot, in the roster's served sentence, as the CLI refuses
// `--engine nec5 --ground finite-fast`, instead of solving it as Sommerfeld.
//
//  - the active pair NEC-5 x refl-coef sends no solve, says why on the pair
//    line and over the stage, and one click moves to the Sommerfeld slot,
//    which solves;
//  - NEC-5 on the Sommerfeld slot solves as it always did;
//  - a chart crossing NEC-5 with the refl-coef slot names that cell refused
//    in its legend and sends no sweep for it, and draws the rest.
//
// The socket here answers nothing; it records what the session sends, which
// is the claim: a refused pair is never sent, and the way out is.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ExampleDescriptor } from "../lib/params";
import { HARNESS_EXAMPLE, mountReady, untilDom } from "./designSessionHarness";
import { NEC5_REFL_COEF_REFUSAL, ROSTER_WITH_NEC5, SERVED_SLOT_SEEDS } from "./backendFixtures";
import { SERVED_UI_DEFAULTS } from "./uiDefaultsFixtures";

vi.setConfig({ testTimeout: 30_000 });

// Slot C holds NEC-5 (the served roster carries its row on a NEC-5 machine).
const SEEDS = SERVED_SLOT_SEEDS.map((s) =>
  s.slot === "C" ? { ...s, backend: "nec5", n_per_wire: null, model: {} } : s,
);

type Sent = Record<string, unknown>;
const sent: Sent[] = [];

class RecordingWebSocket {
  static OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    setTimeout(() => {
      this.readyState = RecordingWebSocket.OPEN;
      this.onopen?.();
    }, 0);
  }
  send(payload: string) {
    const req = JSON.parse(payload) as Sent;
    if ("geometry" in req && typeof req._seq === "number") sent.push(req);
  }
  close() {}
}

const pairLine = () => screen.getByTestId("solve-pair").textContent;
const groundTab = (id: string) =>
  screen.getByRole("tab", { name: new RegExp(`^Ground slot ${id}:`) });
const solverTab = (id: string) =>
  screen.getByRole("tab", { name: new RegExp(`^Solver slot ${id}:`) });
const overlay = () => screen.queryByRole("alertdialog", { name: "Ground refused by this solver" });
const solved = (solver: string, ground_model: string) =>
  untilDom(() => sent.find((r) => r.solver === solver && r.ground_model === ground_model) ?? null);

beforeEach(() => {
  sent.length = 0;
  vi.stubGlobal("WebSocket", RecordingWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("NEC-5 on a refl-coef ground slot (AK#1856)", () => {
  it("is refused with the served sentence, and one click solves on the Sommerfeld slot", async () => {
    const user = userEvent.setup();
    await mountReady({ roster: ROSTER_WITH_NEC5, slotSeeds: SEEDS });
    await solved("momwire", "sommerfeld");

    // NEC-5 on slot X, Sommerfeld: unchanged, it solves.
    await user.click(solverTab("C"));
    await solved("nec5", "sommerfeld");
    expect(pairLine()).toMatch(/^solving on C \(NEC-5\) × X \(Sommerfeld/);
    expect(screen.queryByTestId("solve-pair-refusal")).toBeNull();
    expect(overlay()).toBeNull();

    // Onto slot Z, refl-coef: refused by name, and nothing is sent.
    const before = sent.length;
    await user.click(groundTab("Z"));
    expect(pairLine()).toMatch(/^refused: C \(NEC-5\) × Z \(refl-coef ⊘/);
    const line = screen.getByTestId("solve-pair-refusal");
    expect(line.textContent).toContain(NEC5_REFL_COEF_REFUSAL);
    const shown = await untilDom(overlay);
    expect(shown.textContent).toContain(NEC5_REFL_COEF_REFUSAL);
    // No override: the server refuses the pair, so "Solve anyway" would buy
    // an error, not a result.
    expect(within(shown).queryByRole("button", { name: "Solve anyway" })).toBeNull();
    // A frame for a send to have gone out, had one been scheduled.
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    expect(sent.slice(before).some((r) => r.ground_model === "fast")).toBe(false);
    expect(sent.length).toBe(before);

    // The way out: the first Sommerfeld slot, X, which solves.
    await user.click(within(line).getByRole("button", { name: "Switch to ground X (Sommerfeld)" }));
    expect(groundTab("X").getAttribute("aria-selected")).toBe("true");
    expect(pairLine()).toMatch(/^solving on C \(NEC-5\) × X \(Sommerfeld/);
    expect(screen.queryByTestId("solve-pair-refusal")).toBeNull();
    expect(overlay()).toBeNull();
    await untilDom(() => (sent.length > before ? true : null));
    const after = sent.slice(before);
    expect(after.every((r) => r.solver === "nec5" && r.ground_model === "sommerfeld")).toBe(true);
  });

  it("the overlay's button is the same way out", async () => {
    const user = userEvent.setup();
    await mountReady({ roster: ROSTER_WITH_NEC5, slotSeeds: SEEDS });
    await user.click(solverTab("C"));
    await user.click(groundTab("Z"));
    const shown = await untilDom(overlay);
    await user.click(within(shown).getByRole("button", { name: "Switch to ground X (Sommerfeld)" }));
    expect(groundTab("X").getAttribute("aria-selected")).toBe("true");
    await solved("nec5", "sommerfeld");
  });

  it("with no Sommerfeld slot, the way out solves the active slot as Sommerfeld", async () => {
    const user = userEvent.setup();
    // Slot X turned to refl-coef too: no slot holds Sommerfeld.
    await mountReady({
      roster: ROSTER_WITH_NEC5,
      slotSeeds: SEEDS,
      uiDefaults: {
        grounds: SERVED_UI_DEFAULTS.grounds.map((g) => (g.id === "X" ? { ...g, method: "fast" } : g)),
      },
    });
    await user.click(solverTab("C"));
    const line = await untilDom(() => screen.queryByTestId("solve-pair-refusal"));
    expect(pairLine()).toMatch(/^refused: C \(NEC-5\) × X \(refl-coef ⊘/);
    await user.click(within(line).getByRole("button", { name: "Solve ground X as Sommerfeld" }));
    expect(groundTab("X").getAttribute("aria-label")).toMatch(/^Ground slot X: Sommerfeld/);
    expect(groundTab("Z").getAttribute("aria-label")).toMatch(/^Ground slot Z: refl-coef ⊘/);
    await solved("nec5", "sommerfeld");
  });
});

// An engine cross on the chart: slots A (B-spline) and C (NEC-5) on grounds
// X (Sommerfeld) and Z (refl-coef). Three curves draw; C x Z is a refused
// cell in the legend, in the served sentence, and is never swept.
const DECK: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  bands: [
    { key: "14.175 MHz", label: "14.175 MHz", freq_mhz: 14.175, min_mhz: 14, max_mhz: 14.35 },
  ],
  default_freq: 14.175,
  has_design_freq: false,
  meas_freq_range_mhz: [14, 14.35],
  sweep_range: { lo: 14, hi: 14.35, spacing: "lin", step: 0.025, source: "file" },
};

type Body = Record<string, unknown> & { freqs_mhz: number[] };

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

describe("a chart crossing NEC-5 with a refl-coef slot (AK#1856)", () => {
  it("names that cell refused in the legend, sweeps the rest, and never sweeps it", async () => {
    const bodies: Body[] = [];
    const r = await mountReady({
      roster: ROSTER_WITH_NEC5,
      slotSeeds: SEEDS,
      examples: [DECK],
      pinned: ["antenna", "zparam"],
      // Refinement off, so every /sweep is a base sweep.
      uiDefaults: { switches: { refine: false } },
      routes: {
        "/sweep": (_url: string, init?: RequestInit) => {
          const body = JSON.parse(String(init?.body ?? "{}")) as Body;
          bodies.push(body);
          const lines = body.freqs_mhz.map((f) =>
            JSON.stringify({ freq_mhz: f, z_re: 50 + 100 * Math.abs(f - 14.2), z_im: 0 }),
          );
          lines.push(JSON.stringify({ done: true }));
          return ndjson(lines);
        },
        "/analyses": () =>
          ({
            ok: true,
            status: 200,
            json: async () => ({ geometry: DECK.name, analyses: [] }),
          }) as unknown as Response,
      },
    });
    fireEvent.click(r.container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
    await untilDom(() => screen.queryByRole("button", { name: "Engines and grounds" }));
    await untilDom(() => bodies.find((b) => b._stream === undefined) ?? null);

    fireEvent.click(screen.getAllByRole("button", { name: "Engines and grounds" })[0]);
    const dlg = screen.getByRole("dialog", { name: "Engines and grounds" });
    const box = (prefix: string) => {
      const c = within(dlg)
        .getAllByRole("checkbox")
        .find((x) => x.closest("label")?.textContent?.startsWith(prefix));
      if (!c) throw new Error(`no box ${prefix}`);
      return c;
    };
    fireEvent.click(box("C: "));
    fireEvent.click(box("Z: "));

    const legend = await untilDom(() => {
      const l = document.querySelector<HTMLElement>(".chart-legend");
      return l?.querySelector('[data-refused="1"]') ? l : null;
    });
    await untilDom(() => (["c0r1", "c0r2"].every((s) => bodies.some((b) => b._stream === s)) ? true : null));
    const refused = [...legend.querySelectorAll<HTMLElement>('.chart-legend-row[data-refused="1"]')];
    expect(refused).toHaveLength(1);
    expect(refused[0].textContent).toMatch(/^C: NEC-5, Z: refl-coef/);
    expect(refused[0].textContent).toContain(NEC5_REFL_COEF_REFUSAL);
    expect(legend.dataset.curves).toBe("3");
    // NEC-5 is swept on X only; refl-coef only on B-spline.
    expect(bodies.some((b) => b.solver === "nec5" && b.ground_model === "fast")).toBe(false);
    expect(bodies.some((b) => b.solver === "nec5" && b.ground_model === "sommerfeld")).toBe(true);
    expect(bodies.some((b) => b.solver === "momwire" && b.ground_model === "fast")).toBe(true);
    // A refused pair is the legend's refused cell, not a mixed-ground note.
    expect(legend.querySelector('[role="note"]')).toBeNull();
  });
});
