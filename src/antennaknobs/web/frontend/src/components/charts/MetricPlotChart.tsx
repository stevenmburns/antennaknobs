import type { MetricSpec } from "../../lib/analyses";
import { metricRange, type MetricSeries, metricSpan } from "../../lib/metricPlot";
import { axisTicks, formatTick } from "../../lib/sweepAxis";

// The analysis chart's Metric view (AK#1828, `an.MetricPlot`): a metric
// against the swept knob, one curve per cell, each read off its knob sweep's
// own solves (lib/metricPlot.ts). Relative to a named cell, every curve is
// that difference and the reference is the zero line; a fixed reference is
// drawn flat across the others' span. SVG, so a test reads its curves off
// the data attributes rather than the pixels.

const M = { l: 52, r: 14, t: 26, b: 40 };

/** The runs of consecutive values in `ys`, each as its (x, y) pairs. */
function segments(xs: readonly number[], ys: readonly (number | null)[]): [number, number][][] {
  const out: [number, number][][] = [];
  let cur: [number, number][] = [];
  xs.forEach((v, i) => {
    const w = ys[i];
    if (w === null || w === undefined) {
      if (cur.length > 0) out.push(cur);
      cur = [];
    } else {
      cur.push([v, w]);
    }
  });
  if (cur.length > 0) out.push(cur);
  return out;
}

export function MetricPlotChart({
  metric,
  series,
  xLabel,
  size,
  running,
}: {
  metric: MetricSpec;
  series: readonly MetricSeries[];
  xLabel: string;
  size: number;
  running: boolean;
}) {
  const relative = metric.relativeTo !== null;
  const yLabel = relative
    ? `${metric.name} vs ${metric.relativeTo} (${metric.relativeUnit})`
    : `${metric.name} (${metric.unit})`;
  const span = metricSpan(series);
  const range = metricRange(series);
  const w = size - M.l - M.r;
  const h = size - M.t - M.b;
  const errors = [...new Set(series.map((s) => s.error).filter((e): e is string => !!e))];
  const attrs = {
    "data-metric": metric.name,
    "data-relative": metric.relativeTo ?? "",
    "data-series": JSON.stringify(
      series.map((s) => (s.fixed ? { label: s.label, level: s.level } : { label: s.label, xs: s.xs, ys: s.ys })),
    ),
  };
  if (!span || !range) {
    return (
      <div className="metric-plot metric-plot-empty" style={{ width: size, height: size }} {...attrs}>
        <span>{errors[0] ?? (running ? "solving…" : `no ${metric.name} yet: run the sweep`)}</span>
      </div>
    );
  }
  const xd = span.hi > span.lo ? span : { lo: span.lo - 1, hi: span.hi + 1 };
  const x = (v: number) => M.l + ((v - xd.lo) / (xd.hi - xd.lo)) * w;
  const y = (v: number) => M.t + (1 - (v - range.lo) / (range.hi - range.lo)) * h;
  const xt = axisTicks(xd, 5);
  const yt = axisTicks(range, 5);
  return (
    <div className="metric-plot" style={{ width: size, height: size }} {...attrs}>
      <svg width={size} height={size} role="img" aria-label={`${yLabel} against ${xLabel}`}>
        <g className="metric-plot-grid">
          {yt.map((t) => (
            <line key={`y${t}`} x1={M.l} x2={M.l + w} y1={y(t)} y2={y(t)} />
          ))}
          {xt.map((t) => (
            <line key={`x${t}`} x1={x(t)} x2={x(t)} y1={M.t} y2={M.t + h} />
          ))}
        </g>
        {relative && range.lo < 0 && range.hi > 0 && (
          <line className="metric-plot-zero" x1={M.l} x2={M.l + w} y1={y(0)} y2={y(0)} />
        )}
        <g className="metric-plot-ticks">
          {yt.map((t) => (
            <text key={`y${t}`} x={M.l - 6} y={y(t)} textAnchor="end" dominantBaseline="middle">
              {formatTick(t)}
            </text>
          ))}
          {xt.map((t) => (
            <text key={`x${t}`} x={x(t)} y={M.t + h + 14} textAnchor="middle">
              {formatTick(t)}
            </text>
          ))}
        </g>
        <text className="metric-plot-label" x={M.l + w / 2} y={size - 8} textAnchor="middle">
          {xLabel}
        </text>
        <text className="metric-plot-label" x={M.l} y={M.t - 10} textAnchor="start">
          {yLabel}
        </text>
        {series.map((s) =>
          s.fixed ? (
            s.level !== null && (
              <line
                key={s.key}
                className="metric-plot-fixed"
                x1={M.l}
                x2={M.l + w}
                y1={y(s.level)}
                y2={y(s.level)}
                stroke={s.color}
              />
            )
          ) : (
            <g key={s.key} className={s.stale ? "metric-plot-curve stale" : "metric-plot-curve"}>
              {/* A point with no value (a held gap, AK#1757 step 6; a
                  reference with no point there) breaks the line: one
                  polyline per run of values, never bridging it. */}
              {segments(s.xs, s.ys).map((seg, n) => (
                <polyline
                  key={n}
                  fill="none"
                  stroke={s.color}
                  points={seg.map(([v, w]) => `${x(v)},${y(w)}`).join(" ")}
                />
              ))}
              {s.xs.map((v, i) =>
                s.ys[i] === null ? null : (
                  <circle key={i} cx={x(v)} cy={y(s.ys[i] as number)} r={2.5} fill={s.color} />
                ),
              )}
            </g>
          ),
        )}
      </svg>
      {errors.length > 0 && (
        <div className="sweep-advisory-overlay zparam-refusal" role="alert">
          {errors[0]}
        </div>
      )}
    </div>
  );
}
