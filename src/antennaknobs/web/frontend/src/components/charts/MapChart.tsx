import { useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  bestNode,
  bestNodeLine,
  cellEdges,
  colourValue,
  type ContourQuantity,
  formatG,
  gammaOf,
  landed,
  type MapGrid,
  type MapQuantity,
  type MapRefs,
  mapContours,
  nodeAt,
  quantityLabel,
  swrOf,
  viridisCss,
} from "../../lib/mapGrid";
import { formatOhm, xTicks } from "../../lib/paramSweep";
import { formatTick } from "../../lib/sweepAxis";
import { ThemeContext } from "../hooks";
import { CHART_FONT, useChartScale } from "./chartScale";
import { plotColors, STALE_TRACE_ALPHA } from "./palette";

// The two-knob map (docs/design/sweep-framework-map.md, unit 2): |Γ| on z0
// over a grid of two knobs, drawn as `antennaknobs analyze` draws it
// (`analysis_run._map_figure`): one cell per node centred on it ("nearest"
// shading, so a cell is a solve and never an interpolation), viridis_r on a
// fixed 0..1 scale, the `Ref` lines as contours (lib/mapGrid.ts, the CLI's
// rule and contourpy's vertices), and the grid's least-|Γ| node. A node not
// solved yet is the chart's background, so a partial map reads as partial.
//
// What the CLI's picture cannot do: the live marker at the knobs' current
// values (filled with the live solve's own colour, an arrow at the edge when
// they are off the grid), and a hover (a tap on a phone) that reads the
// nearest node, with no interpolation.

export const MAP_MARGIN = { l: 50, r: 58, t: 12, b: 34 };
const MARGIN = MAP_MARGIN;
const BAR_W = 10;
const MARKER_R = 6;
// The CLI's R contour colours (tab:orange, tab:red, magenta, tab:pink).
const R_COLOURS = ["#ff7f0e", "#d62728", "#ff00ff", "#e377c2"];
const R_DASH = [6, 4];
const SWR_DASH = [2, 3];
// The readout's line and the legend's (one per contour and the best node's)
// sit under the plot, inside the chart's square: the stage sizes the chart,
// and anything past `size` would be cut off.
const FOOT_LINE_PX = 15;

/** The plot's height in CSS px: the square less the readout and legend
 *  lines, never under 60 % of it. */
export function mapPlotHeight(size: number, contours: number): number {
  return Math.max(Math.round(size * 0.6), size - FOOT_LINE_PX * (contours + 2) - 8);
}

/** How a contour is stroked: X solid in the foreground, R dashed in the
 *  CLI's cycling colours, the SWR threshold dotted white, as the CLI. */
export function contourStyle(
  quantity: ContourQuantity,
  rIndex: number,
  fg: string,
): { color: string; dash: number[] } {
  if (quantity === "X") return { color: fg, dash: [] };
  if (quantity === "SWR") return { color: "#ffffff", dash: SWR_DASH };
  return { color: R_COLOURS[rIndex % R_COLOURS.length], dash: R_DASH };
}

/** The knobs' live point: where the marker is, and the live solve's Z for
 *  its fill (null while that solve is in flight). */
export type MapLive = { x: number; y: number; re: number | null; im: number | null };

/** Where the marker sits against the grid: "in", or the side it is off. */
export type MarkerPlace = "in" | "left" | "right" | "below" | "above";

type Axis = {
  lo: number;
  hi: number;
  log: boolean;
  /** Data value → fraction of the plot (0 at lo). */
  f: (v: number) => number;
  /** Fraction → data value. */
  inv: (t: number) => number;
};

function axisOf(values: readonly number[], log: boolean): { axis: Axis; edges: number[] } {
  const canLog = log && values.length > 0 && values.every((v) => v > 0);
  const edges = canLog
    ? cellEdges(values.map(Math.log)).map(Math.exp)
    : cellEdges(values);
  const lo = edges.length ? Math.min(edges[0], edges[edges.length - 1]) : 0;
  const hi = edges.length ? Math.max(edges[0], edges[edges.length - 1]) : 1;
  const a = canLog ? Math.log(lo) : lo;
  const b = canLog ? Math.log(hi) : hi;
  const span = b - a || 1;
  const axis: Axis = canLog
    ? { lo, hi, log: true, f: (v) => (Math.log(v) - a) / span, inv: (t) => Math.exp(a + t * span) }
    : { lo, hi, log: false, f: (v) => (v - a) / span, inv: (t) => a + t * span };
  return { axis, edges };
}

