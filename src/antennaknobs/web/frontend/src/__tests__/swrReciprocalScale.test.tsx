// The compressed VSWR scale, y = 1 − 1/SWR (Steve, 2026-09-26): the pure
// transform and its ticks, the stored-choice validation, and the view-prefs
// round trip. The drawn chart and the planner pin are in
// SweepChart.range.test.tsx.
import { describe, it, expect, beforeEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import {
  axisProjector,
  axisTickMarks,
  RECIPROCAL,
  sameChoice,
  sanitizeChoice,
  sweepAxisDomain,
  swrReciprocalY,
  validChoice,
} from "../lib/sweepAxis";
import { gammaMagFromZ, vswrFromGammaMag } from "../lib/math";
import { useViewPrefs, VIEW_PREFS_KEY } from "../components/session/useViewPrefs";

describe("the transform", () => {
  it("maps SWR 1…∞ onto 0…1 at the values hams read", () => {
    expect(swrReciprocalY(1)).toBe(0);
    expect(swrReciprocalY(1.5)).toBeCloseTo(1 / 3, 12);
    expect(swrReciprocalY(2)).toBe(0.5);
    expect(swrReciprocalY(3)).toBeCloseTo(2 / 3, 12);
    expect(swrReciprocalY(5)).toBeCloseTo(0.8, 12);
    expect(swrReciprocalY(10)).toBeCloseTo(0.9, 12);
    expect(swrReciprocalY(Infinity)).toBe(1);
    // Garbage and sub-1 read as a perfect match, never off the bottom.
    expect(swrReciprocalY(0.5)).toBe(0);
    expect(swrReciprocalY(NaN)).toBe(0);
  });

  it("is 2|Γ|/(1+|Γ|), so the app's capped SWR of 99 still sits below the top", () => {
    for (const [re, im] of [[75, 0], [20, 30], [50, 400]] as const) {
      const g = gammaMagFromZ(re, im, 50);
      expect(swrReciprocalY(vswrFromGammaMag(g))).toBeCloseTo((2 * g) / (1 + g), 9);
    }
    expect(swrReciprocalY(vswrFromGammaMag(1))).toBeLessThan(1);
  });

  it("the projector applies it on VSWR's compressed choice only", () => {
    expect(axisProjector("vswr", RECIPROCAL)(2)).toBe(0.5);
    // VSWR has no Auto; a stray one projects as the 1–∞ scale.
    expect(axisProjector("vswr", { kind: "auto" })(2)).toBe(0.5);
    expect(axisProjector("vswr", { kind: "fixed", lo: 1, hi: 3 })(2)).toBe(2);
    expect(axisProjector("gamma", { kind: "auto" })(-10)).toBe(-10);
    expect(sweepAxisDomain("vswr", RECIPROCAL, [1.1, 40])).toEqual({ lo: 0, hi: 1 });
  });

  it("ticks are labelled in SWR at 1, 1.5, 2, 3, 5, 10, with ∞ on top", () => {
    const marks = axisTickMarks("vswr", RECIPROCAL, { lo: 0, hi: 1 });
    expect(marks.map((m) => m.label)).toEqual(["1", "1.5", "2", "3", "5", "10", "∞"]);
    const at = marks.map((m) => m.at);
    [0, 1 / 3, 0.5, 2 / 3, 0.8, 0.9, 1].forEach((want, i) => expect(at[i]).toBeCloseTo(want, 12));
    // Any other choice keeps the linear numbers.
    expect(axisTickMarks("vswr", { kind: "fixed", lo: 1, hi: 3 }, { lo: 1, hi: 3 }).map((m) => m.label))
      .toEqual(["1", "1.5", "2", "2.5", "3"]);
  });
});

describe("the stored choice", () => {
  it("is valid for VSWR only, and distrusted on the way back in", () => {
    expect(validChoice("vswr", RECIPROCAL)).toBe(true);
    expect(validChoice("gamma", RECIPROCAL)).toBe(false);
    expect(sanitizeChoice("vswr", { kind: "reciprocal" })).toEqual(RECIPROCAL);
    expect(sanitizeChoice("gamma", { kind: "reciprocal" })).toEqual({ kind: "auto" });
    // Garbage reads as the mode's default: 1–∞ on VSWR.
    expect(sanitizeChoice("vswr", { kind: "reciprocl" })).toEqual(RECIPROCAL);
    expect(sanitizeChoice("vswr", undefined)).toEqual(RECIPROCAL);
    // VSWR has no Auto any more: a stored one migrates to 1–∞. S11 keeps it.
    expect(validChoice("vswr", { kind: "auto" })).toBe(false);
    expect(sanitizeChoice("vswr", { kind: "auto" })).toEqual(RECIPROCAL);
    expect(sanitizeChoice("gamma", { kind: "auto" })).toEqual({ kind: "auto" });
    expect(sameChoice(RECIPROCAL, { kind: "reciprocal" })).toBe(true);
    expect(sameChoice(RECIPROCAL, { kind: "auto" })).toBe(false);
  });
});

describe("the view-prefs round trip", () => {
  beforeEach(() => localStorage.clear());

  it("a fresh profile starts VSWR on 1–∞ and S11 on Auto", () => {
    const h = renderHook(() => useViewPrefs());
    expect(h.result.current.sweepAxes).toEqual({ vswr: RECIPROCAL, gamma: { kind: "auto" } });
    h.unmount();
  });

  it("migrates a stored VSWR Auto to 1–∞, and refuses to store a new one", () => {
    // A profile saved while VSWR still had Auto (it was stored explicitly).
    localStorage.setItem(
      VIEW_PREFS_KEY,
      JSON.stringify({ pinned: ["vswr"], seen: ["vswr"], sweepAxes: { vswr: { kind: "auto" } } }),
    );
    const h = renderHook(() => useViewPrefs());
    expect(h.result.current.sweepAxes.vswr).toEqual(RECIPROCAL);
    // Auto is not a VSWR choice: the setter refuses it.
    act(() => h.result.current.setSweepAxis("vswr", { kind: "fixed", lo: 1, hi: 3 }));
    act(() => h.result.current.setSweepAxis("vswr", { kind: "auto" }));
    expect(h.result.current.sweepAxes.vswr).toEqual({ kind: "fixed", lo: 1, hi: 3 });
    // Back to 1–∞, the default: the entry leaves storage.
    act(() => h.result.current.setSweepAxis("vswr", RECIPROCAL));
    const after = JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "{}");
    expect(after.sweepAxes).toBeUndefined();
    h.unmount();
  });

  it("an explicit preset still wins over the default", () => {
    localStorage.setItem(
      VIEW_PREFS_KEY,
      JSON.stringify({ pinned: ["vswr"], seen: ["vswr"], sweepAxes: { vswr: { kind: "fixed", lo: 1, hi: 3 } } }),
    );
    const h = renderHook(() => useViewPrefs());
    expect(h.result.current.sweepAxes.vswr).toEqual({ kind: "fixed", lo: 1, hi: 3 });
    h.unmount();
  });

  it("refuses it for S11, and a hand-edited S11 entry reads back as Auto", () => {
    const h = renderHook(() => useViewPrefs());
    act(() => h.result.current.setSweepAxis("gamma", RECIPROCAL));
    expect(h.result.current.sweepAxes.gamma).toEqual({ kind: "auto" });
    h.unmount();
    localStorage.setItem(
      VIEW_PREFS_KEY,
      JSON.stringify({ pinned: ["vswr"], seen: ["vswr"], sweepAxes: { gamma: { kind: "reciprocal" } } }),
    );
    const again = renderHook(() => useViewPrefs());
    expect(again.result.current.sweepAxes.gamma).toEqual({ kind: "auto" });
    again.unmount();
  });
});
