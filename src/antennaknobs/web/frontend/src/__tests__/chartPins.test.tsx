// Pinned sweeps on the charts and in the legend (AK#1757 item 1): a pin
// draws on the Swr / S11 chart at ITS OWN Z0 (ruling 4), on the R / X plot
// and on the Smith chart, the hover reads each pin beside the live curve,
// the legend lists every pin with show / hide, CSV and delete, greyed with
// its reason where it cannot draw; and the shell's list mints one pin per
// curve with global show / hide. jsdom has no 2-D context, so the render-time
// data-* output is what is asserted.
//
// Mutation notes (run by hand, 2026-09-30; each reverted after):
//   - SweepChart drawing a pin at the chart's z0 instead of its own:
//     "a 50 Ω pin on a 75 Ω chart reads its 50 Ω SWR" fails;
//   - legendShown ignoring pins: "a one-curve chart with a pin shows its
//     legend…" fails.
import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { useContext } from "react";
import { SmithChart } from "../components/charts/SmithChart";
import { SweepChart } from "../components/charts/SweepChart";
import { ZParamChart } from "../components/charts/ZParamChart";
import { ChartLegend, type ChartLegendData, chipText, legendShown } from "../components/results/ChartLegend";
import { type SweepPinsCtx, SweepPinsContext } from "../components/session/contexts";
import { SweepPinsProvider } from "../components/session/SweepPinsProvider";
import type { SweepData } from "../lib/api";
import { FREQUENCY_X, type PinCurve, pinsFromCurves, swrAt } from "../lib/sweepPins";

HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement["getContext"];

const FREQS = [14.0, 14.1, 14.2, 14.3, 14.4];
// The live curve: 75 Ω flat, a perfect match on a 75 Ω chart.
const LIVE: SweepData = { freqs_mhz: FREQS, z_re: FREQS.map(() => 75), z_im: FREQS.map(() => 0) };
// A pin taken at 50 Ω of a 50 Ω flat curve: SWR 1 at its own reference,
// 1.5 at the chart's 75 Ω.
const PIN50: PinCurve = {
  id: "p0",
  color: "rgba(1, 2, 3, 0.95)",
  label: "d · NEC-5 · free space",
  xs: FREQS,
  zRe: FREQS.map(() => 50),
  zIm: FREQS.map(() => 0),
  z0: 50,
};

// jsdom has no PointerEvent: a MouseEvent of the pointer type carries the
// coordinates React reads (ZParamChart.test.tsx's way).
const move = (c: HTMLElement, clientX: number) =>
  act(() => {
    fireEvent(c, new MouseEvent("pointermove", { clientX, clientY: 50, bubbles: true }));
  });

const sweepChart = (pins: PinCurve[], mode: "vswr" | "gamma" = "vswr") =>
  render(
    <SweepChart
      mode={mode}
      r={75}
      x={0}
      z0={75}
      size={200}
      sweep={LIVE}
      measFreqMhz={14.2}
      running={false}
      multiFeed={false}
      pins={pins}
    />,
  );

