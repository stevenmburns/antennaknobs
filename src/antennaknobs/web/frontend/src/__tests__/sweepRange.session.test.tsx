/**
 * The measurement dial's range menu through a real <DesignSession> (AK#1682).
 *
 * The dial's travel IS the sweep range. This drives the production wiring —
 * right-click the dial, edit in the menu, read back the dial's aria extents
 * AND the freqs the session actually sends to /sweep — so parity is checked
 * on the two consumers, not on a fixture that builds its own range.
 */
import { describe, it, expect, afterEach, vi } from "vitest";
import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ExampleDescriptor } from "../lib/params";
import { LONG_PRESS_MS } from "../components/session/VfoPanel";
import { HARNESS_EXAMPLE, mountReady, sweepBaseDone, sweepIdle, untilDom } from "./designSessionHarness";

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

async function mountCapturing(examples: ExampleDescriptor[]) {
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
  // Ready first (AK#1762): the design has loaded, so the dial's travel is
  // the deck's, and the dial and its range menu are live.
  const r = await mountReady({ examples, routes });
  return { ...r, sweeps };
}

// The deck's own range on the dial: synchronous once mountReady returns,
// and after any edit or revert (it lands inside the edit's act).
function deckLoaded() {
  expect(dial()).toEqual([14, 14.35]);
}

// The freq sweep runner's phase, on the Smith chart (pinned by default).
const smith = () => document.querySelector<HTMLElement>("canvas.smith")!;

