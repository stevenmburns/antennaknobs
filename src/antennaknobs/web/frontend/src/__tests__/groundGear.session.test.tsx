// AK#1801 (the "Proposed" section): each ground-slot tab has a ⚙, like the
// solver tabs, that opens THAT slot's ground settings (the ground panel's
// controls) whether or not it is the active slot. The input pane keeps the
// tab strip and, when they apply to the active slot, the notices under it;
// the expanded panel no longer sits there. Layout only: what a slot holds and
// what a solve carries are unchanged, so the payload assertions below are
// the ground-slot tests' own (groundSlots.session.test.tsx).
//
// Mutation (run by hand, 2026-09-29): pointing a slot's ⚙ setters at the
// ACTIVE slot (useGroundConfig's slotSettings editing through editActive)
// fails "editing slot 2 while slot 1 is active changes slot 2 only".
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HARNESS_EXAMPLE, mountReady } from "./designSessionHarness";
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

const solves = () =>
  RecordingWebSocket.all.flatMap((ws) => ws.sent).filter((m) => "geometry" in m);

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

const BURIED: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  name: "verticals.buried_probe",
  label: "Buried probe",
  ground_requirement: "sommerfeld",
};

const tab = (id: string) => screen.getByRole("tab", { name: new RegExp(`^Ground slot ${id}:`) });
const gear = (id: string) => screen.getByRole("button", { name: `Ground slot ${id} settings` });
const dialog = () => screen.queryByRole("dialog", { name: /^Ground slot .* settings$/ });
const checked = (root: HTMLElement, role: "radio" | "checkbox", name: string | RegExp) =>
  (within(root).getByRole(role, { name }) as HTMLInputElement).checked;

beforeEach(() => {
  RecordingWebSocket.all = [];
  vi.stubGlobal("WebSocket", RecordingWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ground settings behind each ground slot's ⚙ (AK#1801)", () => {
  it("the input pane holds the tab strip, not the expanded panel", async () => {
    await mountReady();
    expect(screen.getAllByRole("tab", { name: /^Ground slot / })).toHaveLength(3);
    for (const id of ["1", "2", "3"]) expect(gear(id)).toBeTruthy();
    expect(screen.queryByRole("checkbox", { name: /ground plane/ })).toBeNull();
    expect(screen.queryByRole("radiogroup", { name: "Ground type" })).toBeNull();
    expect(dialog()).toBeNull();
  });

  it("the ⚙ opens the right slot's settings", async () => {
    const user = userEvent.setup();
    await mountReady();
    await user.click(gear("3"));
    let d = dialog()!;
    expect(d.getAttribute("aria-label")).toBe("Ground slot 3 settings");
    expect(d.textContent).toContain("Ground slot 3 — Sommerfeld");
    expect(checked(d, "checkbox", /ground plane/)).toBe(true);
    expect(checked(d, "radio", "Sommerfeld")).toBe(true);
    // Opening it switched nothing: slot 1 is still the active one.
    expect(tab("1").getAttribute("aria-selected")).toBe("true");

    await user.click(within(d).getByRole("button", { name: "Close" }));
    expect(dialog()).toBeNull();
    await user.click(gear("2"));
    d = dialog()!;
    expect(d.getAttribute("aria-label")).toBe("Ground slot 2 settings");
    expect(checked(d, "checkbox", /ground plane/)).toBe(false);

    await user.keyboard("{Escape}");
    expect(dialog()).toBeNull();
  });

  it("editing slot 2 while slot 1 is active changes slot 2 only; the solve follows the active slot", async () => {
    const user = userEvent.setup();
    await mountReady();
    await nextSolve(0, (m) => m.ground === true && m.ground_model === "fast");
    const before = solves().length;

    await user.click(gear("2"));
    const d = dialog()!;
    await user.click(within(d).getByRole("checkbox", { name: /ground plane/ }));
    await user.click(within(d).getByRole("radio", { name: /PEC/ }));
    expect(checked(d, "radio", /PEC/)).toBe(true);
    expect(tab("2").getAttribute("aria-label")).toBe("Ground slot 2: PEC");
    expect(tab("1").getAttribute("aria-label")).toBe("Ground slot 1: refl-coef");
    expect(tab("1").getAttribute("aria-selected")).toBe("true");

    // Slot 1's own settings are untouched.
    await user.click(within(d).getByRole("button", { name: "Close" }));
    await user.click(gear("1"));
    expect(checked(dialog()!, "radio", /finite/)).toBe(true);
    expect(checked(dialog()!, "radio", /refl-coef/)).toBe(true);
    await user.click(within(dialog()!).getByRole("button", { name: "Close" }));

    // Nothing the edit did reached a solve: the active slot is still slot 1.
    expect(solves().slice(before).some((m) => m.ground_model === "pec")).toBe(false);
    // Switching to slot 2 sends its new ground.
    const n = solves().length;
    await user.click(tab("2"));
    expect(await nextSolve(n, (m) => m.ground_model === "pec")).toMatchObject({ ground: true });
  });

  it("editing the active slot through its ⚙ re-solves on the new ground", async () => {
    const user = userEvent.setup();
    await mountReady();
    await nextSolve(0, (m) => m.ground === true);
    const n = solves().length;
    await user.click(gear("1"));
    await user.click(within(dialog()!).getByRole("radio", { name: "Sommerfeld" }));
    expect(tab("1").getAttribute("aria-label")).toBe("Ground slot 1: Sommerfeld");
    expect(await nextSolve(n, (m) => m.ground_model === "sommerfeld")).toMatchObject({
      ground: true,
    });
  });

  it("the active slot's notices sit under the tab strip, outside the ⚙", async () => {
    const user = userEvent.setup();
    await mountReady({ examples: [BURIED] });
    const notices = screen.getByLabelText("Ground notices");
    expect(notices.textContent).toContain("buried design — Sommerfeld ground selected automatically");
    // The active slot's settings do not repeat them.
    await user.click(gear("1"));
    expect(within(dialog()!).queryByText(/buried design/)).toBeNull();
    await user.click(within(dialog()!).getByRole("button", { name: "Close" }));
    // On free space (slot 2) the line goes: the notice is slot 1's, and slot
    // 1's own settings still say so.
    await user.click(tab("2"));
    expect(screen.queryByLabelText("Ground notices")).toBeNull();
    await user.click(gear("1"));
    expect(within(dialog()!).getByText(/buried design — Sommerfeld ground selected/)).toBeTruthy();
  });

  it("on a phone the ⚙ opens the same settings", async () => {
    const user = userEvent.setup();
    await mountReady({ mobile: true });
    await user.click(screen.getAllByRole("button", { name: "Ground slot 2 settings" })[0]);
    const d = dialog()!;
    expect(d.getAttribute("aria-label")).toBe("Ground slot 2 settings");
    expect(within(d).getByRole("checkbox", { name: /ground plane/ })).toBeTruthy();
  });
});
