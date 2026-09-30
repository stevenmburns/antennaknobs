// An analysis chart's legend (AK#1757, sweep-framework step 5 unit 4): one
// row per curve, in its colour, labelled like the CLI's cells (the engine,
// the ground, as the analysis spells them, joined by ", "); a refused cell
// appears here by name with its reason, while the rest draw; and an
// over-cap cross is refused as a whole, in the CLI's words.
//
// A chart with one curve and nothing refused has no legend: it is the chart
// as it was before crosses.
//
// It collapses to a chip, "<n> curves ▾", plus " · <k> refused" whenever a
// cell (or the whole chart, over the cap) is refused, so collapsing never
// hides a refusal (Steve's phone review of unit 4a: the legend covered too
// much of a phone's chart). Collapsed by default on a phone, open on a
// desktop, as the knob sweep's value boxes are (unit 3); per chart and
// session-only, like the rest of a chart's state.
//
// Below the curves, the pinned sweeps (AK#1757 item 1): every pin in the
// session, whether or not it can draw here, each with its colour, its
// context label (and "Z0 50 Ω" when it was taken at another reference than
// this chart's, ruling 4), show / hide (global, ruling 2), CSV export and
// delete. One that cannot draw on this chart stays listed, greyed, with why.
// Any pin makes the legend show, on a one-curve chart too: the pins section
// is where they are controlled.

export type ChartLegendEntry = {
  key: string;
  label: string;
  /** The curve's colour (components/charts/palette.ts cellColor), or null
   *  for a refused cell, which draws nothing. */
  color: string | null;
  refused: string | null;
  /** Why a drawn curve is missing all the same (the server refused its
   *  sweep), or null. */
  error?: string | null;
};

/** A pinned sweep's row. */
export type ChartLegendPin = {
  id: string;
  label: string;
  /** The chart cell it was pinned from ("" on a one-curve chart). */
  cell: string;
  color: string;
  enabled: boolean;
  /** Why it cannot draw on this chart (lib/sweepPins placePin), or null. */
  reason: string | null;
  /** "Z0 50 Ω" when its reference is not this chart's, else null. */
  z0Note: string | null;
  onToggle: () => void;
  onDelete: () => void;
  onCsv: () => void;
};

export type ChartLegendData = {
  entries: ChartLegendEntry[];
  /** The session's pinned sweeps; absent or empty, no pins section. */
  pins?: ChartLegendPin[];
  /** The chart is an R / X plot, where a pin draws R dashed and X dotted
   *  (whatever the live curves' count; `rx` is about those). */
  pinsRx?: boolean;
  capRefusal: string | null;
  /** The R / X plot draws each curve's R solid and its X dashed. */
  rx?: boolean;
  /** Expanded (true, the default) or collapsed to its chip; with
   *  `onOpen`, the chip and the collapse control flip it. */
  open?: boolean;
  onOpen?: (open: boolean) => void;
};

/** How many cells the legend names as refused: the refused entries, or one
 *  for a chart refused whole over the cap. */
export function refusedCount(l: ChartLegendData): number {
  if (l.capRefusal) return 1;
  return l.entries.filter((e) => e.refused).length;
}

/** The collapsed legend's chip: "<n> curves ▾", and " · <k> refused" when
 *  anything is refused. */
export function chipText(l: ChartLegendData): string {
  const drawn = l.capRefusal ? 0 : l.entries.filter((e) => !e.refused).length;
  const k = refusedCount(l);
  return (
    `${drawn} curve${drawn === 1 ? "" : "s"}${pinsText(l)} ▾` + (k > 0 ? ` · ${k} refused` : "")
  );
}

// " · <n> pins", or nothing without pins.
function pinsText(l: ChartLegendData): string {
  const n = l.pins?.length ?? 0;
  return n > 0 ? ` · ${n} pin${n === 1 ? "" : "s"}` : "";
}

export function legendShown(l: ChartLegendData | null | undefined): l is ChartLegendData {
  return (
    !!l &&
    (l.capRefusal !== null ||
      l.entries.length > 1 ||
      l.entries.some((e) => e.refused) ||
      (l.pins?.length ?? 0) > 0)
  );
}