// The most recent base sweep, once the runner has sent and streamed it
// (AK#1762): every sweep an edit queued has then gone out, so the last one
// is the edit's. (Refinement may still be polishing; it adds points to this
// curve and is not what these checks are about.)
async function sweepWhere(
  sweeps: number[][],
  check: (f: number[]) => void,
): Promise<number[]> {
  await sweepBaseDone(smith());
  expect(sweeps.length).toBeGreaterThan(0);
  check(sweeps[sweeps.length - 1]);
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
    const { sweeps } = await mountCapturing([DECK]);
    deckLoaded();
    await sweepWhere(sweeps, spans(14, 14.35, 15));
  });

  it("after an edit, the dial's travel and the sweep's [lo, hi] are the same numbers", async () => {
    const user = userEvent.setup();
    const { container, sweeps } = await mountCapturing([DECK]);
    deckLoaded();
    await sweepWhere(sweeps, spans(14, 14.35, 15));

    const menu = openMenu(container);
    const [lo, hi] = within(menu).getAllByRole("spinbutton");
    await user.clear(hi);
    await user.type(hi, "14.5{Enter}");
    await user.clear(lo);
    await user.type(lo, "13.9{Enter}");
    // The menu reads the file's step, and the edit kept it.
    expect(within(menu).getByText("Step (MHz)")).toBeTruthy();
    expect(dial()).toEqual([13.9, 14.5]);
    // The sweep's ends are the dial's, at the file's 0.025 MHz: 25 points.
    await sweepWhere(sweeps, spans(dial()[0], dial()[1], 25));

    // Spacing → log keeps the point count exactly; the dial is unmoved.
    // Refinement is on by default, so the log field reads "base points".
    await user.selectOptions(within(menu).getByRole("combobox", { name: "sweep spacing" }), "log");
    expect(within(menu).getByText("Base points")).toBeTruthy();
    await sweepWhere(sweeps, (h) => {
      expect(h[1] / h[0]).toBeCloseTo(h[2] / h[1], 9);
      spans(dial()[0], dial()[1])(h);
    });

    // ↺ design range: back to the file's range, dial and sweep together.
    await user.click(within(menu).getByRole("button", { name: "↺ design range" }));
    deckLoaded();
    await sweepWhere(sweeps, spans(14, 14.35, 15));
  });

  it("says when the grid is clamped to the hosted limit", async () => {
    const user = userEvent.setup();
    const { container } = await mountCapturing([DECK]);
    deckLoaded();
    const menu = openMenu(container);
    const step = within(menu).getAllByRole("spinbutton")[2];
    await user.clear(step);
    await user.type(step, "0.0001{Enter}");
    expect(within(menu).getByText(/clamped to 500, the hosted limit/)).toBeTruthy();
  });

  // Steve, 2026-09-23: a non-positive step / a hi ≤ lo / a sub-2 log point
  // count must be visibly refused, not just silently dropped.
  it("0, a negative, or an empty step is refused, marks the field, and leaves the sweep alone", async () => {
    const user = userEvent.setup();
    const { container, sweeps } = await mountCapturing([DECK]);
    deckLoaded();
    await sweepWhere(sweeps, spans(14, 14.35, 15));
    // Fully idle (refinement done too): from here, "no sweep" is the phase
    // staying idle through each edit's act.
    await sweepIdle(smith());
    const sentBefore = sweeps.length;
    const menu = openMenu(container);
    const step = within(menu).getAllByRole("spinbutton")[2] as HTMLInputElement;
    expect(step.getAttribute("aria-invalid")).toBeNull();

    for (const bad of ["0", "-0.01", ""]) {
      await user.clear(step);
      if (bad) await user.type(step, `${bad}{Enter}`);
      expect(step.getAttribute("aria-invalid")).toBe("true");
      expect(step.getAttribute("data-invalid")).toBe("true");
    }
    // Nothing was ever applied: the runner never queued a sweep (still
    // idle, decided inside each keystroke's act), none was sent, and the
    // dial and step are unmoved.
    expect(smith().dataset.phase).toBe("idle");
    expect(sweeps.length).toBe(sentBefore);
    expect(dial()).toEqual([14, 14.35]);

    // Escape cancels the bad text (menu stays open) and restores the field.
    await user.keyboard("{Escape}");
    expect(step.value).toBe("0.025");
    expect(step.getAttribute("aria-invalid")).toBeNull();
    expect(screen.getByRole("dialog", { name: "sweep range" })).toBeTruthy();

    // Re-broken, then blur reverts it the same way.
    await user.clear(step);
    await user.type(step, "-1{Enter}");
    expect(step.getAttribute("aria-invalid")).toBe("true");
    await user.tab();
    expect(step.value).toBe("0.025");
    expect(step.getAttribute("aria-invalid")).toBeNull();
  });

  it("hi <= lo is refused and marks the field being edited", async () => {
    const user = userEvent.setup();
    const { container, sweeps } = await mountCapturing([DECK]);
    deckLoaded();
    await sweepWhere(sweeps, spans(14, 14.35, 15));
    // Fully idle (refinement done too): from here, "no sweep" is the phase
    // staying idle through each edit's act.
    await sweepIdle(smith());
    const sentBefore = sweeps.length;
    const menu = openMenu(container);
    const [lo, hi] = within(menu).getAllByRole("spinbutton") as HTMLInputElement[];

    // hi dropped to below the current lo (14).
    await user.clear(hi);
    await user.type(hi, "10{Enter}");
    expect(hi.getAttribute("aria-invalid")).toBe("true");
    expect(lo.getAttribute("aria-invalid")).toBeNull();
    expect(smith().dataset.phase).toBe("idle");
    expect(sweeps.length).toBe(sentBefore);
    expect(dial()).toEqual([14, 14.35]);

    await user.clear(hi);
    await user.type(hi, "14.35{Enter}"); // back to the file's own hi: valid again
    expect(hi.getAttribute("aria-invalid")).toBeNull();
    // Re-stating the range in force is not an edit (AK#1765): nothing queued.
    expect(smith().dataset.phase).toBe("idle");
    expect(sweeps.length).toBe(sentBefore);

    // lo raised to at or above hi.
    await user.clear(lo);
    await user.type(lo, "14.35{Enter}");
    expect(lo.getAttribute("aria-invalid")).toBe("true");
    expect(smith().dataset.phase).toBe("idle");
    expect(sweeps.length).toBe(sentBefore);
  });

  it("a log point count below 2 is refused", async () => {
    const user = userEvent.setup();
    const { container } = await mountCapturing([DECK]);
    deckLoaded();
    const menu = openMenu(container);
    await user.selectOptions(within(menu).getByRole("combobox", { name: "sweep spacing" }), "log");
    // lo, hi, points -- same slot the step field occupied for lin.
    const points = within(menu).getAllByRole("spinbutton")[2] as HTMLInputElement;
    const before = points.value;
    await user.clear(points);
    await user.type(points, "1{Enter}");
    expect(points.getAttribute("aria-invalid")).toBe("true");
    await user.tab();
    expect(points.value).toBe(before);
    expect(points.getAttribute("aria-invalid")).toBeNull();
  });

  // AK#1765: every valid keystroke used to apply ("14.35" applied 14, 14.3
  // and 14.35, a sweep queued each time); the field now commits on Enter or
  // blur, as the Z-vs-parameter boxes do.
  it("typing applies nothing until Enter, and then exactly one sweep", async () => {
    const user = userEvent.setup();
    const { container, sweeps } = await mountCapturing([DECK]);
    deckLoaded();
    await sweepWhere(sweeps, spans(14, 14.35, 15));
    await sweepIdle(smith());
    const sentBefore = sweeps.length;
    const menu = openMenu(container);
    const hi = within(menu).getAllByRole("spinbutton")[1] as HTMLInputElement;
    await user.clear(hi);
    await user.type(hi, "14.5");
    // Each prefix ("1", "14", "14.", "14.5") is text, not an edit: the dial
    // is unmoved and the runner never left idle.
    expect(hi.value).toBe("14.5");
    expect(dial()).toEqual([14, 14.35]);
    expect(smith().dataset.phase).toBe("idle");
    expect(sweeps.length).toBe(sentBefore);

    await user.keyboard("{Enter}");
    expect(dial()).toEqual([14, 14.5]);
    await sweepWhere(sweeps, spans(14, 14.5, 21));
    await sweepIdle(smith());
    // One edit, one base sweep.
    expect(sweeps.length).toBe(sentBefore + 1);
  });

  it("blur commits a typed value, as Enter does", async () => {
    const user = userEvent.setup();
    const { container, sweeps } = await mountCapturing([DECK]);
    deckLoaded();
    const menu = openMenu(container);
    const lo = within(menu).getAllByRole("spinbutton")[0] as HTMLInputElement;
    await user.clear(lo);
    await user.type(lo, "13.9");
    expect(dial()).toEqual([14, 14.35]);
    await user.tab();
    expect(dial()).toEqual([13.9, 14.35]);
    await sweepWhere(sweeps, spans(13.9, 14.35));
  });

  it("re-entering the file's own range, or re-stating it in another spelling, does not re-sweep", async () => {
    const user = userEvent.setup();
    const { container, sweeps } = await mountCapturing([DECK]);
    deckLoaded();
    await sweepWhere(sweeps, spans(14, 14.35, 15));
    await sweepIdle(smith());
    const sentBefore = sweeps.length;
    const menu = openMenu(container);
    const [lo, hi, step] = within(menu).getAllByRole("spinbutton") as HTMLInputElement[];
    for (const [field, text] of [
      [hi, "14.35"],
      [lo, "14.000"],
      [step, "0.025"],
    ] as const) {
      await user.clear(field);
      await user.type(field, `${text}{Enter}`);
      expect(field.getAttribute("aria-invalid")).toBeNull();
      expect(smith().dataset.phase).toBe("idle");
    }
    // Log and back to lin at the same point count: the file's grid again,
    // but as a session edit with a re-derived step ((hi − lo) / 14, not the
    // file's 0.025 to the last bit). The way back from log is a real change.
    const spacing = within(menu).getByRole("combobox", { name: "sweep spacing" });
    await user.selectOptions(spacing, "log");
    await sweepBaseDone(smith());
    await sweepIdle(smith());
    await user.selectOptions(spacing, "lin");
    await sweepWhere(sweeps, spans(14, 14.35, 15));
    await sweepIdle(smith());
    const afterLin = sweeps.length;
    expect(afterLin).toBe(sentBefore + 2);
    // ↺ design range swaps that session edit for the file's own range: a
    // different range object, a different rung, the same grid. The runner
    // keys on the grid, so nothing is queued.
    await user.click(within(menu).getByRole("button", { name: "↺ design range" }));
    deckLoaded();
    expect(smith().dataset.phase).toBe("idle");
    expect(sweeps.length).toBe(afterLin);
  });

  it("the backdrop closes it, and so does Escape", async () => {
    const user = userEvent.setup();
    const { container } = await mountCapturing([DECK]);
    deckLoaded();
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
    const { container } = await mountCapturing([DECK]);
    deckLoaded();
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
    // The long press's timer opened it outside any act: wait on the dialog.
    expect(
      await untilDom(() => screen.queryByRole("dialog", { name: "sweep range" })),
    ).toBeTruthy();
    // The finger is still down: Android's own contextmenu now lands on the
    // backdrop, and must not close what the long press just opened.
    fireEvent.contextMenu(container.ownerDocument.querySelector(".knob-menu-backdrop")!);
    expect(screen.getByRole("dialog", { name: "sweep range" })).toBeTruthy();
  });

  it("a band pick clears the session edit", async () => {
    const user = userEvent.setup();
    const { container } = await mountCapturing([DECK]);
    deckLoaded();
    const menu = openMenu(container);
    const hi = within(menu).getAllByRole("spinbutton")[1];
    await user.clear(hi);
    await user.type(hi, "15{Enter}");
    expect(dial()).toEqual([14, 15]);
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "measurement band" }));
    await user.click(screen.getByRole("option", { name: "14.175 MHz" }));
    deckLoaded();
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
    const { container } = await mountCapturing([DECK]);
    deckLoaded();
    expect(lcd(container)).toBe("14.175");

    const menu = openMenu(container);
    const [lo, hi] = within(menu).getAllByRole("spinbutton");
    await user.clear(hi);
    await user.type(hi, "14.6{Enter}");
    await user.clear(lo);
    await user.type(lo, "14.4{Enter}");
    expect(dial()).toEqual([14.4, 14.6]);
    // 14.175 is below the new lo: the measurement moves to the end stop.
    expect(lcd(container)).toBe("14.400");

    // ↺ design range: back to 14–14.35, which 14.4 is above.
    await user.click(within(menu).getByRole("button", { name: "↺ design range" }));
    deckLoaded();
    expect(lcd(container)).toBe("14.350");
  });

  it("a locked dial keeps measuring at the design frequency", async () => {
    // HARNESS_EXAMPLE has a design frequency, so the lock is live. The dial
    // is disabled while locked; an edited range that excludes the design
    // frequency does not move the measurement off it.
    const user = userEvent.setup();
    const { container } = await mountCapturing([HARNESS_EXAMPLE]);
    const locked = lcd(container);
    const menu = openMenu(container);
    const [lo, hi] = within(menu).getAllByRole("spinbutton");
    await user.clear(hi);
    await user.type(hi, "1000{Enter}");
    await user.clear(lo);
    await user.type(lo, "900{Enter}");
    expect(dial()).toEqual([900, 1000]);
    expect(lcd(container)).toBe(locked);
  });
});
