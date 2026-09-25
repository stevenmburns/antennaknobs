// Pins the combined Az + El view's fill preference (AK#1730): it defaults to
// "none" (EZNEC's look), persists with the other view prefs, and the stored
// record stays sparse — the default is never written, so a session that never
// touches the fill keeps the exact `{pinned, seen}` shape.
import { describe, it, expect, beforeEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { VIEW_PREFS_KEY, useViewPrefs } from "../components/session/useViewPrefs";

beforeEach(() => {
  localStorage.clear();
});

const stored = () => JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "null");

describe("combined view fill preference", () => {
  it("defaults to none", () => {
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.combinedFill).toBe("none");
  });

  it("persists a change and survives a remount (a reload, to the store)", () => {
    const first = renderHook(() => useViewPrefs());
    act(() => first.result.current.setCombinedFill("elevation"));
    expect(first.result.current.combinedFill).toBe("elevation");
    expect(stored().combinedFill).toBe("elevation");
    first.unmount();
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.combinedFill).toBe("elevation");
  });

  it("writes nothing for the default, and drops the key when set back to it", () => {
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.setCombinedFill("none")); // already the default
    expect(localStorage.getItem(VIEW_PREFS_KEY)).toBeNull();
    act(() => result.current.setCombinedFill("elevation"));
    act(() => result.current.setCombinedFill("none"));
    expect(Object.keys(stored()).sort()).toEqual(["pinned", "seen"]);
  });

  it("reads garbage as the default without condemning the record", () => {
    for (const bad of ["both", "az", 1, null, ["elevation"]]) {
      localStorage.setItem(
        VIEW_PREFS_KEY,
        JSON.stringify({ pinned: ["smith"], seen: ["smith"], combinedFill: bad }),
      );
      const { result, unmount } = renderHook(() => useViewPrefs());
      expect(result.current.combinedFill).toBe("none");
      expect(result.current.pinned).toEqual(["smith"]);
      unmount();
    }
  });
});
