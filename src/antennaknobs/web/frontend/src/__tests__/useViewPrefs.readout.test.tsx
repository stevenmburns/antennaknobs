// Pins the stage readout's per-view minimize preference: every view starts on
// its registry default (VIEW_META.readoutStartsCollapsed), a viewer's choice is
// remembered per view and survives a reload, and the stored record stays
// sparse. A choice equal to the default is not written, so a session that never
// touches the readout keeps the exact `{pinned, seen}` shape.
import { describe, it, expect, beforeEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { VIEWS } from "../lib/view";
import { VIEW_PREFS_KEY, useViewPrefs } from "../components/session/useViewPrefs";

beforeEach(() => {
  localStorage.clear();
});

const stored = () => JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "null");

describe("readout minimize preference", () => {
  it("starts every view on its registry default", () => {
    const { result } = renderHook(() => useViewPrefs());
    for (const v of VIEWS) {
      expect(result.current.isReadoutCollapsed(v.id)).toBe(v.readoutStartsCollapsed);
    }
    expect(result.current.isReadoutCollapsed("files")).toBe(true);
    expect(result.current.isReadoutCollapsed("antenna")).toBe(false);
  });

  it("remembers a choice per view, and only for that view", () => {
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.setReadoutCollapsed("antenna", true));
    expect(result.current.isReadoutCollapsed("antenna")).toBe(true);
    expect(result.current.isReadoutCollapsed("smith")).toBe(false);
    expect(stored().readoutCollapsed).toEqual({ antenna: true });
  });

  it("survives a remount, which is what a reload is to the store", () => {
    const first = renderHook(() => useViewPrefs());
    act(() => first.result.current.setReadoutCollapsed("files", false));
    first.unmount();
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.isReadoutCollapsed("files")).toBe(false);
  });

  it("writes nothing for a choice equal to the default, and drops one set back to it", () => {
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.setReadoutCollapsed("files", true)); // already the default
    expect(localStorage.getItem(VIEW_PREFS_KEY)).toBeNull();
    act(() => result.current.setReadoutCollapsed("antenna", true));
    act(() => result.current.setReadoutCollapsed("antenna", false));
    expect(Object.keys(stored()).sort()).toEqual(["pinned", "seen"]);
  });

  it("drops stored garbage entry by entry", () => {
    localStorage.setItem(
      VIEW_PREFS_KEY,
      JSON.stringify({
        pinned: ["antenna"],
        seen: ["antenna"],
        readoutCollapsed: { antenna: true, nosuchview: true, smith: "yes" },
      }),
    );
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.isReadoutCollapsed("antenna")).toBe(true);
    expect(result.current.isReadoutCollapsed("smith")).toBe(false);
  });

  it("a map that is garbage as a whole leaves every view on its default", () => {
    localStorage.setItem(
      VIEW_PREFS_KEY,
      JSON.stringify({ pinned: ["antenna"], seen: ["antenna"], readoutCollapsed: ["antenna"] }),
    );
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.isReadoutCollapsed("antenna")).toBe(false);
    expect(result.current.isReadoutCollapsed("files")).toBe(true);
  });
});
