// An analysis chart's legend (AK#1757, sweep-framework step 5 unit 4): one
// row per curve, in its colour, labelled like the CLI's cells (the engine,
// the ground, as the analysis spells them, joined by ", "); a refused cell
// appears here by name with its reason, while the rest draw; and an
// over-cap cross is refused as a whole, in the CLI's words.
//
// A chart with one curve and nothing refused has no legend: it is the chart
// as it was before crosses.

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
};

export function legendShown(l: ChartLegendData | null | undefined): l is ChartLegendData {
  return (
    !!l && (l.capRefusal !== null || l.entries.length > 1 || l.entries.some((e) => e.refused))
  );
}

export function ChartLegend({ legend }: { legend: ChartLegendData }) {
  const drawn = legend.entries.filter((e) => !e.refused).length;
  return (
    <details className="chart-legend" open data-curves={drawn}>
      <summary>
        {legend.capRefusal ? "refused" : `${drawn} curve${drawn === 1 ? "" : "s"}`}
        {legend.rx && !legend.capRefusal ? " · R solid, X dashed" : ""}
      </summary>
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
    </details>
  );
}
