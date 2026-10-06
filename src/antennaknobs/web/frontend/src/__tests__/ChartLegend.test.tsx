// The analysis chart's legend and its collapsed chip (AK#1757 step 5 unit
// 4, Steve's phone review of unit 4a): collapsed, one chip counting the
// curves and, whenever anything is refused, the refused cells, so
// collapsing never hides a refusal.
//
// Mutation note (run by hand, 2026-09-29; reverted after): the chip
// dropping its refused count (chipText without the " · <k> refused" part)
// fails "the chip counts the refused cells…".
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ChartLegend, type ChartLegendData, chipText, legendShown } from "../components/results/ChartLegend";

const entry = (key: string, refused: string | null = null) => ({
  key,
  label: key,
  color: refused ? null : "#f00",
  refused,
});

const LEGEND: ChartLegendData = {
  entries: [entry("A"), entry("B"), entry("pec", "no ground slot holds pec")],
  capRefusal: null,
};

describe("the chart legend", () => {
  it("expanded, names every cell and offers to collapse", () => {
    const onOpen = vi.fn();
    render(<ChartLegend legend={{ ...LEGEND, open: true, onOpen }} />);
    const legend = document.querySelector<HTMLElement>(".chart-legend")!;
    expect(legend.dataset.curves).toBe("2");
    expect([...legend.querySelectorAll(".chart-legend-row")].map((r) => r.textContent)).toEqual([
      "A",
      "B",
      "pec: no ground slot holds pec",
    ]);
    expect(document.querySelector(".chart-legend-chip")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Collapse the legend" }));
    expect(onOpen).toHaveBeenCalledWith(false);
  });

  it("a refused cell's row draws no stroke sample: it is no curve (AC6LA, QRZ)", () => {
    render(<ChartLegend legend={{ ...LEGEND, open: true, onOpen: () => {} }} />);
    const rows = [...document.querySelectorAll<HTMLElement>(".chart-legend-row")];
    const swatches = rows.map((r) => r.querySelector(".chart-legend-swatch")!.classList.contains("is-none"));
    expect(swatches).toEqual([false, false, true]);
    // The reason flows on inside the label, one sentence that wraps as text.
    expect(rows[2].querySelector(".chart-legend-label")!.textContent).toBe("pec: no ground slot holds pec");
  });

  it("collapsed, is one chip that opens it again", () => {
    const onOpen = vi.fn();
    render(<ChartLegend legend={{ ...LEGEND, open: false, onOpen }} />);
    expect(document.querySelector(".chart-legend")).toBeNull();
    const chip = screen.getByRole("button", { name: /^Show the legend/ });
    expect(chip.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(chip);
    expect(onOpen).toHaveBeenCalledWith(true);
  });

  it("the chip counts the refused cells, or the chart refused whole over the cap", () => {
    expect(chipText(LEGEND)).toBe("2 curves ▾ · 1 refused");
    expect(chipText({ ...LEGEND, entries: [entry("A"), entry("B")] })).toBe("2 curves ▾");
    expect(chipText({ entries: [entry("A")], capRefusal: null })).toBe("1 curve ▾");
    expect(
      chipText({
        entries: [],
        capRefusal: "REFUSED: 4 values x 2 engines = 8 curves, over the cap of 6",
      }),
    ).toBe("0 curves ▾ · 1 refused");
    render(<ChartLegend legend={{ ...LEGEND, open: false, onOpen: () => {} }} />);
    expect(screen.getByRole("button", { name: /^Show the legend/ }).textContent).toBe(
      "2 curves ▾ · 1 refused",
    );
  });

  it("without a way to flip it, stays open", () => {
    render(<ChartLegend legend={{ ...LEGEND, open: false }} />);
    expect(document.querySelector(".chart-legend")).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Collapse the legend" })).toBeNull();
  });

  it("a skipped engine's note shows the legend over one curve, muted, and is no refusal", () => {
    const note = "skipped: razor-2p, NEC-5, which no slot holds. Put one in a slot to include it.";
    const one: ChartLegendData = { entries: [entry("momwire:bspline")], capRefusal: null };
    expect(legendShown(one)).toBe(false);
    expect(legendShown({ ...one, note })).toBe(true);
    render(<ChartLegend legend={{ ...one, note, open: true, onOpen: () => {} }} />);
    const legend = document.querySelector<HTMLElement>(".chart-legend")!;
    expect(legend.querySelector('[role="note"]')?.textContent).toBe(note);
    expect(legend.querySelector('[role="note"]')?.className).toBe("chart-legend-note");
    expect(legend.querySelector(".is-refused, .chart-legend-why, [role='alert']")).toBeNull();
    expect(chipText({ ...one, note })).toBe("1 curve ▾");
  });
});
