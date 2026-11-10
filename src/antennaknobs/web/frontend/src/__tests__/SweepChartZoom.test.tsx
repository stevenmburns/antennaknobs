// Pins the SWR / S11 charts' frequency zoom (SweepChart.tsx + lib/
// sweepView.ts): a band click, a drag, Ctrl+wheel / pinch and + / − zoom the
// axis; a PLAIN wheel is never taken (it scrolls the page and turns knobs);
// double-click, Esc and the chip go back to the whole sweep; the window
// survives a re-solve of one design and is dropped on a design switch; Auto
// fits only what the window shows; "Sweep this span" hands the window to the
// range edit; a thumbnail gets none of it. jsdom has no canvas pixels, so
// data-view-lo / data-view-hi / data-zoomed / data-y-lo are the seam.
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { SweepChart } from "../components/charts/SweepChart";
import type { SweepData } from "../lib/api";
import { BAND_MARGIN } from "../lib/sweepView";

HTMLCanvasElement.prototype.getContext =
  (() => null) as unknown as HTMLCanvasElement["getContext"];

// 334 px at chart scale 1: the plot runs x = 26 … 326, 300 px for 13–15 MHz.
const SIZE = 334;
const xAt = (f: number) => 26 + ((f - 13) / 2) * 300;

// A dip at 14.2 MHz: matched there, a poor match (S11 ≈ −2.6 dB) at 13 MHz.
function sweepOf(scale = 300): SweepData {
  const freqs_mhz = Array.from({ length: 41 }, (_, i) => 13 + i * 0.05);
  return {
    freqs_mhz,
    z_re: freqs_mhz.map((f) => 50 + scale * Math.abs(f - 14.2)),
    z_im: freqs_mhz.map(() => 0),
  };
}

const TWENTY = { label: "20m", lo: 14, hi: 14.35 };

function props(over: Partial<ComponentProps<typeof SweepChart>> = {}): ComponentProps<typeof SweepChart> {
  return {
    mode: "gamma",
    r: 50,
    x: 0,
    z0: 50,
    size: SIZE,
    sweep: sweepOf(),
    measFreqMhz: 14.2,
    running: false,
    multiFeed: false,
    axis: { kind: "auto" },
    hamBands: [TWENTY],
    interactive: true,
    designKey: "dipole",
    ...over,
  };
}

const canvasOf = (c: HTMLElement) => c.querySelector("canvas.sweep") as HTMLCanvasElement;
const viewOf = (c: HTMLElement) => {
  const el = canvasOf(c);
  return {
    lo: Number(el.getAttribute("data-view-lo")),
    hi: Number(el.getAttribute("data-view-hi")),
    zoomed: el.getAttribute("data-zoomed") === "1",
  };
};

const press = (el: Element, x: number, id = 1, pointerType = "mouse") =>
  fireEvent.pointerDown(el, { clientX: x, clientY: 100, pointerId: id, pointerType, button: 0 });
const move = (el: Element, x: number, id = 1, pointerType = "mouse") =>
  fireEvent.pointerMove(el, { clientX: x, clientY: 100, pointerId: id, pointerType });
const lift = (el: Element, x: number, id = 1, pointerType = "mouse") =>
  fireEvent.pointerUp(el, { clientX: x, clientY: 100, pointerId: id, pointerType });
const click = (el: Element, x: number) => {
  press(el, x);
  lift(el, x);
};
const drag = (el: Element, x0: number, x1: number) => {
  press(el, x0);
  move(el, (x0 + x1) / 2);
  move(el, x1);
  lift(el, x1);
};

