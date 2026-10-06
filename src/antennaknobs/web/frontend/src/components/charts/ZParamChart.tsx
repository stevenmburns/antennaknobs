import { useContext, useEffect, useRef, useState } from "react";
import {
  canLogX,
  formatOhm,
  formatParam,
  gapBetween,
  guideLabel,
  type HeldGap,
  isDensity,
  nearestIndex,
  nudgeClear,
  rangeWithRef,
  refPlacement,
  type ParamSweepData,
  RX_AUTO,
  rxDomain,
  type RxAxisChoice,
  rxTicks,
  traceDotRadius,
  xDomain,
  xFraction,
  xTicks,
} from "../../lib/paramSweep";
import { sweepTimeLimitNote } from "../../lib/sweep";
import { formatTick } from "../../lib/sweepAxis";
import { zinfSuffix } from "../../lib/zinf";
import { ZPARAM_PLOT_MARGIN } from "../../lib/zparamLayout";
import { ThemeContext, useIsMobile } from "../hooks";
import { pinZAt } from "../../lib/sweepPins";
import { curvesAttr, type ExtraCurve, NO_CURVES, NO_PINS, type PinCurve, pinsAttr } from "./curves";
import { CHART_FONT, fitChartCanvas, useChartScale } from "./chartScale";
import { cellColor, PIN_DASH, plotColors } from "./palette";

/** A pinned sweep's X on the R/X plot: dotted, where its R is dashed (the
 *  live curves draw R solid and X dashed). */
const PIN_X_DASH = [2, 3];
import { RxRangePopover } from "./RxRangePopover";

// The Z-vs-parameter chart (docs/design/z-vs-param-view.md): the feed R and X
// against the swept parameter — the mesh density (the old convergence sweep)
// or a design knob — drawn the way AC6LA's SimNEC charts are (QRZ 1003328
// #163) and the CLI's `sweep --panels` now is: R in red on the LEFT axis, X in
// blue on the RIGHT, each on its own range (Auto, or the viewer's), circles at
// every point, value boxes at the two ends, a log or linear x.
//
// Two things the CLI chart cannot do: the dashed guide at the knob's CURRENT
// value, with the live solve's R and X on it, which slides as the knob moves
// (the sweep is not re-run: every point overrides that knob, #1755's lesson);
// and a hover readout at the nearest point.
//
// Port 0 only on a multi-feed design (the Smith trail draws every port).

export type RxAxis = "r" | "x";


// The plot's margins (lib/zparamLayout): ZParamStage pins the readout just
// inside them.
const MARGIN = ZPARAM_PLOT_MARGIN;

/** The live marker's radius: full size on every screen and curve count. */
const LIVE_MARKER_R = 4;

