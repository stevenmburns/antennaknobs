// Issue #716, deferred from #700 (docs/plan-view-rail-scaling.md unit 2):
// useViewPrefs already shares one module store across every session tab in
// ONE window (see useViewPrefs.ts's module-store comment), but two browser
// WINDOWS only used to converge on reload. A `storage` event fires in every
// OTHER window sharing this origin the instant localStorage actually
// changes — never in the window that wrote it — so it's the signal that
// closes that gap. jsdom does not fire it for us on a same-document
// `setItem` (real browsers only fire it cross-window too), so every test
// here dispatches the event by hand, exactly as a real second window's
// write would arrive at this one.
//
// A separate file rather than additions to useViewPrefs.test.tsx: that file
// is the pre-existing baseline unit 2 shipped and unit 3 kept passing
// UNEDITED (see useViewPrefs.grid.test.tsx's header for why it also lives
// apart), so this arc gets its own file too.
import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { VIEW_PREFS_KEY, useViewPrefs } from "../components/session/useViewPrefs";

const FOUNDING = ["antenna", "azimuth", "elevation", "smith"];

beforeEach(() => {
  localStorage.clear();
});

// Fires the event this suite is about: a same-key storage change arriving
// from another window. Real browsers set `storageArea`/`url` too, but the
// module only reads `key` and `newValue`, so those are all any test needs.
function fireStorage(key: string | null, newValue: string | null) {
  act(() => {
    window.dispatchEvent(new StorageEvent("storage", { key, newValue }));
  });
}

describe("storage event: valid payload from another window", () => {
  it("updates a mounted hook's pinned set", () => {
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.pinned).toEqual(FOUNDING);

    fireStorage(VIEW_PREFS_KEY, '{"pinned":["smith","antenna"],"seen":["antenna"]}');

    expect(result.current.pinned).toEqual(["smith", "antenna"]);
  });

  it("updates layout too", () => {
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.layout).toBe("rail");

    fireStorage(
      VIEW_PREFS_KEY,
      '{"pinned":["smith"],"seen":["smith"],"layout":"grid"}',
    );

    expect(result.current.layout).toBe("grid");
  });
});

describe("storage event: unrelated key", () => {
  it("is ignored — state is untouched", () => {
    const { result } = renderHook(() => useViewPrefs());
    const before = result.current.pinned;

    fireStorage("some.other.key", '{"pinned":["smith"],"seen":["smith"]}');

    expect(result.current.pinned).toBe(before); // same array identity: no re-render fired
  });
});

describe("storage event: corrupt or invalid payload", () => {
  const bad = [
    ["corrupt JSON", "{not json"],
    ["a bare array", '["antenna"]'],
    ["no pinned field", '{"seen":["antenna"]}'],
    ["only unknown ids", '{"pinned":["bogus","no-such-view"]}'],
    ["an empty pin set", '{"pinned":[]}'],
  ] as const;

  for (const [what, raw] of bad) {
    it(`ignores ${what} — state is unchanged`, () => {
      const { result } = renderHook(() => useViewPrefs());
      const before = result.current.pinned;

      fireStorage(VIEW_PREFS_KEY, raw);

      expect(result.current.pinned).toBe(before);
    });
  }
});

describe("storage event: null newValue (key removed / storage.clear())", () => {
  it("resets to the same defaults loadPrefs uses for a missing key", () => {
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.togglePin("schematic"));
    expect(result.current.pinned).toEqual([...FOUNDING, "schematic"]);

    fireStorage(VIEW_PREFS_KEY, null);

    expect(result.current.pinned).toEqual(FOUNDING);
  });

  it("also resets on key === null (storage.clear())", () => {
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.togglePin("schematic"));

    fireStorage(null, null);

    expect(result.current.pinned).toEqual(FOUNDING);
  });
});

describe("storage event: no echo", () => {
  it("applying a received state does not write back to localStorage", () => {
    const { result } = renderHook(() => useViewPrefs());
    const spy = vi.spyOn(Storage.prototype, "setItem");

    fireStorage(VIEW_PREFS_KEY, '{"pinned":["smith","antenna"],"seen":["antenna"]}');

    expect(result.current.pinned).toEqual(["smith", "antenna"]);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  it("does not write back even when the payload is a reset (null newValue)", () => {
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.togglePin("schematic"));
    const spy = vi.spyOn(Storage.prototype, "setItem");

    fireStorage(VIEW_PREFS_KEY, null);

    expect(result.current.pinned).toEqual(FOUNDING);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
