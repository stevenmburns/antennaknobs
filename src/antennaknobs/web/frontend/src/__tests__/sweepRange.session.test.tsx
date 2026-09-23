/**
 * The measurement dial's range menu through a real <DesignSession> (AK#1682).
 *
 * The dial's travel IS the sweep range. This drives the production wiring —
 * right-click the dial, edit in the menu, read back the dial's aria extents
 * AND the freqs the session actually sends to /sweep — so parity is checked
 * on the two consumers, not on a fixture that builds its own range.
 */
import { describe, it, expect, afterEach, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ExampleDescriptor } from "../lib/params";
import { LONG_PRESS_MS } from "../components/session/VfoPanel";
import { HARNESS_EXAMPLE, mountDesignSession } from "./designSessionHarness";

// A deck with `FR 0 15 0 0 14.0 0.025`, as /examples serves it.
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

function dial(): [number, number] {
  const k = screen.getByRole("slider", { name: "measurement frequency" });
  return [Number(k.getAttribute("aria-valuemin")), Number(k.getAttribute("aria-valuemax"))];
}

function openMenu(container: HTMLElement) {
  fireEvent.contextMenu(container.querySelector(".vfo-dial")!, { clientX: 40, clientY: 50 });
  return screen.getByRole("dialog", { name: "sweep range" });
}

function mountCapturing(examples: ExampleDescriptor[]) {
  const sweeps: number[][] = [];
  const routes = {
    "/sweep": (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body ?? "{}"));
      if (!body._refine) sweeps.push(body.freqs_mhz as number[]);
      // An empty stream that closes at once: the request is what's under test.
      return {
        ok: true,
        status: 200,
        body: {
          getReader: () => ({
            read: async () => ({ done: true, value: undefined }),
          }),
        },
      } as unknown as Response;
    },
  };
  const r = mountDesignSession({ examples, routes });
  return { ...r, sweeps };
}

// Every wait below is on a CONDITION, never on "a sweep arrived": the
// session mounts before /examples lands, so its first dial window and first
// sweep can be the default ×0.8–×1.25 one (11.44–17.875) rather than the
// deck's. Waiting on the condition itself is what makes these order-proof.
const T = { timeout: 5000 };

async function deckLoaded() {
  await waitFor(() => expect(dial()).toEqual([14, 14.35]), T);
}

// The most recent base sweep, once it satisfies `check`.
async function sweepWhere(
  sweeps: number[][],
  check: (f: number[]) => void,
): Promise<number[]> {
  await waitFor(() => {
    expect(sweeps.length).toBeGreaterThan(0);
    check(sweeps[sweeps.length - 1]);
  }, T);
  return sweeps[sweeps.length - 1];
}

function spans(lo: number, hi: number, n?: number) {
  return (f: number[]) => {
    if (n !== undefined) expect(f).toHaveLength(n);
    expect(f[0]).toBeCloseTo(lo, 9);
    expect(f[f.length - 1]).toBeCloseTo(hi, 9);
  };
}

