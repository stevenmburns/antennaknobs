// EZNEC's VSWR scale (AC6LA, QRZ #166): an alternative to the default
// 1 − 1/SWR, linear in the reflection coefficient ρ = (SWR − 1)/(SWR + 1)
// and labelled in SWR. The transform and its ticks, the stored choice, the
// view-prefs round trip, and the popover button that picks it. The planner
// pin covers it with the other choices in SweepChart.range.test.tsx.
import { useState } from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { SweepChart } from "../components/charts/SweepChart";
import type { SweepData } from "../lib/api";
import {
  axisProjector,
  axisTickMarks,
  DEFAULT_AXES,
  isWholeRange,
  RECIPROCAL,
  RHO,
  sameChoice,
  sanitizeChoice,
  sweepAxisDomain,
  swrRhoY,
  type SweepAxisChoice,
  validChoice,
} from "../lib/sweepAxis";
import { gammaMagFromZ, vswrFromGammaMag } from "../lib/math";
import { useViewPrefs, VIEW_PREFS_KEY } from "../components/session/useViewPrefs";

HTMLCanvasElement.prototype.getContext =
  (() => null) as unknown as HTMLCanvasElement["getContext"];

describe("the transform", () => {
  it("maps SWR 1…∞ onto ρ = 0…1, with 3:1 at mid-axis", () => {
    expect(swrRhoY(1)).toBe(0);
    expect(swrRhoY(3)).toBe(0.5);
    expect(swrRhoY(Infinity)).toBe(1);
    expect(swrRhoY(1.5)).toBeCloseTo(0.2, 12);
    expect(swrRhoY(2)).toBeCloseTo(1 / 3, 12);
    expect(swrRhoY(5)).toBeCloseTo(2 / 3, 12);
    expect(swrRhoY(10)).toBeCloseTo(9 / 11, 12);
    // Garbage and sub-1 read as a perfect match, never off the bottom.
    expect(swrRhoY(0.5)).toBe(0);
    expect(swrRhoY(NaN)).toBe(0);
  });

  it("is |Γ| itself, so the app's capped SWR still sits below the top", () => {
    for (const [re, im] of [[75, 0], [20, 30], [50, 400]] as const) {
      const g = gammaMagFromZ(re, im, 50);
      expect(swrRhoY(vswrFromGammaMag(g))).toBeCloseTo(g, 9);
    }
    expect(swrRhoY(vswrFromGammaMag(1))).toBeLessThan(1);
  });

  it("the projector applies it on the rho choice only; the domain is 0…1", () => {
    expect(axisProjector("vswr", RHO)(3)).toBe(0.5);
    expect(axisProjector("vswr", RECIPROCAL)(3)).toBeCloseTo(2 / 3, 12);
    expect(axisProjector("gamma", RHO)(-10)).toBe(-10);
    expect(sweepAxisDomain("vswr", RHO, [1.1, 40])).toEqual({ lo: 0, hi: 1 });
    expect(isWholeRange(RHO) && isWholeRange(RECIPROCAL)).toBe(true);
    expect(isWholeRange({ kind: "fixed", lo: 1, hi: 3 })).toBe(false);
  });

  it("ticks are labelled in SWR at their ρ positions, ∞ on top", () => {
    const marks = axisTickMarks("vswr", RHO, { lo: 0, hi: 1 });
    expect(marks.map((m) => m.label)).toEqual(["1", "1.5", "2", "3", "5", "10", "∞"]);
    const at = marks.map((m) => m.at);
    [0, 0.2, 1 / 3, 0.5, 2 / 3, 9 / 11, 1].forEach((want, i) =>
      expect(at[i]).toBeCloseTo(want, 12),
    );
  });
});

describe("the stored choice", () => {
  it("is valid for VSWR only, and distrusted on the way back in", () => {
    expect(validChoice("vswr", RHO)).toBe(true);
    expect(validChoice("gamma", RHO)).toBe(false);
    expect(sanitizeChoice("vswr", { kind: "rho" })).toEqual(RHO);
    expect(sanitizeChoice("gamma", { kind: "rho" })).toEqual({ kind: "auto" });
    expect(sameChoice(RHO, { kind: "rho" })).toBe(true);
    expect(sameChoice(RHO, RECIPROCAL)).toBe(false);
  });

  it("1 − 1/SWR stays the default", () => {
    expect(DEFAULT_AXES.vswr).toEqual(RECIPROCAL);
  });
});

describe("the view-prefs round trip", () => {
  beforeEach(() => localStorage.clear());

  it("stores rho, reads it back, and leaves storage on return to the default", () => {
    const h = renderHook(() => useViewPrefs());
    act(() => h.result.current.setSweepAxis("vswr", RHO));
    const stored = JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "{}");
    expect(stored.sweepAxes).toEqual({ vswr: { kind: "rho" } });
    h.unmount();
    const again = renderHook(() => useViewPrefs());
    expect(again.result.current.sweepAxes.vswr).toEqual(RHO);
    act(() => again.result.current.setSweepAxis("vswr", RECIPROCAL));
    const after = JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "{}");
    expect(after.sweepAxes).toBeUndefined();
    again.unmount();
  });
});

// A resonance whose band edges reach SWR ~18.
const FREQS = Array.from({ length: 21 }, (_, i) => 13.7 + i * 0.05);
const SWEEP: SweepData = {
  freqs_mhz: FREQS,
  z_re: FREQS.map(() => 50),
  z_im: FREQS.map((f) => 400 * (f - 14.2)),
};

function Stateful({ start }: { start: SweepAxisChoice }) {
  const [axis, setAxis] = useState<SweepAxisChoice>(start);
  return (
    <SweepChart
      mode="vswr"
      r={0}
      x={0}
      z0={50}
      size={236}
      sweep={SWEEP}
      measFreqMhz={14.2}
      running={false}
      multiFeed={false}
      axis={axis}
      onAxisChange={setAxis}
    />
  );
}

const canvas = () => document.querySelector("canvas.sweep") as HTMLCanvasElement;

describe("the popover's EZNEC button", () => {
  it("switches the chart to ρ and back, ticks labelled in SWR", () => {
    render(<Stateful start={RECIPROCAL} />);
    fireEvent.click(screen.getByRole("button", { name: "VSWR range and SWR threshold" }));
    const rho = screen.getByRole("button", { name: "ρ (EZNEC)" });
    expect(rho.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(rho);
    expect(canvas().dataset.axis).toBe("rho");
    expect(canvas().dataset.ticks).toBe("1,1.5,2,3,5,10,∞");
    expect(screen.getByRole("button", { name: "ρ (EZNEC)" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    // A sample's drawn height is its |Γ|: z = 50 + j0 at 14.2 MHz is 0.
    const frac = (canvas().dataset.yFrac ?? "").split(",").map(Number);
    const ys = (canvas().dataset.yValues ?? "").split(",").map(Number);
    ys.forEach((y, i) => expect(frac[i]).toBeCloseTo((y - 1) / (y + 1), 3));
    fireEvent.click(screen.getByRole("button", { name: "1–∞" }));
    expect(canvas().dataset.axis).toBe("reciprocal");
  });

  it("is VSWR's only: the S11 popover has no ρ button", () => {
    render(
      <SweepChart
        mode="gamma"
        r={0}
        x={0}
        z0={50}
        size={236}
        sweep={SWEEP}
        measFreqMhz={14.2}
        running={false}
        multiFeed={false}
        onAxisChange={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "S11 range and SWR threshold" }));
    expect(screen.queryByRole("button", { name: "ρ (EZNEC)" })).toBeNull();
  });
});
