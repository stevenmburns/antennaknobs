import { useId, useMemo, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import {
  cellCounts,
  compression,
  type FillMap,
  type FillReport,
  type FillReuseMap,
  type FillSectorMap,
  fillShare,
  formatCount,
  formatSeconds,
  provenanceNote,
  reuseCellText,
  reuseNote,
  routeLabel,
  savingNote,
  sectorName,
  sectorRowText,
  sweepNote,
} from "../../lib/fillReport";

// The Fill view (AK#2327): what the matrix fill did on the solve on screen,
// read from momwire's own report. It reports and stops there: nothing in this
// file suggests a change to the model.

const CELL = 20;
const GUTTER = 132;
const HEAD = 22;

function Row({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="fill-row" title={title}>
      <span>{label}</span>
      <span className="val">{value}</span>
    </div>
  );
}

function rect(x: number, y: number, w: number, h: number): string {
  return w > 0 ? `M${x} ${y}h${w}v${h}h${-w}z` : "";
}

/** The three shares of every cell, one path per kind: thousands of cells stay
 *  three DOM nodes. */
function reusePaths(map: FillReuseMap) {
  let computed = "";
  let reused = "";
  let near = "";
  const n = map.rows.length;
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      const counts = cellCounts(map, r, c);
      if (counts.pairs <= 0) continue;
      const x = GUTTER + c * CELL;
      const y = HEAD + r * CELL;
      const wc = (counts.computed / counts.pairs) * CELL;
      const wr = (counts.reused / counts.pairs) * CELL;
      computed += rect(x, y, wc, CELL);
      reused += rect(x + wc, y, wr, CELL);
      near += rect(x + wc + wr, y, (counts.near / counts.pairs) * CELL, CELL);
    }
  }
  return { computed, reused, near };
}

function sectorPaths(map: FillSectorMap) {
  let computed = "";
  let rotation = "";
  const n = map.rows.length;
  map.rows.forEach((row, r) => {
    const d = rect(GUTTER, HEAD + r * CELL, n * CELL, CELL);
    if (row.role === "computed") computed += d;
    else rotation += d;
  });
  return { computed, rotation };
}

