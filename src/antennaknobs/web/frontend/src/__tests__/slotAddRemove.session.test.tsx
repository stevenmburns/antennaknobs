// AK#1801 (the "+" section), extended to the solver slots: both slot tab
// strips end in a + that appends a copy of the ACTIVE slot, makes it active
// and opens its settings; a slot past the stock set carries a remove in its
// settings, and only the last one can go, since slots run without gaps.
// Through a real <DesignSession>, with the solve payload and the settings
// save as the evidence rather than the strip's state.
//
// Mutation (run by hand, 2026-10-01): copying from the FIRST slot instead of
// the active one (useSolverSlots' addSlot reading slots.A; addGroundSlot
// reading state.slots[0]) fails "+ appends a copy of the active solver slot"
// and "+ appends a copy of the active ground slot".
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mountReady, untilDom } from "./designSessionHarness";
import { SERVED_SLOT_SEEDS } from "./backendFixtures";

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

const solverTab = (id: string) =>
  screen.getByRole("tab", { name: new RegExp(`^Solver slot ${id}:`) });
const solverIds = () =>
  screen
    .getAllByRole("tab", { name: /^Solver slot / })
    .map((t) => t.getAttribute("aria-label")!.replace(/^Solver slot ([A-Z]):.*$/, "$1"));
const groundTab = (id: string) =>
  screen.getByRole("tab", { name: new RegExp(`^Ground slot ${id}:`) });
const groundIds = () =>
  screen
    .getAllByRole("tab", { name: /^Ground slot / })
    .map((t) => t.getAttribute("aria-label")!.replace(/^Ground slot ([A-Z]):.*$/, "$1"));
const isActive = (t: HTMLElement) => t.getAttribute("aria-selected") === "true";
const addSolver = () => screen.queryByRole("button", { name: /^Add solver slot / });
const addGround = () => screen.queryByRole("button", { name: /^Add ground slot / });
const solverDialog = (id: string) => screen.queryByRole("dialog", { name: `Slot ${id} options` });
const groundDialog = (id: string) =>
  screen.queryByRole("dialog", { name: `Ground slot ${id} settings` });
// A tab's summary, without the letter: what the slot holds.
const holds = (t: HTMLElement) => t.getAttribute("aria-label")!.replace(/^[^:]+: /, "");

