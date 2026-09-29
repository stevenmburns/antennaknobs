// The analysis chart's Table view, pure half (AK#1757 step 5 unit 5):
// lib/chartTable.ts against what `antennaknobs analyze` prints.
//
// The oracle is fixtures/tableOracle1757.json, written by
// tests/test_analyses_views_workbench_1757.py from a real run: the Z the
// workbench's /sweep and /param_sweep served for an analysis, beside the
// rows the CLI's `analyze` printed for the same analysis. chartTable on the
// served Z must print the CLI's rows, cell for cell. The Python test holds
// the fixture to the current code (served Z = the CLI's, and the printed
// rows re-derived), so neither side can drift alone.
//
// Mutation notes (run by hand, 2026-09-29; each reverted after):
//   - X printed without its sign (formatF's `plus` ignored): "prints the
//     CLI's rows…" fails on every X cell ("+12.345" against "12.345");
//   - SWR against a fixed 50 Ω instead of the table's Z0: the Z0 = 75 case
//     of "SWR is the CLI's formula…" fails;
//   - formatG as toPrecision (no trailing-zero strip, no e+NN): "formatG is
//     Python's %g" fails.
import { describe, expect, it } from "vitest";
import oracle from "./fixtures/tableOracle1757.json";
import { chartTable, formatF, formatG, swrAt, tableTsv, type TableCurve } from "../lib/chartTable";

type OracleCase = {
  name: string;
  kind: "frequency" | "knob" | "density";
  param: string;
  z0: number;
  curves: { label: string; xs: number[]; re: number[]; im: number[]; n_seg?: number[] }[];
  x_name: string;
  columns: string[];
  // One printed block per curve, each row split on whitespace.
  cli_rows: string[][][];
};

const ORACLE = oracle as unknown as { cases: OracleCase[] };

describe("formatG is Python's %g", () => {
  it("matches '%.6g' on the values a table prints", () => {
    const vals = [14.175, 14.0, 1e-5, 0.0001, 123456, 1234567, 0.1 + 0.2, 21.3375, 7.1234565, 99999.95, -3.25, 1e21, 2.5e-7, 28.47, 0.9, 1, 12, 68, 14.049999999999999];
    // Python 3.12: ['%.6g' % v for v in vals].
    expect(vals.map((v) => formatG(v))).toEqual(["14.175", "14", "1e-05", "0.0001", "123456", "1.23457e+06", "0.3", "21.3375", "7.12346", "99999.9", "-3.25", "1e+21", "2.5e-07", "28.47", "0.9", "1", "12", "68", "14.05"]);
  });
  it("and formatF is '%.3f' / '%+.3f'", () => {
    expect([0.0004, -0.0004, 12.3456, -7.8915, 0].map((v) => formatF(v, 3, true))).toEqual([
      "+0.000",
      "-0.000",
      "+12.346",
      "-7.891",
      "+0.000",
    ]);
    expect(formatF(Infinity, 3)).toBe("inf");
  });
});

describe("SWR is the CLI's formula (sweep.swr_of)", () => {
  it("(1 + |Γ|)/(1 − |Γ|) against the table's Z0", () => {
    expect(swrAt(50, 0, 50)).toBeCloseTo(1, 12);
    expect(swrAt(100, 0, 50)).toBeCloseTo(2, 12);
    expect(swrAt(150, 0, 75)).toBeCloseTo(2, 12);
    expect(swrAt(50, 50, 50)).toBeCloseTo(2.618033988749895, 12);
    const t = chartTable("frequency", "frequency", [{ label: "", xs: [14], re: [150], im: [0] }], 75);
    expect(t.rows[0][3]).toBe("2.000");
  });
});

describe("the columns and the rows", () => {
  const a: TableCurve = { label: "A", xs: [14, 14.1, 14.2], re: [50, 60, 70], im: [-1, 0, 1] };
  const b: TableCurve = { label: "B", xs: [14.1, 14.3], re: [55, 65], im: [2, 3] };

  it("one row per x (the union, ascending), a column group per curve, blanks where a curve has no point", () => {
    const t = chartTable("frequency", "frequency", [a, b], 50);
    expect(t.xName).toBe("MHz");
    expect(t.groups).toEqual([
      { label: "A", columns: ["R (Ω)", "X (Ω)", "SWR"] },
      { label: "B", columns: ["R (Ω)", "X (Ω)", "SWR"] },
    ]);
    expect(t.rows.map((r) => r[0])).toEqual(["14", "14.1", "14.2", "14.3"]);
    expect(t.rows[0].slice(4)).toEqual(["", "", ""]);
    expect(t.rows[1]).toEqual(["14.1", "60.000", "+0.000", "1.200", "55.000", "+2.000", "1.108"]);
    expect(t.rows[3].slice(1, 4)).toEqual(["", "", ""]);
  });

  it("a knob sweep is the knob, R and X; a density ladder nominal_N, N_ach, R, X and |ΔΓ| to its finest rung", () => {
    expect(chartTable("knob", "length_factor", [a], 50).groups[0].columns).toEqual(["R (Ω)", "X (Ω)"]);
    expect(chartTable("knob", "length_factor", [a], 50).xName).toBe("length_factor");
    const d = chartTable(
      "density",
      "n_per_wire",
      [{ label: "", xs: [8, 12, 17], re: [70, 72, 73], im: [5, 3, 2], nAch: [41, 61, 85] }],
      50,
    );
    expect(d.xName).toBe("nominal_N");
    expect(d.rows[2]).toEqual(["17", "85", "73.000", "+2.000", "0.0000"]);
    expect(d.rows[0][0]).toBe("8");
    expect(d.rows[0][1]).toBe("41");
  });

  it("copies as TSV: a heading naming each curve's columns, then the rows", () => {
    const tsv = tableTsv(chartTable("knob", "len", [a, b], 50));
    const lines = tsv.trimEnd().split("\n");
    expect(lines[0]).toBe("len\tA R (Ω)\tA X (Ω)\tB R (Ω)\tB X (Ω)");
    expect(lines[1]).toBe("14\t50.000\t-1.000\t\t");
    expect(lines).toHaveLength(5);
    // One unnamed curve: the columns alone.
    expect(tableTsv(chartTable("knob", "len", [{ ...a, label: "" }], 50)).split("\n")[0]).toBe(
      "len\tR (Ω)\tX (Ω)",
    );
  });
});

describe("the CLI's own table (the oracle fixture)", () => {
  it.each(ORACLE.cases.map((c) => [c.name, c] as const))("prints the CLI's rows for %s", (_n, c) => {
    const curves: TableCurve[] = c.curves.map((k) => ({
      label: k.label,
      xs: k.xs,
      re: k.re,
      im: k.im,
      ...(k.n_seg ? { nAch: k.n_seg } : {}),
    }));
    const t = chartTable(c.kind, c.param, curves, c.z0);
    expect(t.xName).toBe(c.x_name);
    expect(t.groups.map((g) => g.columns)).toEqual(c.curves.map(() => c.columns));
    // Every curve's printed block, cell for cell, is its column group read
    // back from the table's rows at that curve's x values.
    const width = c.columns.length;
    c.cli_rows.forEach((block, k) => {
      const mine = t.rows
        .filter((r) => r[1 + k * width] !== "")
        .map((r) => [r[0], ...r.slice(1 + k * width, 1 + (k + 1) * width)]);
      expect(mine).toEqual(block);
    });
  });
});