function MapGrid({ map }: { map: FillReuseMap | FillSectorMap }) {
  const id = useId();
  const [at, setAt] = useState<{ r: number; c: number } | null>(null);
  const [asTable, setAsTable] = useState(false);
  const n = map.rows.length;
  const size = n * CELL;
  const reuse = map.kind === "reuse" ? map : null;
  const sector = map.kind === "sector" ? map : null;
  const paths = useMemo(() => (reuse ? reusePaths(reuse) : null), [reuse]);
  const rows = useMemo(() => (sector ? sectorPaths(sector) : null), [sector]);
  const grouped = map.rows.some((row) => row.wires > 1);

  const detail =
    at === null
      ? "Hover a cell, or focus the map and use the arrow keys, for its counts."
      : reuse
        ? reuseCellText(reuse, at.r, at.c)
        : sectorRowText(map.rows[at.r]);

  function onPointerMove(e: PointerEvent<SVGSVGElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const scale = (GUTTER + size + 4) / box.width;
    const c = Math.floor(((e.clientX - box.left) * scale - GUTTER) / CELL);
    const r = Math.floor(((e.clientY - box.top) * scale - HEAD) / CELL);
    setAt(r >= 0 && r < n && c >= 0 && c < n ? { r, c } : null);
  }

  function onKeyDown(e: KeyboardEvent<SVGSVGElement>) {
    const step: Record<string, [number, number]> = {
      ArrowUp: [-1, 0],
      ArrowDown: [1, 0],
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
    };
    const move = step[e.key];
    if (!move) return;
    e.preventDefault();
    const from = at ?? { r: 0, c: 0 };
    setAt({
      r: Math.min(n - 1, Math.max(0, from.r + move[0])),
      c: Math.min(n - 1, Math.max(0, from.c + move[1])),
    });
  }

  return (
    <div className="fill-map">
      <div className="fill-map-bar">
        <ul className="fill-legend" aria-label="map key">
          {reuse ? (
            <>
              <li><span className="fill-swatch fill-swatch-computed" aria-hidden="true" />computed (solid)</li>
              <li><span className="fill-swatch fill-swatch-reused" aria-hidden="true" />reused (hatched)</li>
              <li><span className="fill-swatch fill-swatch-near" aria-hidden="true" />near (dotted)</li>
            </>
          ) : (
            <>
              <li><span className="fill-swatch fill-swatch-computed" aria-hidden="true" />computed sector and axis (solid)</li>
              <li><span className="fill-swatch fill-swatch-reused" aria-hidden="true" />follows from rotation (hatched)</li>
            </>
          )}
        </ul>
        <button type="button" className="fill-map-toggle" aria-pressed={asTable} onClick={() => setAsTable(!asTable)}>
          {asTable ? "Show as map" : "Show as table"}
        </button>
      </div>
      {grouped && (
        <p className="fill-note">Wires are grouped so that the map stays readable; each row adds up its group.</p>
      )}
      {asTable ? (
        <div className="fill-table-wrap">
          {reuse ? <ReuseTable map={reuse} /> : <SectorTable map={map as FillSectorMap} />}
        </div>
      ) : (
        <>
          <svg
            className="fill-grid"
            viewBox={`0 0 ${GUTTER + size + 4} ${HEAD + size + 4}`}
            role="img"
            tabIndex={0}
            aria-label={
              reuse
                ? `Matrix map, ${n} by ${n} blocks, by share computed, reused and near. Use the arrow keys to read a block, or show the map as a table.`
                : `Matrix map, ${n} rows, marking the computed sector and the rows that follow from rotation. Use the arrow keys to read a row, or show the map as a table.`
            }
            onPointerMove={onPointerMove}
            onPointerLeave={() => setAt(null)}
            onKeyDown={onKeyDown}
          >
            <defs>
              <pattern id={`${id}-hatch`} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect className="fill-mark-reused-bg" width="5" height="5" />
                <line className="fill-mark-reused-line" x1="0" y1="0" x2="0" y2="5" />
              </pattern>
              <pattern id={`${id}-dots`} width="5" height="5" patternUnits="userSpaceOnUse">
                <rect className="fill-mark-near-bg" width="5" height="5" />
                <circle className="fill-mark-near-dot" cx="2.5" cy="2.5" r="1.2" />
              </pattern>
            </defs>
            {paths && (
              <>
                <path className="fill-mark-computed" d={paths.computed} />
                <path d={paths.reused} fill={`url(#${id}-hatch)`} />
                <path d={paths.near} fill={`url(#${id}-dots)`} />
              </>
            )}
            {rows && (
              <>
                <path className="fill-mark-computed" d={rows.computed} />
                <path d={rows.rotation} fill={`url(#${id}-hatch)`} />
              </>
            )}
            {map.rows.map((row, i) => (
              <g key={`${row.first}-${i}`}>
                <line className="fill-boundary" x1={GUTTER} x2={GUTTER + size} y1={HEAD + i * CELL} y2={HEAD + i * CELL} />
                <line className="fill-boundary" y1={HEAD} y2={HEAD + size} x1={GUTTER + i * CELL} x2={GUTTER + i * CELL} />
                <text className="fill-axis" x={GUTTER - 5} y={HEAD + i * CELL + 14} textAnchor="end">
                  {`${i + 1} ${row.label}`.slice(0, 22)}
                </text>
                <text className="fill-axis" x={GUTTER + i * CELL + CELL / 2} y={HEAD - 7} textAnchor="middle">
                  {i + 1}
                </text>
              </g>
            ))}
            <rect className="fill-frame" x={GUTTER} y={HEAD} width={size} height={size} />
            {at && (
              <rect
                className="fill-focus"
                x={sector ? GUTTER : GUTTER + at.c * CELL}
                y={HEAD + at.r * CELL}
                width={sector ? size : CELL}
                height={CELL}
              />
            )}
          </svg>
          <p className="fill-detail" aria-live="polite">{detail}</p>
        </>
      )}
    </div>
  );
}

