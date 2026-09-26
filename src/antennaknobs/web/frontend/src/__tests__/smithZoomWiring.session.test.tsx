// The Smith chart's zoom reaches the chart through the session, not only
// through a fixture that sets `interactive` itself: the stage's bag passes
// chartZoom, the thumbnail strip's does not. A component test alone would
// stay green with the stage never turning the zoom on.
import { afterEach, describe, it, expect, vi } from "vitest";
import { fireEvent } from "@testing-library/react";
import { mountReady } from "./designSessionHarness";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Smith chart zoom wiring", () => {
  it("zooms the chart on the stage", async () => {
    // Ready, not merely mounted: the wheel listener is attached in the
    // chart's effect, which the session's settled load path is past.
    const { container } = await mountReady({
      layout: "grid",
      pinned: ["smith", "vswr", "antenna"],
    });
    const chart = container.querySelector<HTMLElement>(".grid-cell canvas.smith")!;
    expect(chart.getAttribute("tabindex")).toBe("0");
    expect(fireEvent.wheel(chart, { deltaY: -400 })).toBe(false);
    expect(Number(chart.dataset.zoom)).toBeGreaterThan(1);
  });

  it("leaves the thumbnail alone: no zoom, and the wheel goes to the page", async () => {
    const { container } = await mountReady({
      layout: "rail",
      pinned: ["antenna", "smith", "vswr"],
    });
    const thumb = container.querySelector<HTMLElement>(".thumbstrip canvas.smith")!;
    expect(thumb.getAttribute("tabindex")).toBeNull();
    expect(fireEvent.wheel(thumb, { deltaY: -400 })).toBe(true);
    expect(thumb.dataset.zoom).toBe("1");
  });
});
