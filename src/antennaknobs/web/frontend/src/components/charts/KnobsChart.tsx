import { useContext, useEffect, useRef, useState } from "react";
import {
  formatParam,
  gapBetween,
  type HeldGap,
  nearestIndex,
  type ParamSweepData,
  RX_AUTO,
  rxDomain,
  rxTicks,
  traceDotRadius,
  xDomain,
  xFraction,
  xTicks,
} from "../../lib/paramSweep";
import { formatTick } from "../../lib/sweepAxis";
import { ZPARAM_PLOT_MARGIN } from "../../lib/zparamLayout";
import { ThemeContext, useIsMobile } from "../hooks";
import { CHART_FONT, fitChartCanvas, useChartScale } from "./chartScale";
import { cellColor, plotColors } from "./palette";
import type { ExtraCurve } from "./curves";

// The Knobs view (AK#1757, sweep-framework step 6): a held sweep's knobs
// against the swept one, the values the optimizer re-solved them to at each
// point. The first held knob on the LEFT axis, a second (match_z0 holds two)
// on the RIGHT, each on its own Auto range, as the R/X chart does R and X.
// One curve draws the first knob in R's colour and the second in X's; a
// multi-curve chart draws each curve in its legend colour, the first knob
// solid and the second dashed. A gap (a point the hold did not reach) breaks
// the line and is marked on the x axis, its reason in the hover, never drawn
// as a value.

const MARGIN = ZPARAM_PLOT_MARGIN;

type Curve = { d: ParamSweepData; color: string | null; stale: boolean };

