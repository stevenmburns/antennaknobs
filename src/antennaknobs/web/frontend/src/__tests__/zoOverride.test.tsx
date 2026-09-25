// AK#1735: the per-design Zo override store and the gear menu's Zo field.
import { describe, it, expect, vi, afterEach } from "vitest";
import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import {
  isValidZo,
  parseZo,
  setZoOverride,
  useZoOverride,
  ZO_STORAGE_KEY,
} from "../lib/zoOverride";
import { VfoPanel, type ZoControl } from "../components/session/VfoPanel";

afterEach(() => {
  localStorage.clear();
});

describe("parseZo / isValidZo", () => {
  it("takes a positive, finite number of ohms", () => {
    expect(parseZo("75")).toBe(75);
    expect(parseZo(" 12.5 ")).toBe(12.5);
    expect(parseZo("1e3")).toBe(1000);
  });
  it.each(["", "  ", "0", "-50", "abc", "75 ohm", "Infinity", "NaN", "1e400"])(
    "refuses %j",
    (t) => expect(parseZo(t)).toBeNull(),
  );
  it("isValidZo refuses non-numbers", () => {
    expect(isValidZo("75")).toBe(false);
    expect(isValidZo(Number.NaN)).toBe(false);
    expect(isValidZo(0)).toBe(false);
    expect(isValidZo(50)).toBe(true);
  });
});

describe("the per-design store", () => {
  it("reads per design, writes sparsely, and removes the key when empty", () => {
    const { result } = renderHook(() => useZoOverride("a"));
    expect(result.current[0]).toBeNull();
    act(() => result.current[1](75));
    expect(result.current[0]).toBe(75);
    expect(JSON.parse(localStorage.getItem(ZO_STORAGE_KEY)!)).toEqual({ a: 75 });
    act(() => setZoOverride("b", 300));
    expect(JSON.parse(localStorage.getItem(ZO_STORAGE_KEY)!)).toEqual({ a: 75, b: 300 });
    expect(result.current[0]).toBe(75);
    act(() => setZoOverride("b", null));
    act(() => result.current[1](null));
    expect(localStorage.getItem(ZO_STORAGE_KEY)).toBeNull();
  });

  it("survives a reload, and never trusts what it reads back", () => {
    localStorage.setItem(
      ZO_STORAGE_KEY,
      JSON.stringify({ a: 75, b: -1, c: "100", d: 0 }),
    );
    const { result: a } = renderHook(() => useZoOverride("a"));
    expect(a.current[0]).toBe(75);
    for (const g of ["b", "c", "d"]) {
      const { result: other } = renderHook(() => useZoOverride(g));
      expect(other.current[0]).toBeNull();
    }
  });

  it("reads a corrupt record as no overrides", () => {
    localStorage.setItem(ZO_STORAGE_KEY, "{not json");
    const { result } = renderHook(() => useZoOverride("a"));
    expect(result.current[0]).toBeNull();
  });

  it("two mounts on one design agree", () => {
    const { result: one } = renderHook(() => useZoOverride("a"));
    const { result: two } = renderHook(() => useZoOverride("a"));
    act(() => one.current[1](100));
    expect(two.current[0]).toBe(100);
  });
});

function vfoProps(zo?: ZoControl) {
  return {
    currentBands: [],
    measLocked: false,
    measFreq: 14.1,
    bandContaining: () => null,
    measBand: "",
    selectMeasBand: vi.fn(),
    sweepRange: { lo: 11.28, hi: 17.625, spacing: "log" as const },
    setMeasFreq: vi.fn(),
    measLockable: false,
    linkMeas: false,
    toggleLink: vi.fn(),
    autoSim: true,
    setAutoSim: vi.fn(),
    optEnabled: false,
    setOptEnabled: vi.fn(),
    setOptPausedBy: vi.fn(),
    optObjective: "match_z0" as const,
    optSeed: false,
    setOptSeed: vi.fn(),
    setOptObjective: vi.fn(),
    optError: null,
    optPausedBy: null,
    optRunning: false,
    optResult: null,
    optProgress: null,
    trackEnabled: false,
    setTrackEnabled: vi.fn(),
    trackRefusal: null,
    trackLatched: null,
    trackStatus: null,
    zo,
  };
}

const input = () =>
  screen.getByLabelText("Reference impedance Zo, ohms") as HTMLInputElement;

function openWith(zo?: ZoControl) {
  render(<VfoPanel {...vfoProps(zo)} />);
  fireEvent.click(screen.getByLabelText("Optimisation method"));
}

describe("the gear menu's Zo field", () => {
  it("is pre-filled with the session's reference", () => {
    openWith({ value: 75, design: 75, set: vi.fn() });
    expect(input().value).toBe("75");
    expect(screen.queryByRole("button", { name: "reset" })).toBeNull();
  });

  it("commits a valid Zo on Enter, and on blur", () => {
    const set = vi.fn();
    openWith({ value: 50, design: 50, set });
    fireEvent.change(input(), { target: { value: "75" } });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(set).toHaveBeenLastCalledWith(75);
    fireEvent.change(input(), { target: { value: "300" } });
    fireEvent.blur(input());
    expect(set).toHaveBeenLastCalledWith(300);
  });

  it("the design's own value clears the override instead of storing a copy", () => {
    const set = vi.fn();
    openWith({ value: 75, design: 50, set });
    fireEvent.change(input(), { target: { value: "50" } });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(set).toHaveBeenLastCalledWith(null);
  });

  it("refuses bad text visibly and commits nothing; Escape restores", () => {
    const set = vi.fn();
    openWith({ value: 75, design: 50, set });
    fireEvent.change(input(), { target: { value: "-3" } });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(set).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toMatch(/greater than 0/);
    expect(input().getAttribute("aria-invalid")).toBe("true");
    fireEvent.keyDown(input(), { key: "Escape" });
    expect(input().value).toBe("75");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("an override offers a reset to the design's own", () => {
    const set = vi.fn();
    openWith({ value: 75, design: 50, set });
    expect(screen.getByText(/design: 50 Ω/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "reset" }));
    expect(set).toHaveBeenCalledWith(null);
  });

  it("no session behind the panel, no field", () => {
    openWith(undefined);
    expect(screen.queryByLabelText("Reference impedance Zo, ohms")).toBeNull();
  });
});
