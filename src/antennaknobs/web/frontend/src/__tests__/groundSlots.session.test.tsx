// AK#1794 — ground slots, the A/B/C solver slots' twin, end to end through a
// real <DesignSession>. Three stock slots (the design's own ground or the
// session default; free space; Sommerfeld over average soil), one click to
// switch, the ground panel editing the active one, and — the point of the
// feature — the next solve carrying the new ground. The solve goes out on the
// WebSocket, so this file swaps the harness's InertWebSocket for one that
// opens and records what it is sent: an assertion on the payload, not on the
// tab strip's state.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mountReady, switchDesign, HARNESS_EXAMPLE } from "./designSessionHarness";
import type { ExampleDescriptor } from "../lib/params";

class RecordingWebSocket {
  static OPEN = 1;
  static all: RecordingWebSocket[] = [];
  readyState = 0;
  sent: Record<string, unknown>[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    RecordingWebSocket.all.push(this);
    // The server accepts at once: open on the next task, as a browser would.
    setTimeout(() => {
      this.readyState = RecordingWebSocket.OPEN;
      this.onopen?.();
    }, 0);
  }
  send(payload: string) {
    this.sent.push(JSON.parse(payload) as Record<string, unknown>);
  }
  close() {}
}

/** Every solve request the session has sent so far. */
const solves = () =>
  RecordingWebSocket.all.flatMap((ws) => ws.sent).filter((m) => "geometry" in m);

/** Resolves with the first solve sent after `since` solves that satisfies
 *  `pred`. */
async function nextSolve(
  since: number,
  pred: (m: Record<string, unknown>) => boolean,
): Promise<Record<string, unknown>> {
  let hit: Record<string, unknown> | undefined;
  await vi.waitFor(
    () => {
      hit = solves().slice(since).find(pred);
      if (!hit) throw new Error(`no matching solve after #${since}`);
    },
    { timeout: 3000 },
  );
  return hit!;
}

const FREE: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  name: "user.freedeck",
  label: "Free deck",
  ground_seed: "free",
  fixed_segment_counts: true,
};
const GN2: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  name: "user.gn2deck",
  label: "GN 2 deck",
  ground_seed: "sommerfeld",
  ground_medium: { eps_r: 20, sigma: 0.02 },
  fixed_segment_counts: true,
};
const BURIED: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  name: "verticals.buried_probe",
  label: "Buried probe",
  ground_requirement: "sommerfeld",
};

const tab = (id: string) => screen.getByRole("tab", { name: new RegExp(`^Ground slot ${id}:`) });
const tabs = () => screen.getAllByRole("tab", { name: /^Ground slot / });
const selected = () => tabs().find((t) => t.getAttribute("aria-selected") === "true");
const groundBox = () =>
  screen.getByRole("checkbox", { name: /ground plane/ }) as HTMLInputElement;
const radio = (name: string | RegExp) =>
  (screen.getByRole("radio", { name }) as HTMLInputElement).checked;

