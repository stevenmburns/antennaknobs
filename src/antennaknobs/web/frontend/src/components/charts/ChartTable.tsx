import { useRef, useState } from "react";
import { type ChartTableData, tableTsv } from "../../lib/chartTable";

// The analysis chart's Table view (AK#1757 step 5 unit 5): the numbers
// `antennaknobs analyze` prints, one row per x value and one column group
// per curve (lib/chartTable.ts). The table scrolls inside the chart's square,
// both ways, so a wide multi-curve table on a phone never widens the page.
// "copy" puts it on the clipboard as tab-separated text (a spreadsheet
// pastes it as columns); the cells are ordinary text, so a selection copies
// too.

export function ChartTable({
  table,
  size,
  status = null,
}: {
  table: ChartTableData;
  size: number;
  /** Why there are no rows yet, or that a sweep is running. */
  status?: string | null;
}) {
  const [copied, setCopied] = useState<"ok" | "select" | null>(null);
  const tableRef = useRef<HTMLTableElement>(null);
  const named = table.groups.length > 1 || (table.groups[0]?.label ?? "") !== "";
  const copy = async () => {
    const text = tableTsv(table);
    try {
      await navigator.clipboard.writeText(text);
      setCopied("ok");
    } catch {
      // No clipboard (an insecure origin, a denied permission): select the
      // table instead, for the viewer's own copy.
      const t = tableRef.current;
      const sel = window.getSelection();
      if (t && sel) {
        const range = document.createRange();
        range.selectNodeContents(t);
        sel.removeAllRanges();
        sel.addRange(range);
      }
      setCopied("select");
    }
  };
  return (
    <div
      className="chart-table"
      style={{ width: size, height: size }}
      data-kind={table.kind}
      data-rows={table.rows.length}
      data-cells={table.groups.length}
    >
      <div className="chart-table-bar">
        <span className="chart-table-count">
          {status ?? `${table.rows.length} row${table.rows.length === 1 ? "" : "s"}`}
        </span>
        <button
          type="button"
          className="chart-table-copy"
          disabled={table.rows.length === 0}
          title="Copy the table as tab-separated text (pastes as columns in a spreadsheet)"
          onClick={() => void copy()}
        >
          {copied === "ok" ? "copied" : copied === "select" ? "selected: ⌘/Ctrl+C" : "copy"}
        </button>
      </div>
      <div className="chart-table-scroll">
        <table ref={tableRef} aria-label="Analysis table">
          <thead>
            {named && (
              <tr>
                <th />
                {table.groups.map((g, k) => (
                  <th key={k} colSpan={g.columns.length} className="chart-table-group" scope="colgroup">
                    {g.label}
                  </th>
                ))}
              </tr>
            )}
            <tr>
              <th scope="col">{table.xName}</th>
              {table.groups.flatMap((g, k) =>
                g.columns.map((c) => (
                  <th key={`${k}:${c}`} scope="col">
                    {c}
                  </th>
                )),
              )}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((r, i) => (
              <tr key={i}>
                {r.map((cell, j) =>
                  j === 0 ? (
                    <th key={j} scope="row">
                      {cell}
                    </th>
                  ) : (
                    <td key={j}>{cell}</td>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