describe("zooming the frequency axis", () => {
  it("starts on the whole sweep", () => {
    const { container } = render(<SweepChart {...props()} />);
    expect(viewOf(container)).toEqual({ lo: 13, hi: 15, zoomed: false });
    expect(screen.queryByRole("group", { name: "Frequency zoom" })).toBeNull();
  });

  it("zooms to a ham band, with its margin, on a click inside it", () => {
    const { container } = render(<SweepChart {...props()} />);
    click(canvasOf(container), xAt(14.175));
    const v = viewOf(container);
    expect(v.zoomed).toBe(true);
    expect(v.lo).toBeCloseTo(14 - BAND_MARGIN * 0.35, 9);
    expect(v.hi).toBeCloseTo(14.35 + BAND_MARGIN * 0.35, 9);
    // The chip names the window.
    expect(screen.getByTestId("sweep-zoom-span").textContent).toBe("13.965–14.385 MHz");
  });

  it("a click outside every band does nothing", () => {
    const { container } = render(<SweepChart {...props()} />);
    click(canvasOf(container), xAt(13.5));
    expect(viewOf(container).zoomed).toBe(false);
  });

  it("zooms to a dragged span, drawing the selection while it drags", () => {
    const { container } = render(<SweepChart {...props()} />);
    const canvas = canvasOf(container);
    press(canvas, xAt(13.2));
    move(canvas, xAt(13.6));
    expect(container.querySelector(".sweep-zoom-select")).not.toBeNull();
    lift(canvas, xAt(13.6));
    expect(container.querySelector(".sweep-zoom-select")).toBeNull();
    const v = viewOf(container);
    expect(v.lo).toBeCloseTo(13.2, 9);
    expect(v.hi).toBeCloseTo(13.6, 9);
  });

  it("a drag shorter than the click threshold over a band is a click, not a zoom to 3 px", () => {
    const { container } = render(<SweepChart {...props()} />);
    drag(canvasOf(container), xAt(14.1), xAt(14.1) + 2);
    const v = viewOf(container);
    // The band's window, not a sliver.
    expect(v.hi - v.lo).toBeCloseTo(0.35 * (1 + 2 * BAND_MARGIN), 9);
  });

  it("keeps the hover readout working through it", () => {
    const { container } = render(<SweepChart {...props()} />);
    const canvas = canvasOf(container);
    move(canvas, xAt(13.5));
    expect(canvas.getAttribute("data-hover")).toBe("13.5000");
    drag(canvas, xAt(13), xAt(14));
    move(canvas, 26 + 150);
    expect(canvas.getAttribute("data-hover")).toBe("13.5000");
  });

  it("zooms on Ctrl+wheel about the cursor, and takes it from the browser", () => {
    const { container } = render(<SweepChart {...props()} />);
    const canvas = canvasOf(container);
    // fireEvent returns false when a listener called preventDefault.
    expect(fireEvent.wheel(canvas, { deltaY: -300, ctrlKey: true, clientX: xAt(14.5) })).toBe(false);
    const v = viewOf(container);
    expect(v.zoomed).toBe(true);
    // 14.5 MHz sat three quarters across, and still does.
    expect((14.5 - v.lo) / (v.hi - v.lo)).toBeCloseTo(0.75, 9);
    // ⌘ (macOS) does the same.
    expect(fireEvent.wheel(canvas, { deltaY: -300, metaKey: true, clientX: xAt(14.5) })).toBe(false);
    expect(viewOf(container).hi - viewOf(container).lo).toBeLessThan(v.hi - v.lo);
  });

  it("leaves a PLAIN wheel to the page: not prevented, the view unchanged", () => {
    const { container } = render(<SweepChart {...props()} />);
    const canvas = canvasOf(container);
    expect(fireEvent.wheel(canvas, { deltaY: -300, clientX: xAt(14.5) })).toBe(true);
    expect(viewOf(container)).toEqual({ lo: 13, hi: 15, zoomed: false });
    // Zoomed too: a plain wheel neither zooms nor pans the window.
    click(canvas, xAt(14.175));
    const before = viewOf(container);
    expect(fireEvent.wheel(canvas, { deltaY: 300, clientX: xAt(14.2) })).toBe(true);
    expect(fireEvent.wheel(canvas, { deltaX: 300, clientX: xAt(14.2) })).toBe(true);
    expect(viewOf(container)).toEqual(before);
  });

  it("zooms about the centre with + and −, and Esc goes back to the whole sweep", () => {
    const { container } = render(<SweepChart {...props()} />);
    const canvas = canvasOf(container);
    expect(canvas.getAttribute("tabindex")).toBe("0");
    expect(canvas.getAttribute("aria-label")).toMatch(/ham band.*drag.*Ctrl\+scroll.*pinch.*double-click or Esc/);
    fireEvent.keyDown(canvas, { key: "+" });
    fireEvent.keyDown(canvas, { key: "+" });
    let v = viewOf(container);
    expect(v.hi - v.lo).toBeCloseTo(2 / 1.5625, 9);
    expect((v.lo + v.hi) / 2).toBeCloseTo(14, 9);
    fireEvent.keyDown(canvas, { key: "-" });
    v = viewOf(container);
    expect(v.hi - v.lo).toBeCloseTo(2 / 1.25, 9);
    fireEvent.keyDown(canvas, { key: "Escape" });
    expect(viewOf(container)).toEqual({ lo: 13, hi: 15, zoomed: false });
  });

  it("double-click and the chip's Reset zoom go back to the whole sweep in one step", () => {
    const { container } = render(<SweepChart {...props()} />);
    const canvas = canvasOf(container);
    drag(canvas, xAt(13.2), xAt(13.4));
    drag(canvas, xAt(13.25), xAt(13.3));
    expect(viewOf(container).zoomed).toBe(true);
    fireEvent.doubleClick(canvas);
    expect(viewOf(container).zoomed).toBe(false);
    drag(canvas, xAt(13.2), xAt(13.4));
    const reset = screen.getByRole("button", { name: "Reset zoom" });
    expect(reset.getAttribute("title")).toMatch(/double-click.*Esc/);
    fireEvent.click(reset);
    expect(viewOf(container)).toEqual({ lo: 13, hi: 15, zoomed: false });
    expect(screen.queryByRole("button", { name: "Reset zoom" })).toBeNull();
  });
});

