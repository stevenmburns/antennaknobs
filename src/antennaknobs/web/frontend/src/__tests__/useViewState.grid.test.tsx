// Unit 3 of docs/plan-view-rail-scaling.md ("Layout modes"/"Keyboard"): the
// grid-mode half of useViewState — arrow cycling over the displayed cells
// only, and the off-grid-ring recovery effect wired to the pure gridFix
// decision (useViewPrefs.grid.test.tsx tests that function directly; this
// file proves the HOOK actually applies it, which is what mutation probe
// 4(b) — "drop the off-grid snap" — needs to catch).
//
// Rail mode's own arrow-cycling behavior (pinned ∪ active, cap, wrap, the
// input/knob focus guard) is pinned in useViewPrefs.test.tsx and is
// UNTOUCHED by this unit — nothing here repeats it beyond the one sanity
// check that layout defaulting to "rail" doesn't change it.
import { describe, it, expect, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { type View } from "../lib/view";
import { useViewState } from "../components/session/useViewState";
import { type Layout } from "../components/session/useViewPrefs";

const FOUNDING: View[] = ["antenna", "azimuth", "elevation", "smith"];

function press(key: string, target?: HTMLElement) {
  act(() => {
    (target ?? document.body).dispatchEvent(
      new KeyboardEvent("keydown", { key, bubbles: true }),
    );
  });
}

// --- 1. Grid-mode arrow cycling ------------------------------------------

describe("grid-mode arrow cycling", () => {
  it("cycles exactly the displayed cells (first ≤4 pins) and wraps", () => {
    const { result } = renderHook(() =>
      useViewState({ currentExample: undefined, active: true, pinned: FOUNDING, layout: "grid" }),
    );
    const seen: View[] = [];
    for (let i = 0; i < FOUNDING.length; i++) {
      press("ArrowDown");
      seen.push(result.current.view);
    }
    expect(seen).toEqual(["azimuth", "elevation", "smith", "antenna"]);
  });

  it("never lands on pin #5 or #6, even though they're pinned", () => {
    const sixPins: View[] = [...FOUNDING, "schematic", "gamma"];
    const { result } = renderHook(() =>
      useViewState({ currentExample: undefined, active: true, pinned: sixPins, layout: "grid" }),
    );
    const seen = new Set<View>([result.current.view]);
    for (let i = 0; i < 8; i++) {
      press("ArrowDown");
      seen.add(result.current.view);
    }
    expect(seen).toEqual(new Set(FOUNDING));
  });

  it("does not affect rail mode's pinned ∪ active cycle (default layout)", () => {
    const { result } = renderHook(() =>
      useViewState({ currentExample: undefined, active: true, pinned: FOUNDING }),
    );
    act(() => result.current.setView("schematic"));
    press("ArrowDown");
    // Same as useViewPrefs.test.tsx's "keeps a peeked view in the cycle":
    // schematic (a peek, unpinned) sits at the end of pinned ∪ active.
    expect(result.current.view).toBe("antenna");
  });
});

// --- 2. Off-grid ring recovery (mutation probe 4b target) -----------------

describe("off-grid ring recovery", () => {
  it("snaps to cell 1 when the hook mounts already in grid with an off-grid view", () => {
    // The ring starts at useViewState's own default ("antenna"), which IS
    // displayed here, so peek a pinned-but-off-grid view first, THEN mount
    // fresh at layout="grid" to simulate "entering grid with it active" —
    // renderHook's initial render already has layout="grid", so wasGridRef
    // inits to true and this exercises the "already in grid" branch instead;
    // see the next test for the true "just switched into grid" transition.
    const sixPins: View[] = [...FOUNDING, "schematic", "gamma"];
    const { result } = renderHook(() =>
      useViewState({ currentExample: undefined, active: true, pinned: sixPins, layout: "grid" }),
    );
    act(() => result.current.setView("gamma"));
    expect(result.current.view).toBe("antenna");
  });

  it("snaps to cell 1 on the rail→grid transition with a peeked view active", () => {
    const setLayout = vi.fn();
    const { result, rerender } = renderHook<ReturnType<typeof useViewState>, { layout: Layout }>(
      ({ layout }) =>
        useViewState({
          currentExample: undefined,
          active: true,
          pinned: FOUNDING,
          layout,
          setLayout,
        }),
      { initialProps: { layout: "rail" } },
    );
    act(() => result.current.setView("schematic")); // peek, still rail
    expect(result.current.view).toBe("schematic");
    rerender({ layout: "grid" }); // the segmented control's click
    // Entering grid with a peek active snaps the ring — grid mode itself is
    // NOT abandoned (setLayout must not have been called).
    expect(result.current.view).toBe("antenna");
    expect(setLayout).not.toHaveBeenCalled();
  });

  it("snaps to cell 1 on the rail→grid transition with pin #5 active", () => {
    const sixPins: View[] = [...FOUNDING, "schematic", "gamma"];
    const setLayout = vi.fn();
    const { result, rerender } = renderHook<ReturnType<typeof useViewState>, { layout: Layout }>(
      ({ layout }) =>
        useViewState({
          currentExample: undefined,
          active: true,
          pinned: sixPins,
          layout,
          setLayout,
        }),
      { initialProps: { layout: "rail" } },
    );
    act(() => result.current.setView("gamma"));
    rerender({ layout: "grid" });
    expect(result.current.view).toBe("antenna");
    expect(setLayout).not.toHaveBeenCalled();
  });

  it("leaves grid for rail when already-in-grid picks an unpinned peek", () => {
    const setLayout = vi.fn();
    const { result } = renderHook(() =>
      useViewState({
        currentExample: undefined,
        active: true,
        pinned: FOUNDING,
        layout: "grid",
        setLayout,
      }),
    );
    // Simulates the picker's row-click landing on an unpinned view while
    // already in grid mode.
    act(() => result.current.setView("schematic"));
    expect(setLayout).toHaveBeenCalledWith("rail");
    // The view itself is left as the peek — rail mode shows it as primary.
    expect(result.current.view).toBe("schematic");
  });

  it("does nothing when setLayout is omitted (the branch is simply inert)", () => {
    const { result } = renderHook(() =>
      useViewState({ currentExample: undefined, active: true, pinned: FOUNDING, layout: "grid" }),
    );
    expect(() => act(() => result.current.setView("schematic"))).not.toThrow();
  });
});