beforeEach(() => {
  RecordingWebSocket.all = [];
  vi.stubGlobal("WebSocket", RecordingWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ground slots (AK#1794)", () => {
  it("offers the stock set beside the solver slots, slot 1 active", async () => {
    await mountReady();
    expect(tabs().map((t) => t.getAttribute("aria-label"))).toEqual([
      "Ground slot 1: refl-coef",
      "Ground slot 2: free space",
      "Ground slot 3: Sommerfeld",
    ]);
    expect(selected()).toBe(tab("1"));
    // Slot 1 is today's single ground: on, finite, refl-coef.
    expect(groundBox().checked).toBe(true);
    expect(radio(/refl-coef/)).toBe(true);
  });

  it("one click sends the new ground on the next solve", async () => {
    const user = userEvent.setup();
    await mountReady();
    const first = await nextSolve(0, () => true);
    expect(first).toMatchObject({ ground: true, ground_model: "fast", ground_fast: true });

    let n = solves().length;
    await user.click(tab("2"));
    expect(selected()).toBe(tab("2"));
    expect(groundBox().checked).toBe(false);
    expect(await nextSolve(n, (m) => m.ground === false)).toMatchObject({
      ground: false,
      ground_fast: false,
    });

    n = solves().length;
    await user.click(tab("3"));
    expect(radio("Sommerfeld")).toBe(true);
    expect(
      await nextSolve(n, (m) => m.ground === true && m.ground_model === "sommerfeld"),
    ).toMatchObject({ ground: true, ground_fast: false });

    // And back: slot 1 is still what it was.
    n = solves().length;
    await user.click(tab("1"));
    expect(await nextSolve(n, (m) => m.ground_model === "fast")).toMatchObject({
      ground: true,
    });
  });

  it("the ground panel edits the active slot only", async () => {
    const user = userEvent.setup();
    await mountReady();
    await user.click(tab("3"));
    await user.click(screen.getByRole("radio", { name: /PEC/ }));
    expect(tab("3").getAttribute("aria-label")).toBe("Ground slot 3: PEC");
    await user.click(tab("1"));
    expect(radio(/finite/)).toBe(true);
    expect(radio(/refl-coef/)).toBe(true);
    await user.click(tab("3"));
    expect(radio(/PEC/)).toBe(true);
  });

  it("a deck's own ground lands in slot 1, which opens active", async () => {
    await mountReady({ examples: [GN2] });
    expect(selected()).toBe(tab("1"));
    expect(tab("1").getAttribute("aria-label")).toBe(
      "Ground slot 1: Sommerfeld · εr 20, σ 0.02 S/m",
    );
    // The other slots keep their stock.
    expect(tab("2").getAttribute("aria-label")).toBe("Ground slot 2: free space");
    expect(tab("3").getAttribute("aria-label")).toBe("Ground slot 3: Sommerfeld");
    // The notice about the deck's ground is slot 1's, not free space's.
    expect(screen.getByText(/from the file: finite ground, Sommerfeld/)).toBeTruthy();
    await userEvent.setup().click(tab("2"));
    expect(screen.queryByText(/from the file:/)).toBeNull();
  });

  it("a design switch: the deck's ground takes slot 1 and the active slot; slots 2+ keep theirs", async () => {
    const user = userEvent.setup();
    await mountReady({ examples: [HARNESS_EXAMPLE, FREE] });
    await user.click(tab("3"));
    await user.click(screen.getByRole("radio", { name: /PEC/ }));

    const n = solves().length;
    await switchDesign(user, "Free deck", FREE.name);
    expect(selected()).toBe(tab("1"));
    expect(tab("1").getAttribute("aria-label")).toBe("Ground slot 1: free space");
    expect(tab("3").getAttribute("aria-label")).toBe("Ground slot 3: PEC");
    expect(
      await nextSolve(n, (m) => m.geometry === FREE.name && m.ground === false),
    ).toBeTruthy();

    // Back to a design with no ground of its own: slot 1 held only the
    // deck's ground, so the session default comes back.
    await switchDesign(user, "Probe dipole", HARNESS_EXAMPLE.name);
    expect(tab("1").getAttribute("aria-label")).toBe("Ground slot 1: refl-coef");
    expect(tab("3").getAttribute("aria-label")).toBe("Ground slot 3: PEC");
  });

  it("a design with no ground of its own keeps the active slot and a hand-edited slot 1", async () => {
    const user = userEvent.setup();
    const OTHER = { ...HARNESS_EXAMPLE, name: "dipoles.other", label: "Other dipole" };
    await mountReady({ examples: [HARNESS_EXAMPLE, OTHER] });
    await user.click(screen.getByRole("radio", { name: "Sommerfeld" }));
    await user.click(tab("2"));
    await switchDesign(user, "Other dipole", OTHER.name);
    expect(selected()).toBe(tab("2"));
    expect(tab("1").getAttribute("aria-label")).toBe("Ground slot 1: Sommerfeld");
  });

  it("a buried design on the free-space slot sends what unticking the ground did", async () => {
    // The refusal is the solver's, by name, on the request; the slot must
    // send exactly the request the single ground sent with the box unticked.
    const user = userEvent.setup();
    await mountReady({ examples: [BURIED] });
    expect(radio("Sommerfeld")).toBe(true);
    expect(screen.getByText(/buried design — Sommerfeld ground selected/)).toBeTruthy();

    let n = solves().length;
    await user.click(groundBox());
    const unticked = await nextSolve(n, (m) => m.ground === false);
    await user.click(groundBox());
    await nextSolve(n, (m) => m.ground === true);

    n = solves().length;
    await user.click(tab("2"));
    const slot2 = await nextSolve(n, (m) => m.ground === false);
    // The two differ only in `ground_model`, the finite method each slot
    // parks, which the server reads only while `ground` is true
    // (adapter._requested_ground_model); every ground field it does read is
    // equal.
    for (const key of ["ground", "ground_fast", "soil", "terrain"]) {
      expect(slot2[key]).toEqual(unticked[key]);
    }
    expect(screen.queryByText(/buried design — Sommerfeld ground selected/)).toBeNull();
  });

  it("renders however many slots the settings file has", async () => {
    const g = { enabled: true, type: "finite", method: "fast", soil: null, terrain_preset: null };
    await mountReady({
      uiDefaults: {
        switches: {},
        ground: g,
        grounds: [
          { id: "1", ...g },
          { id: "2", ...g, enabled: false },
          { id: "3", ...g, method: "sommerfeld" },
          { id: "4", ...g, type: "pec" },
        ],
        problems: [],
      },
    });
    expect(tabs().map((t) => t.getAttribute("aria-label"))).toEqual([
      "Ground slot 1: refl-coef",
      "Ground slot 2: free space",
      "Ground slot 3: Sommerfeld",
      "Ground slot 4: PEC",
    ]);
  });
});
