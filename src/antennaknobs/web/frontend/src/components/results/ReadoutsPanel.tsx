import type { ReadoutRow } from "../../lib/api";

// Generic server-driven readouts (issue #712). This component is the ONLY
// frontend code any design-side readout ever needs: the server sends
// self-describing {label, value, unit, group} rows (see ReadoutRow), this
// renders them, and a new construction feature — a bungee closure's
// stretch/tension drift, a user design in ~/.antennaknobs/designs — costs
// zero TypeScript. That guarantee is why nothing below may branch on a
// label, a unit or a group name: the rows are opaque display data.

// Significant digits every numeric row is formatted to. One constant, one
// call site: the server picks the UNIT (it alone knows whether a length is
// a sag in millimetres or a mast height in metres), the client picks the
// precision, and neither has to know the other's choice.
const SIG_FIGS = 4;

export function formatReadoutValue(value: ReadoutRow["value"]): string {
  // A missing value is a real state — a rope sag on a model that has no
  // rope — not an error; it reads as an em-dash like every other blank in
  // the readout.
  if (value === null || value === undefined) return "—";
  // Strings are printed verbatim: the server already chose their wording
  // (e.g. a tension quoted in both N and lbf), and re-formatting them here
  // would be exactly the per-design knowledge this component must not have.
  if (typeof value === "string") return value;
  if (!Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  // toPrecision then parseFloat: fixed sig-figs without the trailing zeros
  // (22.53000 -> "22.53") that make a HUD column look ragged.
  return String(parseFloat(value.toPrecision(SIG_FIGS)));
}

function formatRow(row: ReadoutRow): string {
  const text = formatReadoutValue(row.value);
  return row.unit && text !== "—" ? `${text} ${row.unit}` : text;
}

export function ReadoutsPanel({ rows }: { rows?: ReadoutRow[] | null }) {
  // Nothing to say -> nothing rendered, not an empty card: most designs
  // send no rows at all and their readout must look exactly as it did
  // before this feature existed.
  if (!rows || rows.length === 0) return null;

  // Cluster by group, preserving the server's row order inside each group
  // and grouping by FIRST appearance, so a design controls the whole
  // layout from Python. Ungrouped rows lead (they belong to no heading, so
  // a heading above them would be a lie).
  const groups: { name: string | null; rows: ReadoutRow[] }[] = [];
  for (const row of rows) {
    const name = row.group ?? null;
    const bucket = groups.find((g) => g.name === name);
    if (bucket) bucket.rows.push(row);
    else groups.push({ name, rows: [row] });
  }
  const ungroupedFirst = [
    ...groups.filter((g) => g.name === null),
    ...groups.filter((g) => g.name !== null),
  ];

  return (
    <>
      {ungroupedFirst.map((g) => (
        // .feeds-table is the readout's existing "separated block of rows"
        // wrapper (the power budget and per-feed Z tables use it); reusing
        // it keeps a design's rows visually part of the readout rather
        // than a second card bolted on.
        <div className="feeds-table" key={`readout-group-${g.name ?? ""}`}>
          {g.name && <div className="feeds-table-header">{g.name}</div>}
          {g.rows.map((row, i) => (
            <div className="row readout-row" key={`readout-${g.name ?? ""}-${i}`}>
              <span>{row.label}</span>
              <span className="val">{formatRow(row)}</span>
            </div>
          ))}
        </div>
      ))}
    </>
  );
}