beforeEach(() => {
  RecordingWebSocket.all = [];
  vi.stubGlobal("WebSocket", RecordingWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("solver slots: + and remove (AK#1801)", () => {
  it("+ appends a copy of the active solver slot, active, with its options open", async () => {
    const user = userEvent.setup();
    await mountReady();
    expect(solverIds()).toEqual(["A", "B", "C"]);
    await user.click(solverTab("B"));
    await user.click(addSolver()!);
    expect(solverIds()).toEqual(["A", "B", "C", "D"]);
    expect(isActive(solverTab("D"))).toBe(true);
    expect(holds(solverTab("D"))).toBe(holds(solverTab("B")));
    expect(solverDialog("D")).not.toBeNull();
    await user.click(within(solverDialog("D")!).getByRole("button", { name: "Close" }));

    // The solve follows slot D: B's density, not A's.
    await user.click(solverTab("A"));
    const n = solves().length;
    await user.click(solverTab("D"));
    expect(await nextSolve(n, (m) => m.n_per_wire === 20)).toMatchObject({ n_per_wire: 20 });
  });

  it("five at most: the + goes once slot E exists", async () => {
    const user = userEvent.setup();
    await mountReady();
    await user.click(addSolver()!);
    await user.click(within(solverDialog("D")!).getByRole("button", { name: "Close" }));
    expect(addSolver()!.getAttribute("aria-label")).toMatch(/^Add solver slot E/);
    await user.click(addSolver()!);
    expect(solverIds()).toEqual(["A", "B", "C", "D", "E"]);
    expect(addSolver()).toBeNull();
  });

  it("only the last added slot can be removed; a stock slot has no remove", async () => {
    const user = userEvent.setup();
    await mountReady();
    await user.click(screen.getByRole("button", { name: "Slot A options" }));
    expect(
      within(solverDialog("A")!).queryByRole("button", { name: /^Remove solver slot/ }),
    ).toBeNull();
    await user.click(within(solverDialog("A")!).getByRole("button", { name: "Close" }));

    await user.click(addSolver()!);
    await user.click(within(solverDialog("D")!).getByRole("button", { name: "Close" }));
    await user.click(addSolver()!);
    await user.click(within(solverDialog("E")!).getByRole("button", { name: "Close" }));

    await user.click(screen.getByRole("button", { name: "Slot D options" }));
    const removeD = within(solverDialog("D")!).getByRole("button", {
      name: "Remove solver slot D",
    }) as HTMLButtonElement;
    expect(removeD.disabled).toBe(true);
    expect(solverDialog("D")!.textContent).toContain("remove slot E first");
    await user.click(within(solverDialog("D")!).getByRole("button", { name: "Close" }));

    // E is active (the last +); removing it makes D active and closes the dialog.
    expect(isActive(solverTab("E"))).toBe(true);
    await user.click(screen.getByRole("button", { name: "Slot E options" }));
    await user.click(
      within(solverDialog("E")!).getByRole("button", { name: "Remove solver slot E" }),
    );
    expect(solverIds()).toEqual(["A", "B", "C", "D"]);
    expect(isActive(solverTab("D"))).toBe(true);
    expect(solverDialog("E")).toBeNull();
  });

  it("a slot the settings file adds is served as a seed and can be removed", async () => {
    const user = userEvent.setup();
    await mountReady({
      slotSeeds: [
        ...SERVED_SLOT_SEEDS,
        { slot: "D", backend: "bspline", n_per_wire: 31, model: {} },
      ],
    });
    expect(solverIds()).toEqual(["A", "B", "C", "D"]);
    expect(solverTab("D").getAttribute("aria-label")).toContain("N=31");
    await user.click(screen.getByRole("button", { name: "Slot D options" }));
    await user.click(
      within(solverDialog("D")!).getByRole("button", { name: "Remove solver slot D" }),
    );
    expect(solverIds()).toEqual(["A", "B", "C"]);
  });
});

describe("ground slots: + and remove (AK#1801)", () => {
  it("+ appends a copy of the active ground slot, active, with its settings open", async () => {
    const user = userEvent.setup();
    await mountReady();
    await user.click(groundTab("Z"));
    await user.click(addGround()!);
    expect(groundIds()).toEqual(["X", "Y", "Z", "U"]);
    expect(isActive(groundTab("U"))).toBe(true);
    expect(holds(groundTab("U"))).toBe(holds(groundTab("Z")));
    const dialog = groundDialog("U")!;
    expect(dialog).not.toBeNull();

    // Its settings edit slot U only, and the solve follows U.
    const n = solves().length;
    await user.click(within(dialog).getByRole("radio", { name: /PEC/ }));
    expect(groundTab("U").getAttribute("aria-label")).toBe("Ground slot U: PEC");
    expect(holds(groundTab("Z"))).toMatch(/^refl-coef/);
    expect(await nextSolve(n, (m) => m.ground_model === "pec")).toMatchObject({ ground: true });
  });

  it("a stock slot has no remove; the added one does, and its slot before becomes active", async () => {
    const user = userEvent.setup();
    await mountReady();
    await user.click(screen.getByRole("button", { name: "Ground slot Z settings" }));
    expect(
      within(groundDialog("Z")!).queryByRole("button", { name: /^Remove ground slot/ }),
    ).toBeNull();
    await user.click(within(groundDialog("Z")!).getByRole("button", { name: "Close" }));

    await user.click(addGround()!);
    await user.click(within(groundDialog("U")!).getByRole("button", { name: "Close" }));
    await user.click(addGround()!);
    // V's gear is open; U cannot go before V.
    await user.click(within(groundDialog("V")!).getByRole("button", { name: "Close" }));
    await user.click(screen.getByRole("button", { name: "Ground slot U settings" }));
    expect(
      (
        within(groundDialog("U")!).getByRole("button", {
          name: "Remove ground slot U",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    await user.click(within(groundDialog("U")!).getByRole("button", { name: "Close" }));

    await user.click(screen.getByRole("button", { name: "Ground slot V settings" }));
    await user.click(
      within(groundDialog("V")!).getByRole("button", { name: "Remove ground slot V" }),
    );
    expect(groundIds()).toEqual(["X", "Y", "Z", "U"]);
    expect(isActive(groundTab("U"))).toBe(true);
    expect(groundDialog("V")).toBeNull();
  });
});

describe("added slots in the settings save (AK#1801)", () => {
  it("posts every slot, the added ones included, and a removed one not at all", async () => {
    const user = userEvent.setup();
    let posted: Record<string, unknown> | null = null;
    const defaults = {
      path: "/home/ham/.antennaknobs/settings.toml",
      exists: true,
      writable: true,
      switches: {},
      problems: [],
    };
    await mountReady({
      uiDefaults: defaults,
      routes: {
        "/settings": (_url, init) => {
          posted = JSON.parse(String(init?.body));
          return {
            ok: true,
            status: 200,
            json: async () => defaults,
          } as unknown as Response;
        },
      },
    });
    await user.click(addSolver()!);
    await user.click(within(solverDialog("D")!).getByRole("button", { name: "Close" }));
    await user.click(addGround()!);
    await user.click(within(groundDialog("U")!).getByRole("button", { name: "Close" }));
    await user.click(addGround()!);
    await user.click(
      within(groundDialog("V")!).getByRole("button", { name: "Remove ground slot V" }),
    );

    await user.click(screen.getByRole("button", { name: "Tools menu" }));
    await user.click(screen.getByRole("button", { name: "save as my defaults" }));
    await untilDom(() => screen.queryByRole("status"));
    const body = posted as unknown as {
      grounds: Record<string, unknown>;
      slots: Record<string, { backend: string }>;
    };
    expect(Object.keys(body.slots)).toEqual(["A", "B", "C", "D"]);
    expect(body.slots.D!.backend).toBe(body.slots.A!.backend);
    expect(Object.keys(body.grounds)).toEqual(["X", "Y", "Z", "U"]);
  });
});