describe("a pin on the Swr / S11 chart", () => {
  it("a 50 Ω pin on a 75 Ω chart reads its 50 Ω SWR, not the chart's", () => {
    const { container } = sweepChart([PIN50]);
    const c = container.querySelector<HTMLCanvasElement>("canvas.sweep")!;
    expect(c.dataset.pins).toBe("p0:5");
    // SWR 1 at 50 Ω everywhere; 1.5 would be the chart's Z0.
    expect(c.dataset.pinY).toBe("1.0000,1.0000,1.0000,1.0000,1.0000");
    expect(swrAt(50, 0, 75)).toBeCloseTo(1.5, 9);
    // The live curve is at the chart's Z0.
    expect(c.dataset.yValues).toBe("1.0000,1.0000,1.0000,1.0000,1.0000");
  });

  it("S11 too: a pin 75 Ω at 50 is −14 dB whatever the chart's reference", () => {
    const pin = { ...PIN50, zRe: FREQS.map(() => 75) };
    const { container } = sweepChart([pin], "gamma");
    const c = container.querySelector<HTMLCanvasElement>("canvas.sweep")!;
    // |Γ| = 25/125 = 0.2 ⇒ 20·log10(0.2) = −13.98 dB.
    expect(c.dataset.pinY?.split(",")[0]).toBe("-13.9794");
  });

  it("the hover reads each pin at the hovered frequency beside the live curve", () => {
    const pin = { ...PIN50, zRe: [50, 50, 100, 100, 100] };
    const { container } = sweepChart([pin]);
    const c = container.querySelector<HTMLCanvasElement>("canvas.sweep")!;
    // The plot's x runs from 26 px to 200 − 8 px (jsdom's rect is at 0):
    // halfway is 14.2 MHz, a third of the way from 14.1 to 14.2 is 14.1333.
    move(c, 26 + 166 * (1 / 3));
    expect(Number(c.dataset.hover)).toBeCloseTo(14.1333, 3);
    expect(c.dataset.hoverOwn).toBe("1.0000");
    // R 66.67 Ω at 50 Ω: SWR 1.3333.
    expect(c.dataset.hoverPins).toBe("p0:1.3333");
    fireEvent.pointerLeave(c);
    expect(c.dataset.hover).toBe("");
  });
});

describe("a pin on the R / X plot and the Smith chart", () => {
  it("draws on R / X, which fits it, and the hover reads it at the hovered x", () => {
    const pin = { ...PIN50, zRe: [200, 200, 200, 200, 200], zIm: [-100, -50, 0, 50, 100] };
    const { container } = render(
      <ZParamChart
        data={{ param: "frequency", label: "f", values: FREQS, z_re: LIVE.z_re, z_im: LIVE.z_im, z_re_extrap: null, z_im_extrap: null }}
        param="frequency"
        label="f"
        unit="MHz"
        total={5}
        currentValue={null}
        liveR={null}
        liveX={null}
        size={200}
        running={false}
        xLog={false}
        pins={[pin]}
      />,
    );
    const c = container.querySelector<HTMLCanvasElement>("canvas.zparam")!;
    expect(c.dataset.pins).toBe("p0:5");
    // The R range takes the pin's 200 Ω in.
    expect(Number(c.dataset.rHi)).toBeGreaterThanOrEqual(200);
    // The plot spans x 46…154 on a 200 px chart: its left edge is the first
    // point, 14.0 MHz, where the pin reads 200 − j100 Ω.
    move(c, 46);
    expect(c.dataset.hover).toBe("0");
    expect(c.dataset.hoverPins).toBe("p0:200.000,-100.000");
    // Off the plot: nothing hovered.
    move(c, 10_000);
    expect(c.dataset.hoverPins).toBe("");
  });

  it("draws on the Smith chart", () => {
    const { container } = render(
      <SmithChart
        r={75}
        x={0}
        z0={75}
        size={200}
        sweep={LIVE}
        paramSweep={null}
        measured={null}
        measFreqMhz={14.2}
        running={false}
        paramSweepRunning={false}
        multiFeed={false}
        pins={[PIN50]}
      />,
    );
    expect(container.querySelector<HTMLCanvasElement>("canvas.smith")!.dataset.pins).toBe("p0:5");
  });
});

const pinRow = (over: Partial<NonNullable<ChartLegendData["pins"]>[number]> = {}) => ({
  id: "p0",
  label: "d · NEC-5 · free space",
  cell: "",
  color: "rgb(1, 2, 3)",
  enabled: true,
  reason: null,
  z0Note: null,
  onToggle: vi.fn(),
  onDelete: vi.fn(),
  onCsv: vi.fn(),
  ...over,
});