describe("the zoom is a view of one design", () => {
  it("survives a re-solve (a new sweep, same design) and is dropped on a design switch", () => {
    const { container, rerender } = render(<SweepChart {...props()} />);
    drag(canvasOf(container), xAt(13.2), xAt(13.6));
    const zoomed = viewOf(container);
    // A knob turn: a new sweep object over the same span.
    rerender(<SweepChart {...props({ sweep: sweepOf(250), r: 60 })} />);
    expect(viewOf(container)).toEqual(zoomed);
    rerender(<SweepChart {...props({ sweep: sweepOf(250), designKey: "yagi" })} />);
    expect(viewOf(container)).toEqual({ lo: 13, hi: 15, zoomed: false });
  });

  it("Auto fits only the visible part of the curve", () => {
    const { container } = render(<SweepChart {...props()} />);
    const canvas = canvasOf(container);
    const wholeLo = Number(canvas.getAttribute("data-y-lo"));
    // The whole sweep holds the dip (matched at 14.2): a deep floor.
    expect(wholeLo).toBeLessThanOrEqual(-30);
    // 13.0–13.4 MHz is all poor match (S11 ≈ −2 to −3 dB): Auto's floor
    // is the shallowest, as it would be for a sweep of just that span.
    drag(canvas, xAt(13), xAt(13.4));
    const zoomedLo = Number(canvas.getAttribute("data-y-lo"));
    expect(zoomedLo).toBeGreaterThan(wholeLo);
    expect(zoomedLo).toBe(-10);
    // And back.
    fireEvent.doubleClick(canvas);
    expect(Number(canvas.getAttribute("data-y-lo"))).toBe(wholeLo);
  });

  it("follows the zoom with the ham bands: one the window leaves is not marked", () => {
    const forty = { label: "15m-ish", lo: 13.1, hi: 13.2 };
    const { container } = render(<SweepChart {...props({ hamBands: [forty, TWENTY] })} />);
    const canvas = canvasOf(container);
    click(canvas, xAt(14.175));
    // The bands' marks (and their coverage) are the sweep's, zoomed or not.
    expect(canvas.getAttribute("data-hambands")).toMatch(/^15m-ish:.*,20m:/);
    expect(viewOf(container).lo).toBeGreaterThan(forty.hi);
  });
});

