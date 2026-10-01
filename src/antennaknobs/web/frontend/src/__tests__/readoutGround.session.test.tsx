// AK#1796: the readout's R / X never show a previous ground's solve. With a
// pattern view (Azimuth) as the main view, a ground change updated the
// readout's radiated % while R / X kept the last ground's numbers, which
// read as current. The readout now shows impedance only for a result solved
// for the ground (and engine) the controls ask for now, and "—" until that
// solve lands, whichever view is the main one.
//
// The socket here answers every solve with an impedance that depends on the
// request's ground, and can HOLD its answers, which is the window the bug
// lived in: the ground changed, its solve not back yet.
//
// Mutation (run by hand, 2026-09-29): handing the readouts `shownResult`
// again instead of `readoutResult` fails both tests at the held step (the
// previous ground's 48.78 Ω still shows).
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { invveeShape } from "./fixtures/solveShapes";
import { HARNESS_EXAMPLE, mountReady, untilDom } from "./designSessionHarness";

vi.setConfig({ testTimeout: 20_000 });

class GroundWebSocket {
  static OPEN = 1;
  static hold = false;
  static held: (() => void)[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    setTimeout(() => {
      this.readyState = GroundWebSocket.OPEN;
      this.onopen?.();
    }, 0);
  }
  send(payload: string) {
    const req = JSON.parse(payload) as Record<string, unknown>;
    if (!("geometry" in req) || typeof req._seq !== "number") return;
    // Over ground 48.78 Ω, in free space 55.10 Ω (the invvee's numbers).
    const grounded = req.ground === true;
    const reply = {
      ...invveeShape,
      feeds: undefined,
      geometry: req.geometry,
      _seq: req._seq,
      z_in_re: grounded ? 48.78 : 55.1,
      z_in_im: grounded ? -8.64 : -10.22,
      z0_ohms: 50,
    };
    const deliver = () => this.onmessage?.({ data: JSON.stringify(reply) } as MessageEvent);
    if (GroundWebSocket.hold) GroundWebSocket.held.push(deliver);
    else setTimeout(deliver, 0);
  }
  close() {}
  static release() {
    GroundWebSocket.hold = false;
    const all = GroundWebSocket.held.splice(0);
    all.forEach((d) => d());
  }
}

beforeEach(() => {
  GroundWebSocket.hold = false;
  GroundWebSocket.held = [];
  vi.stubGlobal("WebSocket", GroundWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

// The main stage's readout card, as one line of text.
const readout = () =>
  (document.querySelector<HTMLElement>(".stage-readout")?.textContent ?? "").replace(/\s+/g, " ");
// The readout's R value: the text between "R" and "X".
const rValue = () => /R\s*(.*?)\s*X/.exec(readout())?.[1] ?? null;

const groundTab = (id: string) =>
  screen
    .getAllByRole("tab")
    .find((t) => (t.getAttribute("aria-label") ?? "").startsWith(`Ground slot ${id}:`))!;

async function toAzimuth(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByTitle("Switch to Azimuth (xy)"));
  await untilDom(() => screen.queryByTitle("Switch to Antenna") ?? null);
}

describe("the readout's R / X follow the active ground on a pattern view (AK#1796)", () => {
  it("Antenna → Azimuth → change ground: never the previous ground's R, then the new one", async () => {
    const user = userEvent.setup();
    await mountReady({ examples: [HARNESS_EXAMPLE] });
    // Slot X (the session default: finite ground) solved on the Antenna view.
    expect(groundTab("X").getAttribute("aria-selected")).toBe("true");
    await untilDom(() => rValue()?.includes("48.78") || null);

    await toAzimuth(user);
    expect(rValue()).toContain("48.78");

    // Free space: its solve is held, so the result on screen is still the
    // finite ground's.
    GroundWebSocket.hold = true;
    await user.click(groundTab("Y"));
    await vi.waitFor(() => expect(GroundWebSocket.held.length).toBeGreaterThan(0));
    expect(groundTab("Y").getAttribute("aria-selected")).toBe("true");
    expect(rValue()).not.toContain("48.78");
    expect(rValue()).toBe("—");

    GroundWebSocket.release();
    await untilDom(() => rValue()?.includes("55.10") || null);

    // And back: the free-space number goes the moment the ground changes.
    GroundWebSocket.hold = true;
    await user.click(groundTab("X"));
    await vi.waitFor(() => expect(GroundWebSocket.held.length).toBeGreaterThan(0));
    expect(rValue()).toBe("—");
    GroundWebSocket.release();
    await untilDom(() => rValue()?.includes("48.78") || null);
  });

  it("Azimuth before the first solve lands: the readout fills in with the current ground's R", async () => {
    const user = userEvent.setup();
    GroundWebSocket.hold = true;
    await mountReady({ examples: [HARNESS_EXAMPLE] });
    await toAzimuth(user);
    await vi.waitFor(() => expect(GroundWebSocket.held.length).toBeGreaterThan(0));
    expect(rValue()).toBe("—");
    GroundWebSocket.release();
    await untilDom(() => rValue()?.includes("48.78") || null);

    // A ground change straight on the pattern view, its solve held.
    GroundWebSocket.hold = true;
    await user.click(groundTab("Y"));
    await vi.waitFor(() => expect(GroundWebSocket.held.length).toBeGreaterThan(0));
    expect(rValue()).toBe("—");
    GroundWebSocket.release();
    await untilDom(() => rValue()?.includes("55.10") || null);
  });
});
