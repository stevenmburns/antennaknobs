// Issue #714, deferred from #700 (docs/plan-view-rail-scaling.md: "pin order
// = order pinned" was explicitly out of v1). Pin order IS rail/grid/carousel
// order (railViews, gridCells, mobileScreens all derive straight from
// `pinned`), so the whole reorder feature is one swap in the stored array —
// movePinned is the pure half, movePin the hook action that persists it.
//
// A separate file rather than additions to useViewPrefs.test.tsx, for the
// same reason useViewPrefs.grid.test.tsx and useViewPrefs.storage.test.tsx
// are separate: that file is the pre-existing baseline kept passing UNEDITED.
import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { type View } from "../lib/view";
import {
  VIEW_PREFS_KEY,
  movePinned,
  useViewPrefs,
} from "../components/session/useViewPrefs";

const FOUNDING: View[] = ["antenna", "azimuth", "elevation", "smith"];

beforeEach(() => {
  localStorage.clear();
});

function stored() {
  return JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "null");
}

// --- 1. movePinned, the pure swap --------------------------------------

describe("movePinned", () => {
  it("swaps a pin with its earlier neighbor", () => {
    expect(movePinned(FOUNDING, "elevation", -1)).toEqual([
      "antenna",
      "elevation",
      "azimuth",
      "smith",
    ]);
  });

  it("swaps a pin with its later neighbor", () => {
    expect(movePinned(FOUNDING, "azimuth", 1)).toEqual([
      "antenna",
      "elevation",
      "azimuth",
      "smith",
    ]);
  });

  it("returns the SAME array reference at the front edge (no earlier neighbor)", () => {
    const next = movePinned(FOUNDING, "antenna", -1);
    expect(next).toBe(FOUNDING);
  });

  it("returns the SAME array reference at the back edge (no later neighbor)", () => {
    const next = movePinned(FOUNDING, "smith", 1);
    expect(next).toBe(FOUNDING);
  });

  it("returns the SAME array reference for an unpinned id", () => {
    const next = movePinned(FOUNDING, "schematic", -1);
    expect(next).toBe(FOUNDING);
  });

  it("returns the SAME array reference for an id the registry does not know", () => {
    const next = movePinned(FOUNDING, "no-such-view" as View, 1);
    expect(next).toBe(FOUNDING);
  });

  it("does not mutate its input", () => {
    const copy = [...FOUNDING];
    movePinned(copy, "elevation", -1);
    expect(copy).toEqual(FOUNDING);
  });
});

// --- 2. movePin, the hook action ----------------------------------------

describe("movePin", () => {
  it("swaps the neighbor and persists it", () => {
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.movePin("elevation", -1));
    expect(result.current.pinned).toEqual([
      "antenna",
      "elevation",
      "azimuth",
      "smith",
    ]);
    expect(stored().pinned).toEqual([
      "antenna",
      "elevation",
      "azimuth",
      "smith",
    ]);
  });

  it("round-trips a reorder through storage to the next mount", () => {
    const first = renderHook(() => useViewPrefs());
    act(() => first.result.current.movePin("smith", -1));
    first.unmount();

    const second = renderHook(() => useViewPrefs());
    expect(second.result.current.pinned).toEqual([
      "antenna",
      "azimuth",
      "smith",
      "elevation",
    ]);
  });

  it("no-ops at the front edge, and writes nothing", () => {
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.movePin("antenna", -1));
    expect(result.current.pinned).toEqual(FOUNDING);
    expect(localStorage.getItem(VIEW_PREFS_KEY)).toBeNull();
  });

  it("no-ops at the back edge, and writes nothing", () => {
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.movePin("smith", 1));
    expect(result.current.pinned).toEqual(FOUNDING);
    expect(localStorage.getItem(VIEW_PREFS_KEY)).toBeNull();
  });

  it("no-ops for an unpinned id, and writes nothing", () => {
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.movePin("schematic", -1));
    expect(result.current.pinned).toEqual(FOUNDING);
    expect(localStorage.getItem(VIEW_PREFS_KEY)).toBeNull();
  });

  it("no-ops for an unknown id, and writes nothing", () => {
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.movePin("no-such-view" as View, 1));
    expect(result.current.pinned).toEqual(FOUNDING);
    expect(localStorage.getItem(VIEW_PREFS_KEY)).toBeNull();
  });

  it("never calls setItem on a no-op — a genuine reorder is the only thing that writes", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.movePin("antenna", -1)); // front edge
    act(() => result.current.movePin("schematic", 1)); // unpinned
    expect(spy).not.toHaveBeenCalled();
    act(() => result.current.movePin("smith", -1)); // genuine
    expect(spy).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });

  // Cross-window sync (issue #716): movePin persists through the same
  // update() path togglePin/setLayout use, so a reorder in one window fires
  // the ordinary localStorage write, and that write is exactly what #716's
  // `storage` listener (registered once, module scope, in useViewPrefs.ts)
  // relays to every OTHER open window — no reorder-specific wiring needed.
  // This proves the OTHER half: an inbound reorder, arriving as a `storage`
  // event the way #716's own tests simulate one, updates a mounted hook here
  // too.
  it("propagates to another window via the #716 storage listener", () => {
    const { result } = renderHook(() => useViewPrefs());
    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: VIEW_PREFS_KEY,
          newValue: JSON.stringify({
            pinned: ["antenna", "elevation", "azimuth", "smith"],
            seen: FOUNDING,
          }),
        }),
      );
    });
    expect(result.current.pinned).toEqual([
      "antenna",
      "elevation",
      "azimuth",
      "smith",
    ]);
  });
});
