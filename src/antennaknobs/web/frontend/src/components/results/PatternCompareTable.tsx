import { LIVE_ENTITY } from "../charts/combined";
import { GHOST_COLOR_COUNT, GHOST_FALLBACK_RGB } from "../charts/palette";
import type { PatternMetrics, PinnedPattern } from "../charts/types";

export function PatternCompareTable({
  live,
  liveLabel,
  pinned,
  onRemove,
  onToggle,
  highlight,
  onToggleHighlight,
}: {
  live: PatternMetrics | null;
  liveLabel: string;
  pinned: PinnedPattern[];
  onRemove: (id: string) => void;
  onToggle: (id: string) => void;
  /** The combined view's highlight (AK#1730): the designs whose traces draw
   *  at full strength while the rest dim. Given together with
   *  `onToggleHighlight`, each row gets a highlight switch and clicking the row
   *  toggles it — per row, any number at once. Omitted (the one-cut views),
   *  the table is as it always was. */
  highlight?: readonly string[];
  onToggleHighlight?: (id: string) => void;
}) {
  const highlighting = !!onToggleHighlight;
  const fmt = (v: number | undefined, d: number) =>
    v === undefined || v === null ? "—" : v.toFixed(d);
  // Live row's swatch reads the lobe CSS var so it matches the orange lobe in
  // either theme; pinned rows use their fixed canvas ghost colors.
  const rows = [
    {
      key: LIVE_ENTITY,
      bg: "rgba(var(--plot-lobe-rgb), 0.95)",
      label: liveLabel,
      m: live,
      enabled: true,
      onToggle: undefined as undefined | (() => void),
      onX: undefined as undefined | (() => void),
    },
    ...pinned.map((p) => {
      const i = p.colorIdx % GHOST_COLOR_COUNT;
      return {
        key: p.id,
        // CSS var (like the live row) so the swatch rethemes without a render.
        bg: `rgba(var(--plot-ghost-${i}-rgb, ${GHOST_FALLBACK_RGB[i]}), 0.95)`,
        label: p.label,
        m: p.metrics,
        enabled: p.enabled,
        onToggle: () => onToggle(p.id),
        onX: () => onRemove(p.id),
      };
    }),
  ];
  return (
    <table className="compare-table">
      <thead>
        <tr>
          {highlighting && <th className="compare-hl" title="Highlight" />}
          <th>design</th>
          <th>peak</th>
          <th>takeoff</th>
          <th>F/B</th>
          <th>az bw</th>
          <th title="Receiving directivity factor: peak gain over the average gain of the whole pattern">
            RDF
          </th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const lit = !!highlight?.includes(row.key);
          // A hidden pin draws nothing, so there is nothing to highlight.
          const canLight = highlighting && row.enabled;
          const classes = [
            row.enabled ? "" : "compare-off",
            canLight ? "compare-lightable" : "",
            lit ? "compare-lit" : "",
          ]
            .filter(Boolean)
            .join(" ");
          return (
            <tr
              key={row.key}
              className={classes || undefined}
              // Clicking anywhere on the row toggles its highlight; the row's own
              // buttons (show/hide, remove, the switch itself) keep their jobs.
              onClick={
                canLight
                  ? (e) => {
                      if ((e.target as HTMLElement).closest("button")) return;
                      onToggleHighlight?.(row.key);
                    }
                  : undefined
              }
            >
              {highlighting && (
                <td className="compare-hl">
                  <button
                    type="button"
                    className="compare-hl-btn"
                    aria-pressed={lit}
                    aria-label={`Highlight ${row.label}`}
                    disabled={!canLight}
                    onClick={() => onToggleHighlight?.(row.key)}
                    title={
                      lit
                        ? "Un-highlight this design"
                        : "Highlight this design: highlighted designs stay bright and the rest dim (any number at once)"
                    }
                  />
                </td>
              )}
              <td className="compare-name">
                {/* The whole swatch+name is the show/hide toggle — a big-enough
                    touch target where the tiny swatch alone wouldn't be. The
                    metrics stay readable while hidden; that's disable vs delete. */}
                {row.onToggle ? (
                  <button
                    type="button"
                    className="compare-toggle"
                    onClick={row.onToggle}
                    aria-pressed={row.enabled}
                    title={
                      row.enabled
                        ? "Hide this ghost overlay (keeps the pin)"
                        : "Show this ghost overlay"
                    }
                  >
                    <span
                      className="compare-swatch"
                      style={{ background: row.bg }}
                    />
                    {row.label}
                  </button>
                ) : (
                  <>
                    <span
                      className="compare-swatch"
                      style={{ background: row.bg }}
                    />
                    {row.label}
                  </>
                )}
              </td>
              <td>{fmt(row.m?.peak_gain_dbi, 1)}</td>
              <td>{row.m ? `${fmt(row.m.takeoff_deg, 0)}°` : "—"}</td>
              <td>{fmt(row.m?.front_to_back_db, 1)}</td>
              <td>{row.m ? `${fmt(row.m.az_beamwidth_deg, 0)}°` : "—"}</td>
              <td>{fmt(row.m?.rdf_db, 1)}</td>
              <td>
                {row.onX && (
                  <button
                    type="button"
                    className="compare-x"
                    onClick={row.onX}
                    title="Remove this pinned pattern"
                  >
                    ✕
                  </button>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