describe("the sweep range menu in the session (AK#1682)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("the file's range is the dial's travel and the sweep's grid", async () => {
    const { sweeps } = mountCapturing([DECK]);
    await deckLoaded();
    await sweepWhere(sweeps, spans(14, 14.35, 15));
  });

  it("after an edit, the dial's travel and the sweep's [lo, hi] are the same numbers", async () => {
    const user = userEvent.setup();
    const { container, sweeps } = mountCapturing([DECK]);
    await deckLoaded();
    await sweepWhere(sweeps, spans(14, 14.35, 15));

    const menu = openMenu(container);
    const [lo, hi] = within(menu).getAllByRole("spinbutton");
    await user.clear(hi);
    await user.type(hi, "14.5");
    await user.clear(lo);
    await user.type(lo, "13.9");
    // The menu reads the file's step, and the edit kept it.
    expect(within(menu).getByText("Step (MHz)")).toBeTruthy();
    await waitFor(() => expect(dial()).toEqual([13.9, 14.5]), T);
    // The sweep's ends are the dial's, at the file's 0.025 MHz: 25 points.
    await sweepWhere(sweeps, spans(dial()[0], dial()[1], 25));

    // Spacing → log keeps the point count; the dial is unmoved.
    await user.selectOptions(within(menu).getByRole("combobox", { name: "sweep spacing" }), "log");
    expect(within(menu).getByText("Points / decade")).toBeTruthy();
    await sweepWhere(sweeps, (h) => {
      expect(h[1] / h[0]).toBeCloseTo(h[2] / h[1], 9);
      spans(dial()[0], dial()[1])(h);
    });

    // ↺ design range: back to the file's range, dial and sweep together.
    await user.click(within(menu).getByRole("button", { name: "↺ design range" }));
    await deckLoaded();
    await sweepWhere(sweeps, spans(14, 14.35, 15));
  });

  it("says when the grid is clamped to the hosted limit", async () => {
    const user = userEvent.setup();
    const { container } = mountCapturing([DECK]);
    await deckLoaded();
    const menu = openMenu(container);
    const step = within(menu).getAllByRole("spinbutton")[2];
    await user.clear(step);
    await user.type(step, "0.0001");
    await waitFor(() =>
      expect(within(menu).getByText(/clamped to 500, the hosted limit/)).toBeTruthy(),
    T);
  });

  it("the backdrop closes it, and so does Escape", async () => {
    const user = userEvent.setup();
    const { container } = mountCapturing([DECK]);
    await deckLoaded();
    openMenu(container);
    await user.click(container.ownerDocument.querySelector(".knob-menu-backdrop")!);
    expect(screen.queryByRole("dialog", { name: "sweep range" })).toBeNull();
    openMenu(container);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "sweep range" })).toBeNull();
  });

  it("a long press opens it on touch; a drag does not", async () => {
    // jsdom has no pointer capture; the Knob's drag calls it on pointerdown.
    const proto = Element.prototype as unknown as Record<string, unknown>;
    proto.setPointerCapture ??= () => {};
    proto.releasePointerCapture ??= () => {};
    // …and no PointerEvent, so fireEvent would drop clientX / pointerType.
    if (typeof window.PointerEvent === "undefined") {
      class PointerEventShim extends MouseEvent {
        pointerType: string;
        pointerId: number;
        constructor(type: string, init: PointerEventInit = {}) {
          super(type, init);
          this.pointerType = init.pointerType ?? "mouse";
          this.pointerId = init.pointerId ?? 1;
        }
      }
      vi.stubGlobal("PointerEvent", PointerEventShim);
    }
    const { container } = mountCapturing([DECK]);
    await deckLoaded();
    vi.useFakeTimers();
    const target = container.querySelector(".vfo-dial svg")!;
    fireEvent.pointerDown(target, { pointerType: "touch", pointerId: 1, clientX: 40, clientY: 50 });
    fireEvent.pointerMove(target, { pointerType: "touch", pointerId: 1, clientX: 40, clientY: 80 });
    vi.advanceTimersByTime(LONG_PRESS_MS + 50);
    fireEvent.pointerUp(target, { pointerType: "touch", pointerId: 1 });
    expect(screen.queryByRole("dialog", { name: "sweep range" })).toBeNull();

    fireEvent.pointerDown(target, { pointerType: "touch", pointerId: 2, clientX: 40, clientY: 50 });
    vi.advanceTimersByTime(LONG_PRESS_MS + 50);
    vi.useRealTimers();
    expect(await screen.findByRole("dialog", { name: "sweep range" })).toBeTruthy();
    // The finger is still down: Android's own contextmenu now lands on the
    // backdrop, and must not close what the long press just opened.
    fireEvent.contextMenu(container.ownerDocument.querySelector(".knob-menu-backdrop")!);
    expect(screen.getByRole("dialog", { name: "sweep range" })).toBeTruthy();
  });

  it("a band pick clears the session edit", async () => {
    const user = userEvent.setup();
    const { container } = mountCapturing([DECK]);
    await deckLoaded();
    const menu = openMenu(container);
    const hi = within(menu).getAllByRole("spinbutton")[1];
    await user.clear(hi);
    await user.type(hi, "15");
    await waitFor(() => expect(dial()).toEqual([14, 15]), T);
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "measurement band" }));
    await user.click(screen.getByRole("option", { name: "14.175 MHz" }));
    await deckLoaded();
  });
});

describe("measFreq and the range it must sit in (AK#1682)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function lcd(container: HTMLElement) {
    return container.querySelector(".freq-lcd .lcd-live")?.textContent;
  }

  it("an edit that leaves measFreq outside the range clamps it in, and so does ↺", async () => {
    const user = userEvent.setup();
    const { container } = mountCapturing([DECK]);
    await deckLoaded();
    await waitFor(() => expect(lcd(container)).toBe("14.175"), T);

    const menu = openMenu(container);
    const [lo, hi] = within(menu).getAllByRole("spinbutton");
    await user.clear(hi);
    await user.type(hi, "14.6");
    await user.clear(lo);
    await user.type(lo, "14.4");
    await waitFor(() => expect(dial()).toEqual([14.4, 14.6]), T);
    // 14.175 is below the new lo: the measurement moves to the end stop.
    await waitFor(() => expect(lcd(container)).toBe("14.400"), T);

    // ↺ design range: back to 14–14.35, which 14.4 is above.
    await user.click(within(menu).getByRole("button", { name: "↺ design range" }));
    await deckLoaded();
    await waitFor(() => expect(lcd(container)).toBe("14.350"), T);
  });

  it("a locked dial keeps measuring at the design frequency", async () => {
    // HARNESS_EXAMPLE has a design frequency, so the lock is live. The dial
    // is disabled while locked; an edited range that excludes the design
    // frequency does not move the measurement off it.
    const user = userEvent.setup();
    const { container } = mountCapturing([HARNESS_EXAMPLE]);
    await waitFor(() => expect(lcd(container)).toBeTruthy(), T);
    const locked = lcd(container);
    const menu = openMenu(container);
    const [lo, hi] = within(menu).getAllByRole("spinbutton");
    await user.clear(hi);
    await user.type(hi, "1000");
    await user.clear(lo);
    await user.type(lo, "900");
    await waitFor(() => expect(dial()).toEqual([900, 1000]), T);
    expect(lcd(container)).toBe(locked);
  });
});