function ReuseTable({ map }: { map: FillReuseMap }) {
  return (
    <table className="fill-table">
      <caption>Pairs per wire block</caption>
      <thead>
        <tr>
          <th scope="col">Observer</th>
          <th scope="col">Source</th>
          <th scope="col">Pairs</th>
          <th scope="col">Computed</th>
          <th scope="col">Reused</th>
          <th scope="col">Near</th>
        </tr>
      </thead>
      <tbody>
        {map.rows.flatMap((row, r) =>
          map.rows.map((col, c) => {
            const counts = cellCounts(map, r, c);
            return (
              <tr key={`${r}-${c}`}>
                <th scope="row">{row.label}</th>
                <td>{col.label}</td>
                <td>{formatCount(counts.pairs)}</td>
                <td>{formatCount(counts.computed)}</td>
                <td>{formatCount(counts.reused)}</td>
                <td>{formatCount(counts.near)}</td>
              </tr>
            );
          }),
        )}
      </tbody>
    </table>
  );
}

function SectorTable({ map }: { map: FillSectorMap }) {
  return (
    <table className="fill-table">
      <caption>Matrix rows by sector</caption>
      <thead>
        <tr>
          <th scope="col">Rows</th>
          <th scope="col">Sector</th>
          <th scope="col">Wires</th>
          <th scope="col">Segments</th>
          <th scope="col">How they are filled</th>
        </tr>
      </thead>
      <tbody>
        {map.rows.map((row, i) => (
          <tr key={`${row.first}-${i}`}>
            <th scope="row">{row.label}</th>
            <td>
              {row.sector_first === row.sector_last
                ? sectorName(row.sector_first)
                : `${sectorName(row.sector_first)} – ${sectorName(row.sector_last)}`}
            </td>
            <td>{formatCount(row.wires)}</td>
            <td>{formatCount(row.segments)}</td>
            <td>{row.role === "computed" ? "computed" : "follows from rotation"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MapSection({ map }: { map: FillMap | null }) {
  if (map === null) return null;
  if (map.kind === "unavailable") {
    return <p className="fill-note">The wire map is not available: {map.reason}.</p>;
  }
  return <MapGrid map={map} />;
}

function ReuseCounts({ report }: { report: FillReport }) {
  const reuse = report.reuse;
  if (!reuse || reuse.state === "declined") return null;
  const ratio = compression(reuse);
  const families = Object.entries(reuse.families);
  return (
    <section className="fill-section" aria-label="fill reuse">
      <h3>Fill reuse: {reuse.state}</h3>
      <Row
        label="compression"
        value={ratio === null ? "—" : `${ratio.toFixed(2)}×`}
        title="pairs ÷ (computed + near). This is how far the matrix compressed, not the time saved."
      />
      <p className="fill-note">Compression is pairs ÷ (computed + near). It is not the time saved.</p>
      <Row label="pairs" value={formatCount(reuse.pairs)} />
      <Row label="computed" value={formatCount(reuse.computed)} />
      <Row label="reused" value={formatCount(reuse.reused)} />
      <Row label="near" value={formatCount(reuse.near)} />
      {families.length > 1 && (
        <div className="fill-table-wrap">
          <table className="fill-table">
            <caption>By kernel family</caption>
            <thead>
              <tr>
                <th scope="col">Family</th>
                <th scope="col">Pairs</th>
                <th scope="col">Computed</th>
                <th scope="col">Reused</th>
                <th scope="col">Near</th>
              </tr>
            </thead>
            <tbody>
              {families.map(([name, f]) => (
                <tr key={name}>
                  <th scope="row">{name}</th>
                  <td>{formatCount(f.pairs)}</td>
                  <td>{formatCount(f.computed)}</td>
                  <td>{formatCount(f.reused)}</td>
                  <td>{formatCount(f.near)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {reuse.uncounted.length > 0 && (
        <p className="fill-note">Not counted by this fill: {reuse.uncounted.join(", ")}.</p>
      )}
    </section>
  );
}

function SectorFacts({ report }: { report: FillReport }) {
  const sector = report.sector;
  if (!sector || sector.declined) return null;
  const blocks = sector.blocks.map((b) => `${b.count} × ${formatCount(b.size)}`).join(", ");
  return (
    <section className="fill-section" aria-label="sector route">
      <h3>Rotational symmetry</h3>
      <Row label="sectors" value={formatCount(sector.n_sectors)} />
      <Row label="axis wires" value={formatCount(sector.axial)} />
      <Row label="blocks factored" value={blocks || "—"} />
      <Row
        label="entries computed"
        value={`${formatCount(sector.computed_pairs)} of ${formatCount(sector.pairs)}`}
      />
    </section>
  );
}

function ReportBody({ report }: { report: FillReport }) {
  const share = fillShare(report);
  const provenance = provenanceNote(report);
  const reuse = reuseNote(report);
  const saving = savingNote(report);
  return (
    <>
      {provenance && <p className="fill-provenance">{provenance}</p>}
      {report.scope === "sweep" && <p className="fill-note">{sweepNote(report)}</p>}
      {!report.no_fill && (
        <section className="fill-section" aria-label="times">
          <Row label="route" value={routeLabel(report.route)} />
          <Row label="fill" value={formatSeconds(report.times.fill_s)} />
          <Row label="factor" value={formatSeconds(report.times.factor_s)} />
          <Row
            label="census"
            value={formatSeconds(report.times.census_s)}
            title="The part of the fill spent finding what repeats. It is included in the fill time."
          />
          {share !== null && (
            <p className="fill-note">
              The fill is {(share * 100).toFixed(0)}% of the fill and factor time; the factor is the other{" "}
              {((1 - share) * 100).toFixed(0)}%.
            </p>
          )}
          {saving && <p className="fill-note">{saving}</p>}
        </section>
      )}
      {reuse && <p className="fill-state">{reuse}</p>}
      <SectorFacts report={report} />
      <ReuseCounts report={report} />
      <MapSection map={report.map} />
    </>
  );
}

export function FillPanel({
  report,
  refusal,
  sweep,
  size,
  fill,
}: {
  /** The report of the solve on screen; absent on an engine that has none. */
  report: FillReport | null;
  /** A deck the sector route refused: there is no solve to report on. */
  refusal: FillReport | null;
  /** The last frequency sweep's report, while it still describes this design. */
  sweep: FillReport | null;
  size: number;
  fill: boolean;
}) {
  const box = fill ? undefined : { width: size, height: size };
  if (!fill && size < 240) {
    return (
      <div className="files-thumb" style={box}>
        <span className="files-empty">Fill</span>
      </div>
    );
  }
  const declined = refusal?.sector?.declined ?? null;
  return (
    <div className={fill ? "fill-panel fill-panel-fill" : "fill-panel"} style={box}>
      <h2>Matrix fill</h2>
      {declined !== null && (
        <p className="fill-refusal" role="status">
          {declined}
        </p>
      )}
      {report ? (
        <ReportBody report={report} />
      ) : (
        declined === null && (
          <p className="fill-note">The engine on this tab does not report its fill.</p>
        )
      )}
      {sweep && (
        <section className="fill-sweep" aria-label="last frequency sweep">
          <h2>Last frequency sweep</h2>
          <ReportBody report={sweep} />
        </section>
      )}
    </div>
  );
}