export function KnobsChart({
  data,
  param,
  label,
  unit = null,
  knobs,
  total,
  size,
  running,
  xLog,
  curves = [],
}: {
  data: ParamSweepData | null;
  param: string;
  label: string;
  unit?: string | null;
  /** The held knobs, in the hold's order (one or two). */
  knobs: readonly string[];
  total: number;
  size: number;
  running: boolean;
  xLog: boolean;
  curves?: readonly ExtraCurve[];
}) {
  const theme = useContext(ThemeContext);
  const { isMobile } = useIsMobile();
  const k = useChartScale();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hover, setHover] = useState<number | null>(null);

  const own = data && data.param === param && data.held ? data : null;
  const all: Curve[] = [
    ...(own ? [{ d: own, color: null, stale: !!own.stale }] : []),
    ...curves.flatMap((c) =>
      c.paramSweep && c.paramSweep.param === param && c.paramSweep.held
        ? [{ d: c.paramSweep, color: c.color, stale: !!(c.stale || c.paramSweep.stale) }]
        : [],
    ),
  ];
  const multi = curves.length > 0;
  const k1 = knobs[0] ?? null;
  const k2 = knobs[1] ?? null;
  const xs = own ? own.values : [];
  const gaps: readonly HeldGap[] = own?.gaps ?? [];
  const n = xs.length;
  const allX = all.flatMap((c) => [...c.d.values, ...(c.d.gaps ?? []).map((g) => g.value)]);
  const dom = xDomain(allX);
  const fx = xFraction(dom, xLog);
  const vals = (name: string | null) =>
    name ? all.flatMap((c) => (c.d.held?.[name] ?? []).filter(Number.isFinite)) : [];
  const d1 = rxDomain(RX_AUTO, vals(k1));
  const d2 = rxDomain(RX_AUTO, vals(k2));
  const dotR = traceDotRadius(isMobile, Math.max(1, all.length));
  const shown = hover != null && hover >= 0 && hover < n ? hover : null;
  const landed = n + gaps.length;
  const status = running
    ? `holding ${label} ${landed}/${total}…`
    : all.length === 0
      ? `no held sweep yet — ${label}`
      : gaps.length > 0
        ? `${gaps.length} point${gaps.length === 1 ? "" : "s"} not held`
        : null;
  const key = `${dom.lo},${dom.hi}|${d1.lo},${d1.hi}|${d2.lo},${d2.hi}|${xLog}`;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const sz = fitChartCanvas(canvas, ctx, size, k);
    const PC = plotColors();
    const C1 = (a = 1) => `rgba(${PC.rRgb}, ${a})`;
    const C2 = (a = 1) => `rgba(${PC.xRgb}, ${a})`;
    ctx.fillStyle = PC.bg;
    ctx.fillRect(0, 0, sz, sz);
    const pw = sz - MARGIN.l - MARGIN.r;
    const ph = sz - MARGIN.t - MARGIN.b;
    const px = (v: number) => MARGIN.l + pw * fx(v);
    const py = (v: number, dd: { lo: number; hi: number }) =>
      MARGIN.t + ph * (1 - (v - dd.lo) / (dd.hi - dd.lo));

    ctx.font = CHART_FONT.tick;
    ctx.lineWidth = 0.6;
    for (const t of rxTicks(d1)) {
      const y = py(t, d1);
      if (y < MARGIN.t - 0.5 || y > MARGIN.t + ph + 0.5) continue;
      ctx.strokeStyle = PC.grid;
      ctx.beginPath();
      ctx.moveTo(MARGIN.l, y);
      ctx.lineTo(MARGIN.l + pw, y);
      ctx.stroke();
      ctx.fillStyle = C1(0.9);
      const s = formatTick(t);
      ctx.fillText(s, MARGIN.l - 4 - ctx.measureText(s).width, y + 3);
    }
    if (k2) {
      for (const t of rxTicks(d2)) {
        const y = py(t, d2);
        if (y < MARGIN.t - 0.5 || y > MARGIN.t + ph + 0.5) continue;
        ctx.fillStyle = C2(0.9);
        ctx.fillText(formatTick(t), MARGIN.l + pw + 4, y + 3);
      }
    }
    if (allX.length > 0) {
      for (const t of xTicks(dom, xLog)) {
        const x = px(t);
        ctx.strokeStyle = PC.axisFaint;
        ctx.beginPath();
        ctx.moveTo(x, MARGIN.t);
        ctx.lineTo(x, MARGIN.t + ph);
        ctx.stroke();
        ctx.fillStyle = PC.label;
        const s = formatParam(t);
        ctx.fillText(s, x - ctx.measureText(s).width / 2, MARGIN.t + ph + 11);
      }
    }
    ctx.strokeStyle = PC.axis;
    ctx.lineWidth = 1;
    ctx.strokeRect(MARGIN.l, MARGIN.t, pw, ph);
    ctx.font = CHART_FONT.label;
    if (k1) {
      ctx.fillStyle = C1();
      ctx.fillText(k1, 4, 12);
    }
    if (k2) {
      ctx.fillStyle = C2();
      ctx.fillText(k2, sz - 4 - ctx.measureText(k2).width, 12);
    }
    ctx.fillStyle = PC.labelBright;
    const xl = `${label}${unit ? ` (${unit})` : ""}${xLog ? " · log" : ""}`;
    ctx.fillText(xl, MARGIN.l + (pw - ctx.measureText(xl).width) / 2, sz - 5);

    ctx.save();
    ctx.beginPath();
    ctx.rect(MARGIN.l, MARGIN.t, pw, ph);
    ctx.clip();
    const trace = (
      vx: readonly number[],
      ys: readonly number[],
      dd: { lo: number; hi: number },
      c: string,
      dash: number[],
      breaks: readonly HeldGap[],
    ) => {
      ctx.strokeStyle = c;
      ctx.lineWidth = 1.4;
      ctx.setLineDash(dash);
      ctx.beginPath();
      let open = false;
      vx.forEach((v, i) => {
        const y = ys[i];
        if (!Number.isFinite(y)) {
          open = false;
          return;
        }
        if (!open || gapBetween(breaks, vx[i - 1], v)) ctx.moveTo(px(v), py(y, dd));
        else ctx.lineTo(px(v), py(y, dd));
        open = true;
      });
      ctx.stroke();
      ctx.setLineDash([]);
      if (dotR <= 0) return;
      ctx.fillStyle = PC.bg;
      vx.forEach((v, i) => {
        if (!Number.isFinite(ys[i])) return;
        ctx.beginPath();
        ctx.arc(px(v), py(ys[i], dd), dotR, 0, 2 * Math.PI);
        ctx.fill();
        ctx.stroke();
      });
    };
    all.forEach((c, i) => {
      ctx.globalAlpha = c.stale ? 0.35 : 1;
      const col = multi ? (c.color ?? cellColor(i)) : null;
      const gs = c.d.gaps ?? [];
      if (k1) trace(c.d.values, c.d.held?.[k1] ?? [], d1, col ?? C1(), [], gs);
      if (k2) trace(c.d.values, c.d.held?.[k2] ?? [], d2, col ?? C2(), [5, 3], gs);
      // Each gap: an × on the x axis, in its curve's colour.
      ctx.strokeStyle = col ?? PC.labelStrong;
      ctx.lineWidth = 1.4;
      for (const g of gs) {
        const gx = px(g.value);
        const gy = MARGIN.t + ph - 6;
        ctx.beginPath();
        ctx.moveTo(gx - 4, gy - 4);
        ctx.lineTo(gx + 4, gy + 4);
        ctx.moveTo(gx + 4, gy - 4);
        ctx.lineTo(gx - 4, gy + 4);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    });
    if (shown != null && own) {
      const hx = px(xs[shown]);
      ctx.strokeStyle = PC.labelBright;
      ctx.lineWidth = 0.6;
      ctx.beginPath();
      ctx.moveTo(hx, MARGIN.t);
      ctx.lineTo(hx, MARGIN.t + ph);
      ctx.stroke();
    }
    ctx.restore();
    if (shown != null && own) {
      const lines = [
        `${label}=${formatParam(xs[shown])}`,
        ...knobs.map((nm) => `${nm} ${formatParam(own.held?.[nm]?.[shown] ?? Number.NaN)}`),
      ];
      ctx.font = CHART_FONT.tick;
      const w = Math.max(...lines.map((l) => ctx.measureText(l).width)) + 8;
      const h = 12 * lines.length + 4;
      const hx = px(xs[shown]);
      let bx = hx > MARGIN.l + pw / 2 ? hx - w - 8 : hx + 8;
      bx = Math.max(MARGIN.l + 2, Math.min(MARGIN.l + pw - w - 2, bx));
      ctx.fillStyle = `rgba(${PC.bgRgb}, 0.9)`;
      ctx.fillRect(bx, MARGIN.t + 18, w, h);
      ctx.fillStyle = PC.labelStrong;
      lines.forEach((l, i) => ctx.fillText(l, bx + 4, MARGIN.t + 30 + 12 * i));
    }
    if (status) {
      ctx.font = CHART_FONT.label;
      ctx.fillStyle = PC.label;
      ctx.fillText(status, MARGIN.l + pw - ctx.measureText(status).width - 4, MARGIN.t + ph - 14);
    }
    // all / xs / the domains are functions of `data`, `curves` and the knob
    // names; `key` stands in for the domains.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, curves, knobs, param, label, unit, size, k, theme, isMobile, key, shown, status, dotR, multi]);

  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (n === 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const pw = size / k - MARGIN.l - MARGIN.r;
    const at = ((e.clientX - rect.left) / k - MARGIN.l) / pw;
    if (at < -0.05 || at > 1.05) {
      setHover(null);
      return;
    }
    const i = nearestIndex(xs, fx, at);
    setHover(i >= 0 ? i : null);
  };

  const fmt = (v: number) => (Number.isFinite(v) ? v.toPrecision(6) : "");
  return (
    <div className="sweep-chart zparam-chart knobs-chart" style={{ width: size, height: size }}>
      <canvas
        ref={canvasRef}
        className="knobs"
        data-param={own?.param ?? ""}
        data-knobs={knobs.join(",")}
        data-points={n}
        data-curves={all.length}
        data-values={xs.map(formatParam).join(",")}
        data-k1={k1 && own ? (own.held?.[k1] ?? []).map(fmt).join(",") : ""}
        data-k2={k2 && own ? (own.held?.[k2] ?? []).map(fmt).join(",") : ""}
        data-gaps={gaps.map((g) => `${formatParam(g.value)}:${g.reason}`).join(";")}
        data-status={status ?? ""}
        data-hover={shown ?? ""}
        onPointerMove={onPointerMove}
        onPointerDown={onPointerMove}
        onPointerLeave={() => setHover(null)}
      />
    </div>
  );
}
