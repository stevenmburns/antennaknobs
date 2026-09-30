// "Download CSV" in the Table view: the same cells as the copy text, CSV
// quoted, saved through sessionActions.saveTextFile under
// <design>-<what it sweeps>.csv.
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChartTable } from "../components/charts/ChartTable";
import { type ChartTableData, chartTable, tableCsv, tableCsvName, tableTsv } from "../lib/chartTable";

const save = vi.hoisted(() => vi.fn<(text: string, name: string) => void>());
vi.mock("../components/session/sessionActions", () => ({ saveTextFile: save }));

const two = chartTable(
  "frequency",
  "frequency",
  [
    { label: "NEC-5, real ground", xs: [14, 14.1], re: [50, 51.5], im: [-3, 4.25] },
    { label: 'momwire "bs2"', xs: [14, 14.1], re: [49, 50], im: [-2, 3] },
  ],
  50,
);

beforeEach(() => save.mockClear());

describe("tableCsv", () => {
  it("a multi-curve table: a heading row, a row per x, labels with commas and quotes quoted", () => {
    const lines = tableCsv(two).trimEnd().split("\n");
    expect(lines[0]).toBe(
      'MHz,"NEC-5, real ground R (Ω)","NEC-5, real ground X (Ω)","NEC-5, real ground SWR",' +
        '"momwire ""bs2"" R (Ω)","momwire ""bs2"" X (Ω)","momwire ""bs2"" SWR"',
    );
    expect(lines).toHaveLength(3);
    expect(lines[1].startsWith("14,50.000,-3.000,")).toBe(true);
    // Every cell is the copy text's cell, unrounded further.
    const tsvCells = tableTsv(two).trimEnd().split("\n").slice(1).map((l) => l.split("\t"));
    expect(lines.slice(1).map((l) => l.split(","))).toEqual(tsvCells);
  });

  it("a single unnamed curve heads its columns bare; a newline in a cell is quoted", () => {
    const t: ChartTableData = {
      kind: "knob",
      xName: "height",
      groups: [{ label: "", columns: ["R (Ω)"] }],
      rows: [["9.5", "a\nb"]],
    };
    expect(tableCsv(t)).toBe('height,R (Ω)\n9.5,"a\nb"\n');
  });
});

describe("tableCsvName", () => {
  it("names the design and what the chart sweeps, sanitised", () => {
    expect(tableCsvName(two, "inverted vee/1")).toBe("inverted_vee_1-frequency.csv");
    const knob = chartTable("knob", "apex height", [], 50);
    expect(tableCsvName(knob, "dipole")).toBe("dipole-apex_height.csv");
    expect(tableCsvName(chartTable("density", "nominal_nsegs", [], 50), "")).toBe("table-density.csv");
  });
});

describe("the Download CSV button", () => {
  it("saves the table's CSV under a .csv name", () => {
    render(<ChartTable table={two} size={400} design="invvee" />);
    fireEvent.click(screen.getByRole("button", { name: "Download CSV" }));
    expect(save).toHaveBeenCalledTimes(1);
    const [text, name] = save.mock.calls[0];
    expect(name).toBe("invvee-frequency.csv");
    expect(text).toBe(tableCsv(two));
  });

  it("is disabled with no rows", () => {
    render(<ChartTable table={chartTable("frequency", "frequency", [], 50)} size={400} />);
    expect((screen.getByRole("button", { name: "Download CSV" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