describe("Sweep this span", () => {
  it("hands the window, as the chip reads it, to the range edit and resets the view", () => {
    const onSweepSpan = vi.fn();
    const { container } = render(<SweepChart {...props({ onSweepSpan })} />);
    click(canvasOf(container), xAt(14.175));
    fireEvent.click(screen.getByRole("button", { name: "Sweep this span" }));
    expect(onSweepSpan).toHaveBeenCalledTimes(1);
    expect(onSweepSpan).toHaveBeenCalledWith(13.965, 14.385);
    expect(viewOf(container).zoomed).toBe(false);
  });

  it("is not offered without a range edit to call", () => {
    const { container } = render(<SweepChart {...props()} />);
    click(canvasOf(container), xAt(14.175));
    expect(screen.getByRole("button", { name: "Reset zoom" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Sweep this span" })).toBeNull();
  });
});

describe("touch", () => {
  it("one finger at the whole sweep is the page's swipe, not a selection", () => {
    const { container } = render(<SweepChart {...props()} />);
    const canvas = canvasOf(container);
    expect(canvas.style.touchAction).toBe("pan-x pan-y");
    press(canvas, xAt(13.2), 1, "touch");
    move(canvas, xAt(13.8), 1, "touch");
    lift(canvas, xAt(13.8), 1, "touch");
    expect(viewOf(container).zoomed).toBe(false);
    expect(container.querySelector(".sweep-zoom-select")).toBeNull();
  });

  it("two fingers pinch the axis; zoomed, one finger pans it", () => {
    const { container } = render(<SweepChart {...props()} />);
    const canvas = canvasOf(container);
    press(canvas, xAt(13.8), 1, "touch");
    press(canvas, xAt(14.2), 2, "touch");
    move(canvas, xAt(14.6), 2, "touch");
    lift(canvas, xAt(14.6), 2, "touch");
    lift(canvas, xAt(13.8), 1, "touch");
    const v = viewOf(container);
    expect(v.zoomed).toBe(true);
    expect(v.hi - v.lo).toBeCloseTo(1, 6); // the fingers' spread doubled
    expect(canvas.style.touchAction).toBe("none");
    press(canvas, xAt(14), 3, "touch");
    move(canvas, xAt(13.9), 3, "touch");
    lift(canvas, xAt(13.9), 3, "touch");
    const panned = viewOf(container);
    expect(panned.hi - panned.lo).toBeCloseTo(1, 6);
    expect(panned.lo).toBeGreaterThan(v.lo);
  });
});

describe("a thumbnail stays inert", () => {
  it("gets no zoom, no chip, no focus and no gesture handlers", () => {
    const onSweepSpan = vi.fn();
    const { container } = render(
      <SweepChart {...props({ interactive: false, hamBands: [], onSweepSpan })} />,
    );
    const canvas = canvasOf(container);
    expect(canvas.getAttribute("tabindex")).toBeNull();
    expect(fireEvent.wheel(canvas, { deltaY: -300, ctrlKey: true, clientX: xAt(14.5) })).toBe(true);
    drag(canvas, xAt(13.2), xAt(13.6));
    fireEvent.keyDown(canvas, { key: "+" });
    fireEvent.doubleClick(canvas);
    expect(viewOf(container)).toEqual({ lo: 13, hi: 15, zoomed: false });
    expect(container.querySelector(".sweep-zoom-select")).toBeNull();
    expect(screen.queryByRole("group", { name: "Frequency zoom" })).toBeNull();
    expect(onSweepSpan).not.toHaveBeenCalled();
  });

  it("drops a zoom it was given while interactive (the stage chart shrunk to a thumb)", () => {
    const { container, rerender } = render(<SweepChart {...props()} />);
    drag(canvasOf(container), xAt(13.2), xAt(13.6));
    expect(viewOf(container).zoomed).toBe(true);
    rerender(<SweepChart {...props({ interactive: false })} />);
    expect(viewOf(container).zoomed).toBe(false);
  });
});