export function ZParamChart({
  data,
  param,
  label,
  unit = null,
  total,
  currentValue,
  liveR,
  liveX,
  size,
  running,
  xLog,
  onXLogChange,
  rAxis = RX_AUTO,
  xAxis = RX_AUTO,
  onAxisChange,
  z0 = 50,
  phase = "idle",
  callouts = true,
  onCalloutsChange,
  curves = NO_CURVES,
  pins = NO_PINS,
}: {
  data: ParamSweepData | null;
  /** The parameter the view is set to sweep — the sweep in hand may still
   *  be the previous one's until it re-runs, and draws blank then. */
  param: string;
  label: string;
  unit?: string | null;
  /** Points the sweep in flight asked for, for the "k/N" status. */
  total: number;
  /** The parameter's value on the live solve: the guide's x. */
  currentValue: number | null;
  /** The live solve's R and X, drawn on the guide. */
  liveR: number | null;
  liveX: number | null;
  size: number;
  running: boolean;
  xLog: boolean;
  /** Given, the chart shows the lin/log x toggle (stage only). */
  onXLogChange?: (log: boolean) => void;
  rAxis?: RxAxisChoice;
  xAxis?: RxAxisChoice;
  /** Given, each y axis opens its range popover (stage only). */
  onAxisChange?: (axis: RxAxis, c: RxAxisChoice) => void;
  /** The reference impedance (the design's Zo, or the session's override,
   *  AK#1735): R = Z0 is the R axis's reference line. */
  z0?: number;
  /** The runner's phase, as data-phase: idle / queued (dwelling) / running. */
  phase?: "idle" | "queued" | "running";
  /** Draw the value boxes at the sweep's two ends. Off (a phone starts so:
   *  four boxes on a ~280 px plot covered it, Steve 2026-09-29), the points'
   *  own circles mark the ends and a tap still reads the nearest point. */
  callouts?: boolean;
  /** Given, the chart shows its one "values" toggle for the boxes (stage
   *  only; the state is the session's, never stored). */
  onCalloutsChange?: (on: boolean) => void;
  /** The analysis chart's other curves (AK#1757 step 5 unit 4). With any,
   *  every curve (this chart's own too, in cell 0's colour) draws its R
   *  solid and its X dashed in its own colour, and the ranges take them in;
   *  the end-value boxes and Z∞ stay the chart's own curve's. */
  curves?: readonly ExtraCurve[];
  /** Pinned sweeps (AK#1757 item 1) of this chart's x, placed on its range:
   *  R dashed and X dotted in the pin's colour, no dots, no live marker.
   *  The ranges take them in; the hover reads them at the hovered x. */
  pins?: readonly PinCurve[];
}) {
  const theme = useContext(ThemeContext); // repaint on theme toggle (dep below)
  const { isMobile } = useIsMobile();
  // The chart scale (./chartScale): the canvas draws in a logical square of
  // size / k, so its type, marks and margins grow by k together.
  const k = useChartScale();
  const [zinfOpen, setZinfOpen] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [menu, setMenu] = useState<{ axis: RxAxis; x: number; y: number } | null>(
    null,
  );

  // A sweep of another parameter (the previous choice, still on screen for
  // the moment before the new one starts) draws nothing rather than
  // mislabelled points.
  const d = data && data.param === param ? data : null;
  const xs = d ? d.values : [];
  const rs = d ? d.z_re : [];
  const xsIm = d ? d.z_im : [];
  const n = xs.length;
  // A held sweep's gaps (AK#1757 step 6): points the optimizer did not
  // converge at, drawn as a break in the line and a mark on the x axis,
  // their reasons in the hover, never as a value.
  const gaps: readonly HeldGap[] = d?.gaps ?? [];
  // The other curves of the same parameter, which the ranges fit as well.
  const others = curves.flatMap((c) =>
    c.paramSweep && c.paramSweep.param === param && c.paramSweep.values.length > 0
      ? [{ c, d: c.paramSweep }]
      : [],
  );
  const multi = curves.length > 0;
  // No dots on a phone (lines only), small ones from three curves (a
  // 5-curve family of 2.6 px circles is a smear); the live marker is not one
  // of them and keeps its size.
  const dotR = traceDotRadius(isMobile, 1 + others.length);
  const otherXs = [
    ...others.flatMap((o) => o.d.values),
    ...others.flatMap((o) => (o.d.gaps ?? []).map((g) => g.value)),
    ...gaps.map((g) => g.value),
    ...pins.flatMap((p) => p.xs),
  ];
  const dom = xDomain(
    xs.length > 0 || otherXs.length > 0
      ? [...xs, ...otherXs]
      : currentValue != null
        ? [currentValue]
        : [],
  );
  const logX = xLog && canLogX(dom);
  const fx = xFraction(dom, logX);
  // Auto fits the trace alone (with the live value when it is inside the
  // sweep's span, so the live dots stay on the plot). Not while the sweep is
  // stale: the live dots are then solved on inputs the trace was not (another
  // ground slot, say), and fitting both spans the gap between two physics —
  // on a low inverted-L, refl-coef vs Sommerfeld is 14 ohms, which flattened
  // a converged trace into a line. The stale trace keeps its own range and a
  // live dot past it sits at that edge, as a reference line does.
  const inSpan =
    currentValue != null && n > 1 && currentValue >= dom.lo && currentValue <= dom.hi;
  const liveFits = inSpan && !d?.stale;
  const otherR = [...others.flatMap((o) => o.d.z_re), ...pins.flatMap((p) => p.zRe)];
  const otherX = [...others.flatMap((o) => o.d.z_im), ...pins.flatMap((p) => p.zIm)];
  const rFit = [...(liveFits && liveR != null ? [...rs, liveR] : rs), ...otherR];
  const xFit = [...(liveFits && liveX != null ? [...xsIm, liveX] : xsIm), ...otherX];
  const extrap =
    d && isDensity(d.param)
      ? {
          re: d.z_re_extrap,
          im: d.z_im_extrap,
          p: d.z_extrap_p ?? null,
          status: d.z_extrap_status ?? null,
          reason: d.z_extrap_reason ?? null,
        }
      : null;
  // The Z∞ readout: its value and status word always; the reason clause
  // ("(rough: ...): fed segment ...") is long, so on a phone it moves behind
  // an ⓘ (AK#1757, Steve's phone) and the canvas line stays short.
  const zinfHead =
    extrap && extrap.re != null && extrap.im != null
      ? `Z∞ ≈ ${extrap.re.toFixed(2)} ${extrap.im >= 0 ? "+" : "−"} j${Math.abs(extrap.im).toFixed(2)} Ω${zinfSuffix(extrap.status, extrap.p)}`
      : null;
  const zinfReason = extrap?.reason ?? "";
  const zinfFull = zinfHead != null ? `${zinfHead}${zinfReason}` : null;
  const zinfInfo = isMobile && zinfReason !== "";
  const rDom = rxDomain(rAxis, extrap?.re != null ? [...rFit, extrap.re] : rFit);
  const xDom = rxDomain(xAxis, extrap?.im != null ? [...xFit, extrap.im] : xFit);
  // The two lines that matter (Steve, 2026-09-26): R = Z0 and X = 0. Drawn
  // where they fall, or marked at the edge they are past — never pulled into
  // the auto range.
  const rRef = refPlacement(z0, rDom);
  const xRef = refPlacement(0, xDom);
  const refAttr = (p: typeof rRef) => (p.at === "in" ? p.frac.toFixed(4) : p.at);
  const rT = rxTicks(rDom);
  const xT = rxTicks(xDom);
  const xTk = n > 0 ? xTicks(dom, logX) : [];
  const shownHover = hover != null && hover >= 0 && hover < n ? hover : null;
  // A hover nearer a gap than a drawn point reads the gap's reason.
  const [gapHover, setGapHover] = useState<number | null>(null);
  const shownGap = gapHover != null && gapHover >= 0 && gapHover < gaps.length ? gaps[gapHover] : null;
  // Each pin's Z at the hovered x (AK#1757 item 1), beside the live curve's.
  const hoverPins =
    shownHover != null ? pins.map((p) => ({ p, z: pinZAt(p, xs[shownHover]) })) : [];
  const keyOf = (dd: { lo: number; hi: number }) => `${dd.lo},${dd.hi}`;
  const domKey = `${keyOf(dom)}|${keyOf(rDom)}|${keyOf(xDom)}|${logX}|${z0}|${curvesAttr(curves)}|${pinsAttr(pins)}`;
  // The refusal's own words are a note over the stage (they do not fit a
  // canvas line); the chart says only that there is one.
  // Points landed, gaps included: a held sweep's progress counts both.
  const landed = n + gaps.length;
  const gapWords = gaps.length > 0 ? ` · ${gaps.length} not held` : "";
  const status = d?.error
    ? "sweep refused — see the note"
    : d?.stale
    ? "stale — the design, solver or ground changed; re-run?"
    : d?.partial && d.timeLimitS !== undefined
    ? `${sweepTimeLimitNote({ stopped: "time", time_budget_s: d.timeLimitS })} — ${landed}/${total}${gapWords}`
    : d?.partial
    ? `stopped at ${landed}/${total} — partial${gapWords}`
    : running
    ? `${d?.held ? "holding" : "sweeping"} ${label} ${landed}/${total}…`
    : n === 0 && gaps.length === 0
      ? `no sweep yet — ${label}`
      : gaps.length > 0
        ? `${gaps.length} point${gaps.length === 1 ? "" : "s"} not held — hover the marks`
        : null;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const sz = fitChartCanvas(canvas, ctx, size, k);

    const PC = plotColors();
    const R = (a = 1) => `rgba(${PC.rRgb}, ${a})`;
    const X = (a = 1) => `rgba(${PC.xRgb}, ${a})`;
    ctx.fillStyle = PC.bg;
    ctx.fillRect(0, 0, sz, sz);

    const pw = sz - MARGIN.l - MARGIN.r;
    const ph = sz - MARGIN.t - MARGIN.b;
    const px = (v: number) => MARGIN.l + pw * fx(v);
    const py = (v: number, dd: { lo: number; hi: number }) =>
      MARGIN.t + ph * (1 - (v - dd.lo) / (dd.hi - dd.lo));
    const onPlot = (y: number) => y >= MARGIN.t - 0.5 && y <= MARGIN.t + ph + 0.5;

    ctx.font = CHART_FONT.tick;
    // R grid + left labels, X right labels (its grid would double the lines).
    ctx.lineWidth = 0.6;
    for (const t of rT) {
      const y = py(t, rDom);
      if (!onPlot(y)) continue;
      ctx.strokeStyle = PC.grid;
      ctx.beginPath();
      ctx.moveTo(MARGIN.l, y);
      ctx.lineTo(MARGIN.l + pw, y);
      ctx.stroke();
      ctx.fillStyle = R(0.9);
      const s = formatTick(t);
      ctx.fillText(s, MARGIN.l - 4 - ctx.measureText(s).width, y + 3);
    }
    for (const t of xT) {
      const y = py(t, xDom);
      if (!onPlot(y)) continue;
      ctx.fillStyle = X(0.9);
      ctx.fillText(formatTick(t), MARGIN.l + pw + 4, y + 3);
    }
    // x ticks + labels.
    for (const t of xTk) {
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
    ctx.strokeStyle = PC.axis;
    ctx.lineWidth = 1;
    ctx.strokeRect(MARGIN.l, MARGIN.t, pw, ph);

    // Boxes (and off-scale reference markers) already drawn: a new one that would land on one is nudged
    // vertically clear of it (toward whichever side has room), so the R and
    // X boxes at a shared end never stack when the traces meet there.
    const placed: { x: number; y: number; w: number; h: number }[] = [];

    // The reference lines: R = Z0 in R's colour, X = 0 in X's, heavier and
    // longer-dashed than the grid, labelled at their own axis's side. Past
    // the range: a small arrow marker at that edge, labelled, on its side.
    const refLine = (
      p: typeof rRef,
      label: string,
      c: string,
      side: "left" | "right",
    ) => {
      ctx.font = CHART_FONT.tick;
      const tw = ctx.measureText(label).width;
      const lx = side === "left" ? MARGIN.l + 4 : MARGIN.l + pw - tw - 4;
      if (p.at === "in") {
        const y = MARGIN.t + ph * (1 - p.frac);
        ctx.strokeStyle = c;
        ctx.lineWidth = 1.3;
        ctx.setLineDash([8, 4]);
        ctx.beginPath();
        ctx.moveTo(MARGIN.l, y);
        ctx.lineTo(MARGIN.l + pw, y);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = c;
        ctx.fillText(label, lx, y - 3);
        return;
      }
      const up = p.at === "above";
      const txt = `${label} ${up ? "↑" : "↓"}`;
      const w = ctx.measureText(txt).width;
      const mx = side === "left" ? MARGIN.l + 4 : MARGIN.l + pw - w - 4;
      const my = up ? MARGIN.t + 10 : MARGIN.t + ph - 4;
      ctx.fillStyle = c;
      ctx.fillText(txt, mx, my);
      // The value boxes steer clear of the marker.
      placed.push({ x: mx - 2, y: my - 10, w: w + 4, h: 13 });
    };
    refLine(rRef, `Z0 = ${formatTick(Number(z0.toFixed(2)))} Ω`, R(0.95), "left");
    refLine(xRef, "X = 0", X(0.95), "right");

    // Titles: "R Ω" over the left axis, "X Ω" over the right, the parameter
    // under the plot (with "(log)" when the axis is).
    ctx.font = CHART_FONT.label;
    ctx.fillStyle = R();
    ctx.fillText("R Ω", 4, 12);
    ctx.fillStyle = X();
    const xt = "X Ω";
    ctx.fillText(xt, sz - 4 - ctx.measureText(xt).width, 12);
    ctx.fillStyle = PC.labelBright;
    const xl = `${label}${unit ? ` (${unit})` : ""}${logX ? " · log" : ""}`;
    ctx.fillText(xl, MARGIN.l + (pw - ctx.measureText(xl).width) / 2, sz - 5);

    ctx.save();
    ctx.beginPath();
    ctx.rect(MARGIN.l, MARGIN.t, pw, ph);
    ctx.clip();

    // Z∞ (density): a dotted line on each axis, dimmer when rough (the
    // ladder is not yet asymptotic, so the first order was assumed).
    if (extrap) {
      ctx.setLineDash([2, 3]);
      ctx.lineWidth = 1;
      const a = extrap.status === "rough" ? 0.35 : 0.7;
      for (const [v, dd, c] of [
        [extrap.re, rDom, R(a)],
        [extrap.im, xDom, X(a)],
      ] as const) {
        if (v == null) continue;
        const y = py(v, dd);
        ctx.strokeStyle = c;
        ctx.beginPath();
        ctx.moveTo(MARGIN.l, y);
        ctx.lineTo(MARGIN.l + pw, y);
        ctx.stroke();
      }
      ctx.setLineDash([]);
      // "Z*" at the left end of each line, R's above it and X's below, so
      // the two stay tellable apart when their auto ranges put them level.
      ctx.font = CHART_FONT.tick;
      if (extrap.re != null) {
        ctx.fillStyle = R(0.9);
        ctx.fillText("Z∞ R", MARGIN.l + 4, py(extrap.re, rDom) - 3);
        placed.push({
          x: MARGIN.l + 2,
          y: py(extrap.re, rDom) - 13,
          w: ctx.measureText("Z∞ R").width + 4,
          h: 13,
        });
      }
      if (extrap.im != null) {
        ctx.fillStyle = X(0.9);
        ctx.fillText("Z∞ X", MARGIN.l + 4, py(extrap.im, xDom) + 10);
        placed.push({
          x: MARGIN.l + 2,
          y: py(extrap.im, xDom),
          w: ctx.measureText("Z∞ X").width + 4,
          h: 13,
        });
      }
    }

    // The traces: a polyline and hollow circles at every point.
    const trace = (
      vx: number[],
      ys: number[],
      dd: { lo: number; hi: number },
      c: string,
      dash: number[] = [],
      breaks: readonly HeldGap[] = [],
    ) => {
      if (vx.length === 0) return;
      ctx.strokeStyle = c;
      ctx.lineWidth = 1.4;
      ctx.setLineDash(dash);
      ctx.beginPath();
      vx.forEach((v, i) => {
        const x = px(v);
        const y = py(ys[i], dd);
        // A held sweep breaks at a gap: no line through a point the hold
        // never reached (step 6).
        if (i === 0 || gapBetween(breaks, vx[i - 1], v)) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.setLineDash([]);
      if (dotR <= 0) return; // lines only
      ctx.fillStyle = PC.bg;
      vx.forEach((v, i) => {
        ctx.beginPath();
        ctx.arc(px(v), py(ys[i], dd), dotR, 0, 2 * Math.PI);
        ctx.fill();
        ctx.stroke();
      });
    };
    // A stale knob sweep (its inputs changed, and it waits to be asked):
    // the old trace, dimmed.
    const dim = d?.stale ? 0.35 : 1;
    // A gap's mark: an × on the x axis at its x, in its curve's colour.
    const gapMarks = (gs: readonly HeldGap[], c: string) => {
      ctx.strokeStyle = c;
      ctx.lineWidth = 1.4;
      ctx.setLineDash([]);
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
    };
    if (multi) {
      // One colour per curve (the legend's), R solid and X dashed.
      const own = cellColor(0, dim);
      trace(xs, rs, rDom, own, [], gaps);
      trace(xs, xsIm, xDom, own, [5, 3], gaps);
      gapMarks(gaps, own);
      for (const o of others) {
        ctx.globalAlpha = o.c.stale || o.d.stale ? 0.35 : 1;
        trace(o.d.values, o.d.z_re, rDom, o.c.color, [], o.d.gaps ?? []);
        trace(o.d.values, o.d.z_im, xDom, o.c.color, [5, 3], o.d.gaps ?? []);
        gapMarks(o.d.gaps ?? [], o.c.color);
        ctx.globalAlpha = 1;
      }
    } else {
      trace(xs, rs, rDom, R(dim), [], gaps);
      trace(xs, xsIm, xDom, X(dim), [], gaps);
      gapMarks(gaps, PC.labelStrong);
    }

    // The pinned sweeps: R dashed, X dotted, in each pin's colour.
    for (const p of pins) {
      ctx.strokeStyle = p.color;
      ctx.lineWidth = 1.3;
      for (const [ys, dd, dash] of [
        [p.zRe, rDom, PIN_DASH],
        [p.zIm, xDom, PIN_X_DASH],
      ] as const) {
        ctx.setLineDash(dash);
        ctx.beginPath();
        p.xs.forEach((v, i) => {
          const x = px(v);
          const y = py(ys[i], dd);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();
      }
      ctx.setLineDash([]);
    }

    // The current value: a dashed guide, and the live solve's R and X on it.
    if (currentValue != null && currentValue >= dom.lo && currentValue <= dom.hi) {
      const gx = px(currentValue);
      ctx.strokeStyle = PC.spoke;
      ctx.lineWidth = 0.9;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(gx, MARGIN.t);
      ctx.lineTo(gx, MARGIN.t + ph);
      ctx.stroke();
      ctx.setLineDash([]);
      // Its label, at the guide's top on whichever side has room, clear of
      // the reference markers and Z∞ labels already placed; the value boxes
      // (drawn after) then steer clear of it.
      ctx.font = CHART_FONT.tick;
      ctx.fillStyle = PC.label;
      const gl = guideLabel(d && isDensity(d.param) ? "N" : label, currentValue);
      const gw = ctx.measureText(gl).width;
      const glx = gx + 4 + gw <= MARGIN.l + pw - 2 ? gx + 4 : gx - 4 - gw;
      const gly = nudgeClear(
        MARGIN.t + 2,
        { x: glx, w: gw, h: 13 },
        placed,
        MARGIN.t + 2,
        MARGIN.t + ph - 15,
      );
      placed.push({ x: glx - 1, y: gly, w: gw + 2, h: 13 });
      ctx.fillText(gl, glx, gly + 10);
      for (const [v, dd, c] of [
        [liveR, rDom, R()],
        [liveX, xDom, X()],
      ] as const) {
        if (v == null) continue;
        ctx.fillStyle = c;
        ctx.strokeStyle = `rgba(${PC.bgRgb}, 0.9)`;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        const at = refPlacement(v, dd).at;
        if (at === "in") {
          ctx.arc(gx, py(v, dd), LIVE_MARKER_R, 0, 2 * Math.PI);
        } else {
          // Past the range (a stale trace's, which the live value does not
          // widen): a triangle at that edge pointing the way it lies.
          const s = at === "above" ? -1 : 1;
          const ey = at === "above" ? MARGIN.t : MARGIN.t + ph;
          const r = LIVE_MARKER_R + 1;
          ctx.moveTo(gx, ey);
          ctx.lineTo(gx - r, ey - 2 * s * r);
          ctx.lineTo(gx + r, ey - 2 * s * r);
          ctx.closePath();
        }
        ctx.fill();
        ctx.stroke();
      }
    }

    // Hover: a hairline at the nearest point.
    if (shownHover != null) {
      const hx = px(xs[shownHover]);
      ctx.strokeStyle = PC.labelBright;
      ctx.lineWidth = 0.6;
      ctx.beginPath();
      ctx.moveTo(hx, MARGIN.t);
      ctx.lineTo(hx, MARGIN.t + ph);
      ctx.stroke();
    }
    ctx.restore();

    // A value box: the parameter and one component, in that component's
    // colour, beside its point and kept inside the plot.
    const box = (lines: string[], ax: number, ay: number, c: string, left: boolean) => {
      ctx.font = CHART_FONT.tick;
      const w = Math.max(...lines.map((l) => ctx.measureText(l).width)) + 8;
      const h = 12 * lines.length + 4;
      let bx = left ? ax - w - 8 : ax + 8;
      bx = Math.max(MARGIN.l + 2, Math.min(MARGIN.l + pw - w - 2, bx));
      const top = MARGIN.t + 2;
      const bottom = MARGIN.t + ph - h - 2;
      const by = nudgeClear(
        Math.max(top, Math.min(bottom, ay - h / 2)),
        { x: bx, w, h },
        placed,
        top,
        bottom,
      );
      placed.push({ x: bx, y: by, w, h });
      ctx.fillStyle = `rgba(${PC.bgRgb}, 0.9)`;
      ctx.fillRect(bx, by, w, h);
      ctx.strokeStyle = c;
      ctx.lineWidth = 0.8;
      ctx.strokeRect(bx, by, w, h);
      ctx.fillStyle = c;
      lines.forEach((l, i) => ctx.fillText(l, bx + 4, by + 12 + 12 * i));
    };
    const name = d && isDensity(d.param) ? "N" : label;
    if (callouts && n >= 2 && shownHover == null) {
      for (const i of [0, n - 1]) {
        const last = i === n - 1;
        const tag = `${name}=${formatParam(xs[i])}`;
        const yr = py(rs[i], rDom);
        const yx = py(xsIm[i], xDom);
        // Keep the R and X boxes apart when the traces are close.
        const apart = Math.abs(yr - yx) < 30 ? (yr <= yx ? -16 : 16) : 0;
        box([tag, `R ${formatOhm(rs[i])}`], px(xs[i]), yr + apart, R(), last);
        box([tag, `X ${formatOhm(xsIm[i])}`], px(xs[i]), yx - apart, X(), last);
      }
    }
    if (shownGap != null) {
      // A gap's hover: its x and the optimizer's reason, never a value.
      const hx = px(shownGap.value);
      const words = shownGap.reason.length > 60 ? `${shownGap.reason.slice(0, 59)}…` : shownGap.reason;
      box([`${name}=${formatParam(shownGap.value)}: not held`, words], hx, MARGIN.t + 24, PC.labelStrong, hx > MARGIN.l + pw / 2);
    }
    if (shownHover != null) {
      const i = shownHover;
      const lines = [
        `${name}=${formatParam(xs[i])}`,
        `R ${formatOhm(rs[i])} Ω`,
        `X ${formatOhm(xsIm[i])} Ω`,
      ];
      const hx = px(xs[i]);
      const left = hx > MARGIN.l + pw / 2;
      box(lines, hx, MARGIN.t + 24, PC.labelStrong, left);
      // The pins at the same x, one line each in its colour, in a box of
      // their own under the live one's.
      const rows = hoverPins.map(({ p, z }) => ({
        text: z ? `pin R ${formatOhm(z.re)} X ${formatOhm(z.im)}` : "pin —",
        color: p.color,
      }));
      if (rows.length > 0) {
        ctx.font = CHART_FONT.tick;
        const w = Math.max(...rows.map((r) => ctx.measureText(r.text).width)) + 8;
        const h = 12 * rows.length + 4;
        let bx = left ? hx - w - 8 : hx + 8;
        bx = Math.max(MARGIN.l + 2, Math.min(MARGIN.l + pw - w - 2, bx));
        const by = Math.min(MARGIN.t + ph - h - 2, MARGIN.t + 24 + 12 * lines.length + 8);
        ctx.fillStyle = `rgba(${PC.bgRgb}, 0.9)`;
        ctx.fillRect(bx, by, w, h);
        rows.forEach((r, k) => {
          ctx.fillStyle = r.color;
          ctx.fillText(r.text, bx + 4, by + 12 + 12 * k);
        });
      }
    }
    // Z∞ readout, top of the plot (density), with how it was reached.
    // On a phone the line is DOM (below), so its ⓘ can follow the text
    // instead of floating over a painted string (Steve: the ⓘ sat on Z∞).
    if (zinfFull != null && !isMobile) {
      ctx.font = CHART_FONT.readout;
      ctx.fillStyle = PC.labelBright;
      ctx.fillText(zinfFull, MARGIN.l + (pw - ctx.measureText(zinfFull).width) / 2, 12);
    }
    if (status) {
      ctx.font = CHART_FONT.label;
      ctx.fillStyle = PC.label;
      // Bottom-right: the first point's value boxes sit at the left.
      ctx.fillText(status, MARGIN.l + pw - ctx.measureText(status).width - 4, MARGIN.t + ph - 6);
    }
    // xs/rs/xsIm/rT/xT/xTk/fx are pure functions of `data` and the axis
    // choices below; domKey stands in for the domains as a string, so an
    // unchanged range does not redraw.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, param, label, unit, size, k, theme, isMobile, zinfFull, dotR, domKey, currentValue, liveR, liveX, shownHover, shownGap, status, callouts, curves, pins]);

  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (n === 0 && gaps.length === 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    // In the canvas's logical px (size / k, ./chartScale).
    const pw = size / k - MARGIN.l - MARGIN.r;
    const at = ((e.clientX - rect.left) / k - MARGIN.l) / pw;
    if (at < -0.05 || at > 1.05) {
      setHover(null);
      setGapHover(null);
      return;
    }
    const i = nearestIndex(xs, fx, at);
    const g = nearestIndex(gaps.map((x) => x.value), fx, at);
    // The gap wins when it is the nearer of the two.
    const gapNearer =
      g >= 0 && (i < 0 || Math.abs(fx(gaps[g].value) - at) < Math.abs(fx(xs[i]) - at));
    setGapHover(gapNearer ? g : null);
    setHover(!gapNearer && i >= 0 ? i : null);
  };

  const axisTitle = (a: RxAxis) => (a === "r" ? "R range" : "X range");
  const axisChoice = (a: RxAxis) => (a === "r" ? rAxis : xAxis);
  return (
    <div className="sweep-chart zparam-chart" style={{ width: size, height: size }}>
      <canvas
        ref={canvasRef}
        className="zparam"
        data-param={d?.param ?? ""}
        data-points={n}
        data-values={xs.map(formatParam).join(",")}
        data-r={rs.map((v) => v.toFixed(3)).join(",")}
        data-x={xsIm.map((v) => v.toFixed(3)).join(",")}
        data-x-log={logX ? "1" : "0"}
        data-r-lo={rDom.lo.toFixed(4)}
        data-r-hi={rDom.hi.toFixed(4)}
        data-x-lo={xDom.lo.toFixed(4)}
        data-x-hi={xDom.hi.toFixed(4)}
        data-guide={
          currentValue != null && currentValue >= dom.lo && currentValue <= dom.hi
            ? formatParam(currentValue)
            : ""
        }
        data-guide-label={
          currentValue != null && currentValue >= dom.lo && currentValue <= dom.hi
            ? guideLabel(d && isDensity(d.param) ? "N" : label, currentValue)
            : ""
        }
        data-ref-r={refAttr(rRef)}
        data-ref-x={refAttr(xRef)}
        data-z0={z0}
        data-extrap={
          extrap && extrap.re != null && extrap.im != null
            ? `${extrap.re.toFixed(3)},${extrap.im.toFixed(3)}`
            : ""
        }
        data-extrap-status={extrap?.status ?? ""}
        data-extrap-reason={extrap?.reason ?? ""}
        data-extrap-p={extrap?.p != null ? extrap.p.toFixed(3) : ""}
        data-dot-r={dotR}
        data-live-r={LIVE_MARKER_R}
        data-live-at-r={liveR == null ? "" : refAttr(refPlacement(liveR, rDom))}
        data-live-at-x={liveX == null ? "" : refAttr(refPlacement(liveX, xDom))}
        data-zinf-line={isMobile ? "short" : "full"}
        data-hover={shownHover ?? ""}
        data-gaps={gaps.map((g) => `${formatParam(g.value)}:${g.reason}`).join(";")}
        data-gap-hover={shownGap ? shownGap.reason : ""}
        data-held={d?.held ? "1" : "0"}
        data-status={status ?? ""}
        data-error={d?.error ?? ""}
        data-partial={d?.partial ? "1" : "0"}
        data-stale={d?.stale ? "1" : "0"}
        data-phase={phase}
        data-callouts={callouts && n >= 2 ? "1" : "0"}
        data-curves={curvesAttr(curves)}
        data-pins={pinsAttr(pins)}
        data-hover-pins={hoverPins
          .map(({ p, z }) => `${p.id}:${z ? `${z.re.toFixed(3)},${z.im.toFixed(3)}` : ""}`)
          .join(";")}
        onPointerMove={onPointerMove}
        // A tap on a phone reads the nearest point too.
        onPointerDown={onPointerMove}
        onPointerLeave={() => {
          setHover(null);
          setGapHover(null);
        }}
      />
      {isMobile && zinfHead != null && (
        <div className="zinf-line" data-zinf-dom="1">
          <span className="zinf-text">{zinfInfo ? zinfHead : zinfFull}</span>
          {zinfInfo && (
            <button
              type="button"
              className="zinf-info-btn"
              aria-expanded={zinfOpen}
              aria-label={zinfOpen ? "Hide the Z∞ note" : "Show the Z∞ note"}
              onClick={() => setZinfOpen((o) => !o)}
            >
              ⓘ
            </button>
          )}
        </div>
      )}
      {zinfInfo && zinfOpen && (
        <div className="chart-note-pop zinf-pop" role="note" aria-label="Z∞ note">
          {zinfFull}
        </div>
      )}
      {onAxisChange &&
        (["r", "x"] as const).map((a) => (
          <button
            key={a}
            type="button"
            className={`sweep-axis-btn zparam-axis-btn-${a}`}
            style={{ top: MARGIN.t * k, height: size - (MARGIN.t + MARGIN.b) * k }}
            aria-label={axisTitle(a)}
            title={`${axisTitle(a)} (${axisChoice(a).kind === "auto" ? "Auto" : "fixed"})`}
            aria-haspopup="dialog"
            aria-expanded={menu?.axis === a}
            // The X axis is on the right: its popover opens leftward, toward
            // the chart; both are clamped to the viewport (useInViewport).
            onClick={(e) =>
              setMenu({ axis: a, x: a === "x" ? e.clientX - 8 : e.clientX + 8, y: e.clientY - 8 })
            }
          />
        ))}
      {onXLogChange && (
        <button
          type="button"
          className="zparam-xlog-btn"
          aria-pressed={logX}
          disabled={!canLogX(dom)}
          title={
            canLogX(dom)
              ? "Log or linear x axis"
              : "A log axis needs every value above zero"
          }
          onClick={() => onXLogChange(!xLog)}
        >
          {logX ? "log x" : "lin x"}
        </button>
      )}
      {onCalloutsChange && (
        <button
          type="button"
          className="zparam-xlog-btn zparam-callout-btn"
          aria-pressed={callouts}
          aria-label={callouts ? "Hide the end values" : "Show the end values"}
          title="The R and X values boxed at the sweep's two ends"
          onClick={() => onCalloutsChange(!callouts)}
        >
          values
        </button>
      )}
      {onAxisChange && menu && (
        <RxRangePopover
          title={axisTitle(menu.axis)}
          at={menu}
          side={menu.axis === "x" ? "left" : "right"}
          preset={
            menu.axis === "r"
              ? {
                  label: "take in Z0",
                  title: `A range holding the trace and R = Z0 (${z0} Ω)`,
                  choice: rangeWithRef(rs, z0),
                }
              : {
                  label: "take in 0",
                  title: "A range holding the trace and X = 0",
                  choice: rangeWithRef(xsIm, 0),
                }
          }
          choice={axisChoice(menu.axis)}
          drawn={menu.axis === "r" ? rDom : xDom}
          onChoice={(c) => onAxisChange(menu.axis, c)}
          onClose={() => setMenu(null)}
        />
      )}
    </div>
  );
}
