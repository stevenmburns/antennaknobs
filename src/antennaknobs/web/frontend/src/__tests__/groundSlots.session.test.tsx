// AK#1794 — ground slots, the A/B/C solver slots' twin, end to end through a
// real <DesignSession>. Three stock slots (the design's own ground or the
// session default, Sommerfeld; free space; refl-coef over average soil), one click to
// switch, the ground panel editing the active one, and — the point of the
// feature — the next solve carrying the new ground. The solve goes out on the
// WebSocket, so this file swaps the harness's InertWebSocket for one that
// opens and records what it is sent: an assertion on the payload, not on the
// tab strip's state.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mountReady, switchDesign, HARNESS_EXAMPLE, groundSettings } from "./designSessionHarness";
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
// What each tab reads as its name (AK#1801): the slot's letter.
const letters = () => tabs().map((t) => within(t).getByText(/^[A-Z]$/).textContent);
const selected = () => tabs().find((t) => t.getAttribute("aria-selected") === "true");
const groundBox = () =>
  within(groundSettings()).getByRole("checkbox", { name: /ground plane/ }) as HTMLInputElement;
const radio = (name: string | RegExp) =>
  (within(groundSettings()).getByRole("radio", { name }) as HTMLInputElement).checked;

beforeEach(() => {
  RecordingWebSocket.all = [];
  vi.stubGlobal("WebSocket", RecordingWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ground slots (AK#1794)", () => {
  it("offers the stock set beside the solver slots, slot X active", async () => {
    await mountReady();
    expect(tabs().map((t) => t.getAttribute("aria-label"))).toEqual([
      "Ground slot X: Sommerfeld",
      "Ground slot Y: free space",
      "Ground slot Z: refl-coef",
    ]);
    // The tabs read X, Y, Z (AK#1801), their own family beside A, B, C.
    expect(letters()).toEqual(["X", "Y", "Z"]);
    expect(selected()).toBe(tab("X"));
    // Slot X is the session's default ground: on, finite, Sommerfeld
    // (AK#1856; it was refl-coef).
    expect(groundBox().checked).toBe(true);
    expect(radio("Sommerfeld")).toBe(true);
  });

  it("one click sends the new ground on the next solve", async () => {
    const user = userEvent.setup();
    await mountReady();
    const first = await nextSolve(0, () => true);
    expect(first).toMatchObject({ ground: true, ground_model: "sommerfeld", ground_fast: false });

    let n = solves().length;
    await user.click(tab("Y"));
    expect(selected()).toBe(tab("Y"));
    expect(groundBox().checked).toBe(false);
    expect(await nextSolve(n, (m) => m.ground === false)).toMatchObject({
      ground: false,
      ground_fast: false,
    });

    n = solves().length;
    await user.click(tab("Z"));
    expect(radio(/refl-coef/)).toBe(true);
    expect(
      await nextSolve(n, (m) => m.ground === true && m.ground_model === "fast"),
    ).toMatchObject({ ground: true, ground_fast: true });

    // And back: slot X is still what it was.
    n = solves().length;
    await user.click(tab("X"));
    expect(await nextSolve(n, (m) => m.ground_model === "sommerfeld")).toMatchObject({
      ground: true,
    });
  });

  it("the ground panel edits the active slot only", async () => {
    const user = userEvent.setup();
    await mountReady();
    await user.click(tab("Z"));
    await user.click(within(groundSettings()).getByRole("radio", { name: /PEC/ }));
    expect(tab("Z").getAttribute("aria-label")).toBe("Ground slot Z: PEC");
    await user.click(tab("X"));
    expect(radio(/finite/)).toBe(true);
    expect(radio("Sommerfeld")).toBe(true);
    await user.click(tab("Z"));
    expect(radio(/PEC/)).toBe(true);
  });

  it("a deck's own ground lands in slot X, which opens active", async () => {
    await mountReady({ examples: [GN2] });
    expect(selected()).toBe(tab("X"));
    expect(tab("X").getAttribute("aria-label")).toBe(
      "Ground slot X: Sommerfeld · εr 20, σ 0.02 S/m",
    );
    // The other slots keep their stock.
    expect(tab("Y").getAttribute("aria-label")).toBe("Ground slot Y: free space");
    expect(tab("Z").getAttribute("aria-label")).toBe("Ground slot Z: refl-coef");
    // The notice about the deck's ground is slot X's, not free space's.
    expect(screen.getByText(/from the file: finite ground, Sommerfeld/)).toBeTruthy();
    await userEvent.setup().click(tab("Y"));
    expect(screen.queryByText(/from the file:/)).toBeNull();
  });

  it("a design switch: the deck's ground takes slot X and the active slot; slots Y, Z keep theirs", async () => {
    const user = userEvent.setup();
    await mountReady({ examples: [HARNESS_EXAMPLE, FREE] });
    await user.click(tab("Z"));
    await user.click(within(groundSettings()).getByRole("radio", { name: /PEC/ }));

    const n = solves().length;
    await switchDesign(user, "Free deck", FREE.name);
    expect(selected()).toBe(tab("X"));
    expect(tab("X").getAttribute("aria-label")).toBe("Ground slot X: free space");
    expect(tab("Z").getAttribute("aria-label")).toBe("Ground slot Z: PEC");
    expect(
      await nextSolve(n, (m) => m.geometry === FREE.name && m.ground === false),
    ).toBeTruthy();

    // Back to a design with no ground of its own: slot X held only the
    // deck's ground, so the session default comes back.
    await switchDesign(user, "Probe dipole", HARNESS_EXAMPLE.name);
    expect(tab("X").getAttribute("aria-label")).toBe("Ground slot X: Sommerfeld");
    expect(tab("Z").getAttribute("aria-label")).toBe("Ground slot Z: PEC");
  });

  it("a design with no ground of its own keeps the active slot and a hand-edited slot X", async () => {
    const user = userEvent.setup();
    const OTHER = { ...HARNESS_EXAMPLE, name: "dipoles.other", label: "Other dipole" };
    await mountReady({ examples: [HARNESS_EXAMPLE, OTHER] });
    // A hand edit away from the default (Sommerfeld since AK#1856).
    await user.click(within(groundSettings()).getByRole("radio", { name: /refl-coef/ }));
    await user.click(tab("Y"));
    await switchDesign(user, "Other dipole", OTHER.name);
    expect(selected()).toBe(tab("Y"));
    expect(tab("X").getAttribute("aria-label")).toBe("Ground slot X: refl-coef");
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
    await user.click(tab("Y"));
    const slot2 = await nextSolve(n, (m) => m.ground === false);
    // The two differ only in `ground_model`, the finite method each slot
    // parks, which the server reads only while `ground` is true
    // (adapter._requested_ground_model); every ground field it does read is
    // equal.
    for (const key of ["ground", "ground_fast", "soil", "terrain"]) {
      expect(slot2[key]).toEqual(unticked[key]);
    }
    // The notice line under the tab strip is the active slot's: slot Y has
    // none. (Slot X's own settings, still open from the clicks above, keep
    // theirs: they are slot X's.)
    expect(screen.queryByLabelText("Ground notices")).toBeNull();
    expect(within(groundSettings("X")).getByText(/buried design — Sommerfeld ground selected/)).toBeTruthy();
  });

  it("renders however many slots the settings file has", async () => {
    const g = { enabled: true, type: "finite", method: "fast", soil: null, terrain_preset: null };
    await mountReady({
      uiDefaults: {
        grounds: [
          { id: "X", ...g },
          { id: "Y", ...g, enabled: false },
          { id: "Z", ...g, method: "sommerfeld" },
          { id: "U", ...g, type: "pec" },
        ],
      },
    });
    expect(tabs().map((t) => t.getAttribute("aria-label"))).toEqual([
      "Ground slot X: refl-coef",
      "Ground slot Y: free space",
      "Ground slot Z: Sommerfeld",
      "Ground slot U: PEC",
    ]);
  });
});
