import { type PointerEvent, useState } from "react";
import type { MetricSpec } from "../../lib/analyses";
import { metricRange, type MetricSeries, metricSpan } from "../../lib/metricPlot";
import { formatParam, guideLabel } from "../../lib/paramSweep";
import { axisTicks, formatTick } from "../../lib/sweepAxis";

// The analysis chart's Metric view (AK#1828, `an.MetricPlot`): a metric
// against the swept knob, one curve per cell, each read off its knob sweep's
// own solves (lib/metricPlot.ts). Relative to a named cell, every curve is
// that difference and the reference is the zero line; a fixed reference is
// drawn flat across the others' span. SVG, so a test reads its curves off
// the data attributes rather than the pixels.
//
// The current knob value and the pointer are the R/X chart's (ZParamChart,
// AK#1867): a dashed guide at the live value, labelled as there, and a
// hairline that follows the pointer while it moves or drags across the
// plot, snapped to the nearest swept x, with every curve's value there in
// its colour.

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

/** The swept x values every non-fixed curve has, ascending, once each. */
function sweptXs(series: readonly MetricSeries[]): number[] {
  return [...new Set(series.flatMap((s) => (s.fixed ? [] : s.xs)))].sort((a, b) => a - b);
}

/** A curve's value at `x`: a fixed reference's level, else its point
 *  there (null: none). */
function valueAt(s: MetricSeries, x: number): number | null {
  if (s.fixed) return s.level;
  const i = s.xs.indexOf(x);
  return i >= 0 ? (s.ys[i] ?? null) : null;
}

const formatValue = (v: number | null) => (v === null ? "—" : v.toFixed(2).replace("-", "−"));

export function MetricPlotChart({
  metric,
  series,
  xLabel,
  name,
  currentValue,
  size,
  running,
}: {
  metric: MetricSpec;
  series: readonly MetricSeries[];
  xLabel: string;
  /** The swept knob's short name, for the guide's and the readout's label. */
  name: string;
  /** The knob's live value: the dashed guide, when inside the swept span. */
  currentValue: number | null;
  size: number;
  running: boolean;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const relative = metric.relativeTo !== null;
  const yLabel = relative
    ? `${metric.name} vs ${metric.relativeTo} (${metric.relativeUnit})`
    : `${metric.name} (${metric.unit})`;
  const span = metricSpan(series);
  const range = metricRange(series);
  const w = size - M.l - M.r;
  const h = size - M.t - M.b;
  const errors = [...new Set(series.map((s) => s.error).filter((e): e is string => !!e))];
  const xsAll = sweptXs(series);
  const shownHover = hover !== null && xsAll.includes(hover) ? hover : null;
  const unit = relative ? metric.relativeUnit : metric.unit;
  const guide =
    span && currentValue !== null && currentValue >= span.lo && currentValue <= span.hi ? currentValue : null;
  const attrs = {
    "data-metric": metric.name,
    "data-relative": metric.relativeTo ?? "",
    "data-series": JSON.stringify(
      series.map((s) => (s.fixed ? { label: s.label, level: s.level } : { label: s.label, xs: s.xs, ys: s.ys })),
    ),
    "data-guide": guide === null ? "" : formatParam(guide),
    "data-guide-label": guide === null ? "" : guideLabel(name, guide),
    "data-hover": shownHover === null ? "" : formatParam(shownHover),
    "data-hover-values":
      shownHover === null ? "" : series.map((s) => formatValue(valueAt(s, shownHover))).join(";"),
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
  // The y range is padded (metricRange): its floor is no value of its own.
  const yt = axisTicks(range, 5, false);
  // The pointer's x, in the svg's own px (it may be drawn scaled), snapped
  // to the nearest swept x; off the plot's sides, none.
  const onPointerMove = (e: PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = (e.clientX - rect.left) * (rect.width > 0 ? size / rect.width : 1);
    if (xsAll.length === 0 || !Number.isFinite(px) || px < M.l - 8 || px > M.l + w + 8) {
      setHover(null);
      return;
    }
    let best = xsAll[0];
    for (const v of xsAll) if (Math.abs(x(v) - px) < Math.abs(x(best) - px)) best = v;
    setHover(best);
  };
  const readout =
    shownHover === null
      ? null
      : [
          { text: `${name} = ${formatParam(shownHover)}`, color: null },
          ...series.map((s) => ({ text: `${formatValue(valueAt(s, shownHover))} ${unit}`, color: s.color })),
        ];
  const boxW = readout ? Math.max(...readout.map((r) => r.text.length)) * 6.2 + 10 : 0;
  const boxH = readout ? readout.length * 13 + 6 : 0;
  const hx = shownHover === null ? 0 : x(shownHover);
  // The box on the side of the hairline with room, kept inside the plot.
  const boxX =
    shownHover === null
      ? 0
      : Math.max(M.l + 2, Math.min(M.l + w - boxW - 2, hx > M.l + w / 2 ? hx - boxW - 8 : hx + 8));
  return (
    <div className="metric-plot" style={{ width: size, height: size }} {...attrs}>
      <svg
        width={size}
        height={size}
        role="img"
        aria-label={`${yLabel} against ${xLabel}`}
        onPointerMove={onPointerMove}
        // A tap on a phone reads the nearest point too, and a drag follows.
        onPointerDown={onPointerMove}
        onPointerLeave={() => setHover(null)}
      >
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
        {guide !== null && (
          <g className="metric-plot-guide">
            <line x1={x(guide)} x2={x(guide)} y1={M.t} y2={M.t + h} />
            <text
              x={x(guide) > M.l + w / 2 ? x(guide) - 4 : x(guide) + 4}
              y={M.t + 11}
              textAnchor={x(guide) > M.l + w / 2 ? "end" : "start"}
            >
              {guideLabel(name, guide)}
            </text>
          </g>
        )}
        {readout && (
          <g className="metric-plot-hover">
            <line x1={hx} x2={hx} y1={M.t} y2={M.t + h} />
            <rect x={boxX} y={M.t + 20} width={boxW} height={boxH} />
            {readout.map((r, i) => (
              <text key={i} x={boxX + 5} y={M.t + 20 + 14 + 13 * i} {...(r.color ? { fill: r.color } : {})}>
                {r.text}
              </text>
            ))}
          </g>
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
