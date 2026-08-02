import { GHOST_COLOR_COUNT, GHOST_FALLBACK_RGB } from "../charts/palette";
import type { PatternMetrics, PinnedPattern } from "../charts/types";

export function PatternCompareTable({
  live,
  liveLabel,
  pinned,
  onRemove,
  onToggle,
}: {
  live: PatternMetrics | null;
  liveLabel: string;
  pinned: PinnedPattern[];
  onRemove: (id: string) => void;
  onToggle: (id: string) => void;
}) {
  const fmt = (v: number | undefined, d: number) =>
    v === undefined || v === null ? "—" : v.toFixed(d);
  // Live row's swatch reads the lobe CSS var so it matches the orange lobe in
  // either theme; pinned rows use their fixed canvas ghost colors.
  const rows = [
    {
      key: "live",
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
          <th>design</th>
          <th>peak</th>
          <th>takeoff</th>
          <th>F/B</th>
          <th>az bw</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} className={row.enabled ? undefined : "compare-off"}>
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
        ))}
      </tbody>
    </table>
  );
}
