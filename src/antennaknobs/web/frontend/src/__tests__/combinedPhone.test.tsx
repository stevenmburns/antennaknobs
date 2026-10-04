// The combined Az + El view on a phone (AK#1732). At ~390 px the two cut
// knobs, side by side over the lower right, covered the plot's own lower
// right. On a phone the pair now stacks into a column at the right edge
// (styles.css .mobile-screen-combined) and the plot is narrowed to leave that
// column free. jsdom does no layout, so the CSS itself is not measurable
// here; what is pinned is the arithmetic the plot is sized by and that the
// real session's phone tree applies it to the combined page alone.
import { describe, it, expect, afterEach, vi } from "vitest";
import { combinedPhoneChartSize, CUT_PAIR_PHONE_COLUMN_PX } from "../components/charts/combined";
import { mountReady } from "./designSessionHarness";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the combined view's plot size on a phone", () => {
  it("gives the knob column its width at phone width", () => {
    // A 390 px portrait phone: the output pane is ~390 × 375, so the slide's
    // square is 359. The plot keeps 390 - 116 = 274 and the column the rest.
    const size = combinedPhoneChartSize(359, 390);
    expect(size).toBe(390 - CUT_PAIR_PHONE_COLUMN_PX);
    // Plot inset + plot + gap + the 90 px column + its inset fit the pane.
    expect(8 + size + 8 + 90 + 8).toBeLessThanOrEqual(390);
  });

  it("leaves a wide pane's plot alone: the square already clears the column", () => {
    // A phone on its side: the pane is wide and short, the square is the
    // height's, and the column fits beside it unchanged.
    expect(combinedPhoneChartSize(344, 520)).toBe(344);
  });

  it("never goes below the slide's own floor", () => {
    expect(combinedPhoneChartSize(160, 200)).toBe(160);
  });
});

describe("the phone tree's combined page", () => {
  it("is marked for the column layout, and no other page is", async () => {
    const { container } = await mountReady({ mobile: true, pinned: ["combined", "azimuth", "antenna"] });
    const pages = [...container.querySelectorAll(".mobile-screen")];
    const marked = pages.filter((p) => p.classList.contains("mobile-screen-combined"));
    expect(marked).toHaveLength(1);
    expect(pages.indexOf(marked[0])).toBe(0);
    // The page carries the combined view's knob pair, the box the layout moves.
    expect(marked[0].querySelector(".cut-overlay-pair")).not.toBeNull();
  });
});