describe("the legend's pins section", () => {
  const ONE: ChartLegendData = {
    entries: [{ key: "A", label: "A: NEC-5", color: "#f00", refused: null }],
    capRefusal: null,
  };

  it("a one-curve chart with a pin shows its legend; without, it does not", () => {
    expect(legendShown(ONE)).toBe(false);
    expect(legendShown({ ...ONE, pins: [pinRow()] })).toBe(true);
    expect(chipText({ ...ONE, pins: [pinRow(), pinRow({ id: "p1" })] })).toBe("1 curve · 2 pins ▾");
  });

  it("lists each pin with its Z0 note, greys one that cannot draw with why, and wires its controls", () => {
    const a = pinRow({ z0Note: "Z0 50 Ω" });
    const b = pinRow({ id: "p1", label: "d · PyNEC", reason: "sweeps height; this chart sweeps frequency" });
    const c = pinRow({ id: "p2", label: "d · hidden", enabled: false });
    render(<ChartLegend legend={{ ...ONE, pins: [a, b, c] }} />);
    const rows = [...document.querySelectorAll<HTMLElement>(".chart-legend-pin")];
    expect(rows.map((r) => [r.dataset.pin, r.dataset.drawable, r.dataset.enabled, r.className])).toEqual([
      ["p0", "1", "1", "chart-legend-pin"],
      ["p1", "0", "1", "chart-legend-pin is-greyed"],
      ["p2", "1", "0", "chart-legend-pin is-greyed"],
    ]);
    expect(rows[0].textContent).toContain("d · NEC-5 · free space · Z0 50 Ω");
    expect(rows[1].textContent).toContain(": sweeps height; this chart sweeps frequency");
    // The live curve's row is unchanged (the pin rows are their own class).
    expect(document.querySelectorAll(".chart-legend-row")).toHaveLength(1);

    fireEvent.click(screen.getByRole("checkbox", { name: "Show pin d · NEC-5 · free space" }));
    expect(a.onToggle).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Export pin d · NEC-5 · free space as CSV" }));
    expect(a.onCsv).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Delete pin d · PyNEC" }));
    expect(b.onDelete).toHaveBeenCalledTimes(1);
    expect(a.onDelete).not.toHaveBeenCalled();
  });
});

describe("the shell's pin list", () => {
  function Probe({ onCtx }: { onCtx: (c: SweepPinsCtx) => void }) {
    onCtx(useContext(SweepPinsContext));
    return null;
  }

  it("adds one pin per curve in the smallest free slots; show / hide is one global flag", () => {
    let ctx: SweepPinsCtx | null = null;
    render(
      <SweepPinsProvider>
        <Probe onCtx={(c) => (ctx = c)} />
      </SweepPinsProvider>,
    );
    const snaps = pinsFromCurves(
      [0, 1, 2].map((k) => ({
        xs: FREQS,
        zRe: FREQS.map(() => 50 + k),
        zIm: FREQS.map(() => 0),
        x: FREQUENCY_X,
        label: `cell ${k}`,
        cell: `cell ${k}`,
        design: "d",
      })),
      50,
    );
    act(() => ctx!.addPins(snaps));
    expect(ctx!.pins.map((p) => [p.label, p.colorIdx, p.enabled])).toEqual([
      ["cell 0", 0, true],
      ["cell 1", 1, true],
      ["cell 2", 2, true],
    ]);
    const ids = ctx!.pins.map((p) => p.id);
    expect(new Set(ids).size).toBe(3);
    act(() => ctx!.togglePin(ids[1]));
    expect(ctx!.pins.map((p) => p.enabled)).toEqual([true, false, true]);
    act(() => ctx!.removePin(ids[0]));
    act(() => ctx!.addPins(snaps.slice(0, 1)));
    // Slot 0 was freed and is reused; the others keep theirs.
    expect(ctx!.pins.map((p) => p.colorIdx)).toEqual([1, 2, 0]);
  });
});