export function ChartLegend({ legend }: { legend: ChartLegendData }) {
  const drawn = legend.entries.filter((e) => !e.refused).length;
  const { onOpen } = legend;
  if (legend.open === false && onOpen) {
    return (
      <button
        type="button"
        className="chart-legend-chip"
        aria-expanded={false}
        aria-label={`Show the legend: ${chipText(legend)}`}
        data-curves={drawn}
        data-refused={refusedCount(legend)}
        onClick={() => onOpen(true)}
      >
        {chipText(legend)}
      </button>
    );
  }
  return (
    <div className="chart-legend" data-curves={drawn}>
      <div className="chart-legend-head">
        <span>
          {legend.capRefusal ? "refused" : `${drawn} curve${drawn === 1 ? "" : "s"}`}
          {pinsText(legend)}
          {legend.rx && !legend.capRefusal ? " · R solid, X dashed" : ""}
        </span>
        {onOpen && (
          <button
            type="button"
            className="chart-legend-collapse"
            aria-expanded={true}
            aria-label="Collapse the legend"
            onClick={() => onOpen(false)}
          >
            ▴
          </button>
        )}
      </div>
      {legend.capRefusal ? (
        <div className="chart-legend-row is-refused" role="alert">
          {legend.capRefusal}
        </div>
      ) : (
        <ul>
          {legend.entries.map((e) => (
            <li
              key={e.key}
              className={`chart-legend-row${e.refused || e.error ? " is-refused" : ""}`}
              data-refused={e.refused ? "1" : "0"}
            >
              <span
                className="chart-legend-swatch"
                style={e.color ? { background: e.color } : undefined}
                aria-hidden="true"
              />
              <span className="chart-legend-label">{e.label}</span>
              {e.refused && <span className="chart-legend-why">: {e.refused}</span>}
              {!e.refused && e.error && <span className="chart-legend-why">: {e.error}</span>}
            </li>
          ))}
        </ul>
      )}
      {legend.pins && legend.pins.length > 0 && <PinRows pins={legend.pins} rx={!!legend.pinsRx} />}
    </div>
  );
}

// The pins section: a row per pin. The swatch is dashed in the pin's
// colour, as the chart draws it.
function PinRows({ pins, rx }: { pins: ChartLegendPin[]; rx: boolean }) {
  return (
    <div className="chart-legend-pins" role="group" aria-label="Pinned sweeps">
      <div className="chart-legend-head">
        <span>pinned{rx ? " · R dashed, X dotted" : ", dashed"}</span>
      </div>
      <ul>
        {pins.map((p) => {
          const greyed = !p.enabled || p.reason !== null;
          return (
            <li
              key={p.id}
              className={`chart-legend-pin${greyed ? " is-greyed" : ""}`}
              data-pin={p.id}
              data-color={p.color}
              data-enabled={p.enabled ? "1" : "0"}
              data-drawable={p.reason === null ? "1" : "0"}
              title={p.cell ? `${p.label} (${p.cell})` : p.label}
            >
              <input
                type="checkbox"
                checked={p.enabled}
                aria-label={`Show pin ${p.label}`}
                onChange={p.onToggle}
              />
              <span
                className="chart-legend-swatch chart-legend-pin-swatch"
                style={{ borderColor: p.color }}
                aria-hidden="true"
              />
              <span className="chart-legend-label">
                {p.label}
                {p.z0Note && <span className="chart-legend-z0"> · {p.z0Note}</span>}
                {p.reason && <span className="chart-legend-pin-why">: {p.reason}</span>}
              </span>
              <button
                type="button"
                className="chart-legend-pin-btn"
                aria-label={`Export pin ${p.label} as CSV`}
                title="Save this pin as CSV: x, R, X and the SWR at its own Z0"
                onClick={p.onCsv}
              >
                csv
              </button>
              <button
                type="button"
                className="chart-legend-pin-btn"
                aria-label={`Delete pin ${p.label}`}
                title="Delete this pin, from every chart"
                onClick={p.onDelete}
              >
                ×
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
