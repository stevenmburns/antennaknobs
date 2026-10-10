// The Smith chart's admittance-grid preference: off by default, persisted
// with the other view prefs, and sparse — only "on" is written.
import { describe, it, expect, beforeEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { VIEW_PREFS_KEY, useViewPrefs } from "../components/session/useViewPrefs";

beforeEach(() => {
  localStorage.clear();
});

const stored = () => JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "null");

describe("Smith admittance grid preference", () => {
  it("defaults to off", () => {
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.smithYGrid).toBe(false);
  });

  it("persists on, survives a remount, and drops the key when turned off", () => {
    const first = renderHook(() => useViewPrefs());
    act(() => first.result.current.setSmithYGrid(true));
    expect(stored().smithYGrid).toBe(true);
    first.unmount();
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.smithYGrid).toBe(true);
    act(() => result.current.setSmithYGrid(false));
    expect(Object.keys(stored()).sort()).toEqual(["pinned", "seen"]);
  });

  it("reads anything but the literal true as off", () => {
    for (const bad of ["true", 1, null, {}]) {
      localStorage.setItem(
        VIEW_PREFS_KEY,
        JSON.stringify({ pinned: ["zparam"], seen: ["zparam"], smithYGrid: bad }),
      );
      const { result, unmount } = renderHook(() => useViewPrefs());
      expect(result.current.smithYGrid).toBe(false);
      expect(result.current.pinned).toEqual(["zparam"]);
      unmount();
    }
  });
});