export function MapChart({
  grid,
  xLabel,
  yLabel,
  xLog = false,
  yLog = false,
  z0,
  refs,
  quantity,
  live,
  size,
  status = null,
  stale = false,
  footer,
}: {
  grid: MapGrid;
  /** The axes' knob names, as the CLI labels them. */
  xLabel: string;
  yLabel: string;
  xLog?: boolean;
  yLog?: boolean;
  /** The reference impedance: |Γ| is on it, and R = z0 is the default R
   *  contour. A change re-colours the map; nothing re-solves. */
  z0: number;
  refs: MapRefs;
  quantity: MapQuantity;
  live: MapLive | null;
  size: number;
  /** One line over the plot: the run's progress, a stop, staleness. */
  status?: string | null;
  /** Drawn for inputs that have since changed: the map dims, the marker
   *  does not. */
  stale?: boolean;
  /** The chart's own controls (the runner's unit), under the legend. */
  footer?: ReactNode;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const theme = useContext(ThemeContext);
  const k = useChartScale();
  const [hover, setHover] = useState<{ i: number; j: number } | null>(null);

  const { axis: ax, edges: xe } = useMemo(() => axisOf(grid.xs, xLog), [grid.xs, xLog]);
  const { axis: ay, edges: ye } = useMemo(() => axisOf(grid.ys, yLog), [grid.ys, yLog]);
  const contours = useMemo(() => mapContours(grid, refs, z0), [grid, refs, z0]);
  const best = useMemo(() => bestNode(grid, z0), [grid, z0]);
  const nLanded = useMemo(() => landed(grid), [grid]);
  const total = grid.xs.length * grid.ys.length;
  const bestLine = best ? bestNodeLine(best, grid, xLabel, yLabel) : null;
  const plotH = mapPlotHeight(size, contours.length);

  const liveGamma =
    live && live.re !== null && live.im !== null ? gammaOf(live.re, live.im, z0) : null;
  const place: MarkerPlace | null = !live
    ? null
    : live.x < ax.lo
      ? "left"
      : live.x > ax.hi
        ? "right"
        : live.y < ay.lo
          ? "below"
          : live.y > ay.hi
            ? "above"
            : "in";

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    // A plot narrower than tall would waste the square: it is `size` wide
    // and `plotH` high, drawn in logical px (÷ the chart scale k).
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.floor(size * dpr);
    canvas.height = Math.floor(plotH * dpr);
    ctx.setTransform(dpr * k, 0, 0, dpr * k, 0, 0);
    const sz = size / k;
    const szH = plotH / k;
    const PC = plotColors();
    const pw = sz - MARGIN.l - MARGIN.r;
    const ph = szH - MARGIN.t - MARGIN.b;
    const px = (v: number) => MARGIN.l + ax.f(v) * pw;
    const py = (v: number) => MARGIN.t + (1 - ay.f(v)) * ph;
    ctx.fillStyle = PC.bg;
    ctx.fillRect(0, 0, sz, szH);
    ctx.strokeStyle = PC.axis;
    ctx.strokeRect(MARGIN.l, MARGIN.t, pw, ph);

    // The cells, one per solved node.
    for (let j = 0; j < grid.ys.length; j++) {
      for (let i = 0; i < grid.xs.length; i++) {
        const re = grid.re[j][i];
        const im = grid.im[j][i];
        if (re === null || im === null) continue;
        const g = gammaOf(re, im, z0);
        ctx.fillStyle = viridisCss(colourValue(g, quantity));
        const x0 = px(xe[i]);
        const x1 = px(xe[i + 1]);
        const y0 = py(ye[j]);
        const y1 = py(ye[j + 1]);
        // A hair of overlap so neighbouring cells leave no seam.
        ctx.fillRect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0) + 0.5, Math.abs(y1 - y0) + 0.5);
      }
    }
    // Stale: the cells fade under a veil of the background (one veil, so the
    // cells' hairline overlaps cannot show through as a grid), and the
    // contours with them.
    if (stale) {
      ctx.fillStyle = `rgba(${PC.bgRgb}, ${1 - STALE_TRACE_ALPHA})`;
      ctx.fillRect(MARGIN.l, MARGIN.t, pw, ph);
      ctx.globalAlpha = STALE_TRACE_ALPHA;
    }
    // The contours, as the legend names them.
    let r = 0;
    for (const c of contours) {
      const st = contourStyle(c.quantity, c.quantity === "R" ? r++ : 0, PC.labelStrong);
      if (!c.reached) continue;
      ctx.strokeStyle = st.color;
      ctx.setLineDash(st.dash);
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      for (const [x1, y1, x2, y2] of c.segments) {
        ctx.moveTo(px(x1), py(y1));
        ctx.lineTo(px(x2), py(y2));
      }
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.lineWidth = 1;
    ctx.globalAlpha = 1;

    // The best node so far: a small ring.
    if (best) {
      ctx.strokeStyle = PC.labelStrong;
      ctx.beginPath();
      ctx.arc(px(grid.xs[best.i]), py(grid.ys[best.j]), 3, 0, 2 * Math.PI);
      ctx.stroke();
    }

    // Ticks and titles.
    ctx.font = CHART_FONT.tick;
    ctx.fillStyle = PC.label;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    // Ticks over the nodes' span: a cell edge half a step past the last
    // node is no value anyone set.
    const span = (v: readonly number[]) => ({ lo: Math.min(...v), hi: Math.max(...v) });
    for (const t of xTicks(span(grid.xs), ax.log)) {
      ctx.fillText(formatTick(t), px(t), MARGIN.t + ph + 3);
    }
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (const t of xTicks(span(grid.ys), ay.log)) {
      ctx.fillText(formatTick(t), MARGIN.l - 4, py(t));
    }
    ctx.font = CHART_FONT.label;
    ctx.fillStyle = PC.labelBright;
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    ctx.fillText(xLabel, MARGIN.l + pw / 2, szH - 2);
    ctx.save();
    ctx.translate(11, MARGIN.t + ph / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textBaseline = "middle";
    ctx.fillText(yLabel, 0, 0);
    ctx.restore();

    // The colour bar: 0 (a match) at the bottom, 1 at the top.
    const bx = MARGIN.l + pw + 10;
    for (let s = 0; s < ph; s++) {
      ctx.fillStyle = viridisCss(1 - s / ph);
      ctx.fillRect(bx, MARGIN.t + s, BAR_W, 1.5);
    }
    ctx.strokeStyle = PC.axis;
    ctx.strokeRect(bx, MARGIN.t, BAR_W, ph);
    ctx.font = CHART_FONT.tick;
    ctx.fillStyle = PC.label;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    for (const t of [0, 0.25, 0.5, 0.75, 1]) {
      ctx.fillText(String(t), bx + BAR_W + 3, MARGIN.t + (1 - t) * ph);
    }
    ctx.save();
    ctx.translate(sz - 6, MARGIN.t + ph / 2);
    ctx.rotate(Math.PI / 2);
    ctx.textAlign = "center";
    ctx.font = CHART_FONT.label;
    ctx.fillStyle = PC.labelBright;
    ctx.fillText(quantityLabel(quantity, z0), 0, 0);
    ctx.restore();

    // The live marker: a ring filled with the live solve's colour, or an
    // arrow on the edge it is off.
    if (live && place) {
      const fill = liveGamma === null ? PC.bg : viridisCss(colourValue(liveGamma, quantity));
      ctx.lineWidth = 2;
      ctx.strokeStyle = PC.labelStrong;
      ctx.fillStyle = fill;
      if (place === "in") {
        ctx.beginPath();
        ctx.arc(px(live.x), py(live.y), MARKER_R, 0, 2 * Math.PI);
        ctx.fill();
        ctx.stroke();
      } else {
        const cx = Math.min(MARGIN.l + pw, Math.max(MARGIN.l, px(Math.min(ax.hi, Math.max(ax.lo, live.x)))));
        const cy = Math.min(MARGIN.t + ph, Math.max(MARGIN.t, py(Math.min(ay.hi, Math.max(ay.lo, live.y)))));
        const d = MARKER_R + 2;
        const tri: [number, number][] =
          place === "left"
            ? [[cx, cy - d], [cx, cy + d], [cx - d, cy]]
            : place === "right"
              ? [[cx, cy - d], [cx, cy + d], [cx + d, cy]]
              : place === "below"
                ? [[cx - d, cy], [cx + d, cy], [cx, cy + d]]
                : [[cx - d, cy], [cx + d, cy], [cx, cy - d]];
        ctx.beginPath();
        ctx.moveTo(...tri[0]);
        ctx.lineTo(...tri[1]);
        ctx.lineTo(...tri[2]);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }
      ctx.lineWidth = 1;
    }

    if (status) {
      ctx.font = CHART_FONT.label;
      ctx.fillStyle = PC.labelStrong;
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(status, MARGIN.l + 4, MARGIN.t + 4);
    }
  }, [grid, ax, ay, xe, ye, contours, best, quantity, z0, live, liveGamma, place, size, plotH, k, theme, status, stale, xLabel, yLabel]);

  const toData = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const lx = (e.clientX - rect.left) / k;
    const ly = (e.clientY - rect.top) / k;
    const pw = size / k - MARGIN.l - MARGIN.r;
    const ph = plotH / k - MARGIN.t - MARGIN.b;
    return { x: ax.inv((lx - MARGIN.l) / pw), y: ay.inv(1 - (ly - MARGIN.t) / ph) };
  };
  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const { x, y } = toData(e);
    setHover(nodeAt(grid.xs, grid.ys, x, y));
  };

  const hv = hover && hover.i < grid.xs.length && hover.j < grid.ys.length ? hover : null;
  const hre = hv ? grid.re[hv.j][hv.i] : null;
  const him = hv ? grid.im[hv.j][hv.i] : null;
  const readout = hv
    ? `${xLabel} ${formatG(grid.xs[hv.i], 6)}, ${yLabel} ${formatG(grid.ys[hv.j], 6)}: ` +
      (hre === null || him === null
        ? "not solved yet"
        : (() => {
            const g = gammaOf(hre, him, z0);
            const s = swrOf(g);
            return (
              `R ${formatOhm(hre)} Ω, X ${formatOhm(him)} Ω, ` +
              `SWR ${Number.isFinite(s) ? s.toFixed(2) : "∞"}, |Γ| ${g.toFixed(3)}`
            );
          })())
    : null;

  let rIdx = 0;
  const legend = contours.map((c) => ({
    c,
    style: contourStyle(c.quantity, c.quantity === "R" ? rIdx++ : 0, "currentColor"),
  }));
  return (
    <div className="map-chart" style={{ width: size, height: size }}>
      <div className="map-chart-plot" style={{ width: size, height: plotH }}>
        <canvas
          ref={canvasRef}
          className="map"
          style={{ width: size, height: plotH }}
          data-nodes={nLanded}
          data-total={total}
          data-quantity={quantity}
          data-z0={z0}
          data-contours={contours.map((c) => c.label).join("|")}
          data-segments={contours.map((c) => c.segments.length).join(",")}
          data-best={best ? `${best.i},${best.j}` : ""}
          data-marker={place ?? ""}
          data-live={live ? `${live.x},${live.y}` : ""}
          data-marker-fill={liveGamma === null ? "" : liveGamma.toFixed(4)}
          data-hover={hv ? `${hv.i},${hv.j}` : ""}
          data-stale={stale ? "1" : "0"}
          data-status={status ?? ""}
          onPointerMove={onPointerMove}
          // A tap on a phone reads the nearest node too.
          onPointerDown={onPointerMove}
          onPointerLeave={() => setHover(null)}
        />
      </div>
      <div className="map-readout" role="status" aria-label="Map node">
        {readout ?? ""}
      </div>
      <ul className="map-legend" aria-label="Map legend">
        {legend.map(({ c, style }) => (
          <li key={`${c.quantity}:${c.level}`} data-reached={c.reached ? "1" : "0"}>
            <svg width="22" height="8" aria-hidden="true">
              <line
                x1="1"
                y1="4"
                x2="21"
                y2="4"
                stroke={c.quantity === "SWR" ? "#888" : style.color}
                strokeWidth="2"
                strokeDasharray={style.dash.join(" ")}
              />
            </svg>{" "}
            {c.label}
          </li>
        ))}
        <li className="map-best">
          {bestLine ?? "no node solved yet"}
          {nLanded < total ? ` (${nLanded}/${total} nodes)` : ""}
        </li>
      </ul>
      {footer}
    </div>
  );
}
