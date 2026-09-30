import type { PatternMetrics } from "../charts/types";
import { MetricCells, MetricHeaders } from "./PatternCompareTable";

// A pattern analysis's PatternTable view (AK#1757, sweep-framework step 7
// unit 3): one row per cell, in the cell's colour and by its name, with the
// pattern pins' compare-table columns (PatternCompareTable's MetricCells),
// the metrics /pattern_cell returned beside each cell's solve. A refused
// cell has a row too, its reason in place of numbers.

export type PatternCellRow = {
  key: string;
  label: string;
  color: string | null;
  metrics: PatternMetrics | null;
  /** Why the cell drew nothing (refused, or its solve failed), or null. */
  refused: string | null;
  stale: boolean;
};

export function PatternCellsTable({ rows, size }: { rows: readonly PatternCellRow[]; size: number }) {
  return (
    <div className="analysis-pattern-table" style={{ width: size, maxHeight: size, overflow: "auto" }}>
      <table className="compare-table" aria-label="Pattern metrics">
        <thead>
          <tr>
            <th>cell</th>
            <MetricHeaders />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className={r.stale ? "compare-off" : undefined} data-refused={r.refused ? "1" : "0"}>
              <td className="compare-name">
                <span className="compare-swatch" style={{ background: r.color ?? "transparent" }} />
                {r.label}
              </td>
              {r.refused ? (
                <td colSpan={5} className="compare-refused">
                  {r.refused}
                </td>
              ) : (
                <MetricCells m={r.metrics} />
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
