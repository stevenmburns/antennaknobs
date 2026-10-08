import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PatternCellsTable } from "../components/results/PatternCellsTable";

// QRZ 1005128 #61 (Dan): on a short stage the floating solve readout covered
// the pattern table's first row. The readout sits at the bottom-left of the
// chart's square, so the table's box must FILL that square, as a chart does,
// rather than shrink to its rows. jsdom has no layout, so this pins the box's
// own size; the CSS that ends the scroll above the readout is in styles.css.
describe("PatternCellsTable box", () => {
  it("fills the chart's square however few rows it has", () => {
    render(
      <PatternCellsTable
        size={320}
        rows={[
          {
            key: "a",
            label: "hgh = 20",
            color: "#f00",
            metrics: null,
            refused: null,
            stale: false,
          },
        ]}
      />,
    );
    const box = screen.getByRole("table", { name: "Pattern metrics" })
      .parentElement as HTMLElement;
    expect(box.style.width).toBe("320px");
    expect(box.style.height).toBe("320px");
  });
});
