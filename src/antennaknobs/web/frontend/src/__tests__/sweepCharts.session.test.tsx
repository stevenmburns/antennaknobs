// AK#1738 through the real <DesignSession>, moved onto the analysis chart
// when AK#1757 step 5 unit 3 folded the Smith, VSWR and S11 views into it:
//   - the one freq-sweep switch those three charts (and the Tools menu)
//     shared is gone: the chart's own dwell switch is it now, and nothing
//     else on the page carries a "freq sweep" checkbox;
//   - a range picked on the Swr view's axis persists in the view prefs, as it
//     did on the VSWR view, and is what the chart draws; the S11 view stays
//     on Auto.
import { describe, it, expect, afterEach, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mountReady, stageChart, untilDom } from "./designSessionHarness";
import { VIEW_PREFS_KEY } from "../components/session/useViewPrefs";

afterEach(() => {
  vi.unstubAllGlobals();
});

// A viewer's stored grid from before unit 3: the three sweep views and the
// antenna. The three become the one chart, on the Smith view (the first).
const OLD_GRID = { layout: "grid" as const, pinned: ["smith" as const, "vswr" as const, "gamma" as const, "antenna" as const] };

const chartView = () => screen.getByRole("combobox", { name: "Chart view" }) as HTMLSelectElement;

describe("the chart's dwell switch replaces the shared freq-sweep switch (AK#1738, AK#1757)", () => {
  it("no freq-sweep checkbox is left, in the chart or the Tools menu; the chart's switch is on", async () => {
    const user = userEvent.setup();
    const { container } = await mountReady(OLD_GRID);
    // One chart cell and the antenna's, not four cells.
    expect(container.querySelectorAll(".grid-cell")).toHaveLength(2);
    expect(stageChart("canvas.smith")).toBeTruthy();
    expect(screen.queryAllByRole("checkbox", { name: "freq sweep" })).toEqual([]);
    const dwell = screen.getByRole("checkbox", { name: "auto re-run" }) as HTMLInputElement;
    expect(dwell.checked).toBe(true);
    await user.click(screen.getByRole("button", { name: "Tools menu" }));
    expect(screen.queryAllByRole("checkbox", { name: "freq sweep" })).toEqual([]);
    expect(screen.queryAllByRole("checkbox", { name: "param sweep" })).toEqual([]);
  });
});

describe("a chart's range persists in the view prefs", () => {
  it("a VSWR preset is stored sparsely and drawn; S11 stays on Auto", async () => {
    const user = userEvent.setup();
    await mountReady(OLD_GRID);
    fireEvent.change(chartView(), { target: { value: "Swr" } });
    const vswr = await untilDom(() => stageChart('canvas.sweep[data-mode="vswr"]'));
    await user.click(
      screen.getByRole("button", { name: "VSWR range and SWR threshold" }),
    );
    await user.click(screen.getByRole("button", { name: "1–2" }));
    await untilDom(() => vswr.dataset.axis === "fixed" || null);
    expect(vswr.dataset.yHi).toBe("2");
    fireEvent.change(chartView(), { target: { value: "S11" } });
    const gamma = await untilDom(() => stageChart('canvas.sweep[data-mode="gamma"]'));
    expect(gamma.dataset.axis).toBe("auto");
    const stored = JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "{}");
    expect(stored.sweepAxes).toEqual({ vswr: { kind: "fixed", lo: 1, hi: 2 } });
    expect(stored.swrThreshold).toBeUndefined();
    // The chart's view flips are the session's: the stored record names
    // the chart, not the view on screen.
    expect(stored.pinned).toEqual(["zparam", "antenna"]);
    expect(stored.chartView).toBeUndefined();
  });
});
