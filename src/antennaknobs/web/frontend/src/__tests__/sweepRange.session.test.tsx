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

async function lastSweepAfter(sweeps: number[][], n: number): Promise<number[]> {
  await waitFor(() => expect(sweeps.length).toBeGreaterThan(n), { timeout: 3000 });
  return sweeps[sweeps.length - 1];
}

describe("the sweep range menu in the session (AK#1682)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("the file's range is the dial's travel and the sweep's grid", async () => {
    const { sweeps } = mountCapturing([DECK]);
    await waitFor(() => expect(dial()).toEqual([14, 14.35]));
    const f = await lastSweepAfter(sweeps, 0);
    expect(f).toHaveLength(15);
    expect(f[0]).toBeCloseTo(14, 9);
    expect(f[14]).toBeCloseTo(14.35, 9);
  });

  it("after an edit, the dial's travel and the sweep's [lo, hi] are the same numbers", async () => {
    const user = userEvent.setup();
    const { container, sweeps } = mountCapturing([DECK]);
    await waitFor(() => expect(dial()).toEqual([14, 14.35]));
    await lastSweepAfter(sweeps, 0);

    const menu = openMenu(container);
    const [lo, hi] = within(menu).getAllByRole("spinbutton");
    await user.clear(hi);
    await user.type(hi, "14.5");
    await user.clear(lo);
    await user.type(lo, "13.9");
    // The menu reads the file's step, and the edit kept it.
    expect(within(menu).getByText("Step (MHz)")).toBeTruthy();
    await waitFor(() => expect(dial()).toEqual([13.9, 14.5]));
    const before = sweeps.length;
    const f = await lastSweepAfter(sweeps, before - 1);
    await waitFor(() => {
      const g = sweeps[sweeps.length - 1];
      expect(g[0]).toBeCloseTo(dial()[0], 9);
      expect(g[g.length - 1]).toBeCloseTo(dial()[1], 9);
    });
    expect(f.length).toBeGreaterThan(0);
    const g = sweeps[sweeps.length - 1];
    expect(g).toHaveLength(25); // 13.9 → 14.5 at the file's 0.025 MHz

    // Spacing → log keeps the point count; the dial is unmoved.
    await user.selectOptions(within(menu).getByRole("combobox", { name: "sweep spacing" }), "log");
    expect(within(menu).getByText("Points / decade")).toBeTruthy();
    await waitFor(() => {
      const h = sweeps[sweeps.length - 1];
      expect(h[1] / h[0]).toBeCloseTo(h[2] / h[1], 9);
      expect(h[0]).toBeCloseTo(dial()[0], 9);
      expect(h[h.length - 1]).toBeCloseTo(dial()[1], 9);
    });

    // ↺ design range: back to the file's range, dial and sweep together.
    await user.click(within(menu).getByRole("button", { name: "↺ design range" }));
    await waitFor(() => expect(dial()).toEqual([14, 14.35]));
    await waitFor(() => {
      const h = sweeps[sweeps.length - 1];
      expect(h).toHaveLength(15);
      expect(h[0]).toBeCloseTo(14, 9);
      expect(h[14]).toBeCloseTo(14.35, 9);
    });
  });

  it("says when the grid is clamped to the hosted limit", async () => {
    const user = userEvent.setup();
    const { container } = mountCapturing([DECK]);
    await waitFor(() => expect(dial()).toEqual([14, 14.35]));
    const menu = openMenu(container);
    const step = within(menu).getAllByRole("spinbutton")[2];
    await user.clear(step);
    await user.type(step, "0.0001");
    await waitFor(() =>
      expect(within(menu).getByText(/clamped to 500, the hosted limit/)).toBeTruthy(),
    );
  });

  it("the backdrop closes it, and so does Escape", async () => {
    const user = userEvent.setup();
    const { container } = mountCapturing([DECK]);
    await waitFor(() => expect(dial()).toEqual([14, 14.35]));
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
    await waitFor(() => expect(dial()).toEqual([14, 14.35]));
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
    await waitFor(() => expect(dial()).toEqual([14, 14.35]));
    const menu = openMenu(container);
    const hi = within(menu).getAllByRole("spinbutton")[1];
    await user.clear(hi);
    await user.type(hi, "15");
    await waitFor(() => expect(dial()).toEqual([14, 15]));
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "measurement band" }));
    await user.click(screen.getByRole("option", { name: "14.175 MHz" }));
    await waitFor(() => expect(dial()).toEqual([14, 14.35]));
  });
});
