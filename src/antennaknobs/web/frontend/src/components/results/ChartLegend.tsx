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

export type ChartLegendData = {
  entries: ChartLegendEntry[];
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
  return `${drawn} curve${drawn === 1 ? "" : "s"} ▾` + (k > 0 ? ` · ${k} refused` : "");
}

export function legendShown(l: ChartLegendData | null | undefined): l is ChartLegendData {
  return (
    !!l && (l.capRefusal !== null || l.entries.length > 1 || l.entries.some((e) => e.refused))
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
    </div>
  );
}
