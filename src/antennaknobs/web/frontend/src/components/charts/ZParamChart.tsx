import { useContext, useEffect, useRef, useState } from "react";
import {
  canLogX,
  formatOhm,
  formatParam,
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
  xDomain,
  xFraction,
  xTicks,
} from "../../lib/paramSweep";
import { formatTick } from "../../lib/sweepAxis";
import { ThemeContext } from "../hooks";
import { plotColors } from "./palette";
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


const MARGIN = { l: 46, r: 46, t: 18, b: 30 };

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
}) {
  const theme = useContext(ThemeContext); // repaint on theme toggle (dep below)
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
  const dom = xDomain(xs.length > 0 ? xs : currentValue != null ? [currentValue] : []);
  const logX = xLog && canLogX(dom);
  const fx = xFraction(dom, logX);
  // Auto fits the trace alone (with the live value when it is inside the
  // sweep's span, so the live dots stay on the plot).
  const inSpan =
    currentValue != null && n > 1 && currentValue >= dom.lo && currentValue <= dom.hi;
  const rFit = inSpan && liveR != null ? [...rs, liveR] : rs;
  const xFit = inSpan && liveX != null ? [...xsIm, liveX] : xsIm;
  const extrap = d && isDensity(d.param) ? { re: d.z_re_extrap, im: d.z_im_extrap } : null;
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
  const keyOf = (dd: { lo: number; hi: number }) => `${dd.lo},${dd.hi}`;
  const domKey = `${keyOf(dom)}|${keyOf(rDom)}|${keyOf(xDom)}|${logX}|${z0}`;
  // The refusal's own words are a note over the stage (they do not fit a
  // canvas line); the chart says only that there is one.
  const status = d?.error
    ? "sweep refused — see the note"
    : d?.stale
    ? "stale — the design changed; re-run?"
    : d?.partial
    ? `stopped at ${n}/${total} — partial`
    : running
    ? `sweeping ${label} ${n}/${total}…`
    : n === 0
      ? `no sweep yet — ${label}`
      : null;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.floor(size * dpr);
    canvas.height = Math.floor(size * dpr);
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const PC = plotColors();
    const R = (a = 1) => `rgba(${PC.rRgb}, ${a})`;
    const X = (a = 1) => `rgba(${PC.xRgb}, ${a})`;
    ctx.fillStyle = PC.bg;
    ctx.fillRect(0, 0, size, size);

    const pw = size - MARGIN.l - MARGIN.r;
    const ph = size - MARGIN.t - MARGIN.b;
    const px = (v: number) => MARGIN.l + pw * fx(v);
    const py = (v: number, dd: { lo: number; hi: number }) =>
      MARGIN.t + ph * (1 - (v - dd.lo) / (dd.hi - dd.lo));
    const onPlot = (y: number) => y >= MARGIN.t - 0.5 && y <= MARGIN.t + ph + 0.5;

    ctx.font = "9px ui-monospace, monospace";
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
      ctx.font = "9px ui-monospace, monospace";
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
    ctx.font = "10px ui-monospace, monospace";
    ctx.fillStyle = R();
    ctx.fillText("R Ω", 4, 12);
    ctx.fillStyle = X();
    const xt = "X Ω";
    ctx.fillText(xt, size - 4 - ctx.measureText(xt).width, 12);
    ctx.fillStyle = PC.labelBright;
    const xl = `${label}${unit ? ` (${unit})` : ""}${logX ? " · log" : ""}`;
    ctx.fillText(xl, MARGIN.l + (pw - ctx.measureText(xl).width) / 2, size - 5);

    ctx.save();
    ctx.beginPath();
    ctx.rect(MARGIN.l, MARGIN.t, pw, ph);
    ctx.clip();

    // Richardson Z* (density): a dotted line on each axis.
    if (extrap) {
      ctx.setLineDash([2, 3]);
      ctx.lineWidth = 1;
      for (const [v, dd, c] of [
        [extrap.re, rDom, R(0.7)],
        [extrap.im, xDom, X(0.7)],
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
      ctx.font = "9px ui-monospace, monospace";
      if (extrap.re != null) {
        ctx.fillStyle = R(0.9);
        ctx.fillText("Z* R", MARGIN.l + 4, py(extrap.re, rDom) - 3);
      }
      if (extrap.im != null) {
        ctx.fillStyle = X(0.9);
        ctx.fillText("Z* X", MARGIN.l + 4, py(extrap.im, xDom) + 10);
      }
    }

    // The traces: a polyline and hollow circles at every point.
    const trace = (ys: number[], dd: { lo: number; hi: number }, c: string) => {
      if (n === 0) return;
      ctx.strokeStyle = c;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      xs.forEach((v, i) => {
        const x = px(v);
        const y = py(ys[i], dd);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.fillStyle = PC.bg;
      xs.forEach((v, i) => {
        ctx.beginPath();
        ctx.arc(px(v), py(ys[i], dd), 2.6, 0, 2 * Math.PI);
        ctx.fill();
        ctx.stroke();
      });
    };
    // A stale knob sweep (its inputs changed, and it waits to be asked):
    // the old trace, dimmed.
    const dim = d?.stale ? 0.35 : 1;
    trace(rs, rDom, R(dim));
    trace(xsIm, xDom, X(dim));

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
      for (const [v, dd, c] of [
        [liveR, rDom, R()],
        [liveX, xDom, X()],
      ] as const) {
        if (v == null) continue;
        ctx.fillStyle = c;
        ctx.strokeStyle = `rgba(${PC.bgRgb}, 0.9)`;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(gx, py(v, dd), 4, 0, 2 * Math.PI);
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
      ctx.font = "9px ui-monospace, monospace";
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
    if (n >= 2 && shownHover == null) {
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
    if (shownHover != null) {
      const i = shownHover;
      const lines = [
        `${name}=${formatParam(xs[i])}`,
        `R ${formatOhm(rs[i])} Ω`,
        `X ${formatOhm(xsIm[i])} Ω`,
      ];
      const hx = px(xs[i]);
      box(lines, hx, MARGIN.t + 24, PC.labelStrong, hx > MARGIN.l + pw / 2);
    }
    // Z* readout, top of the plot (density).
    if (extrap && extrap.re != null && extrap.im != null) {
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillStyle = PC.labelBright;
      const sign = extrap.im >= 0 ? "+" : "−";
      const txt = `Z* ≈ ${extrap.re.toFixed(2)} ${sign} j${Math.abs(extrap.im).toFixed(2)} Ω`;
      ctx.fillText(txt, MARGIN.l + (pw - ctx.measureText(txt).width) / 2, 12);
    }
    if (status) {
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillStyle = PC.label;
      // Bottom-right: the first point's value boxes sit at the left.
      ctx.fillText(status, MARGIN.l + pw - ctx.measureText(status).width - 4, MARGIN.t + ph - 6);
    }
    // xs/rs/xsIm/rT/xT/xTk/fx are pure functions of `data` and the axis
    // choices below; domKey stands in for the domains as a string, so an
    // unchanged range does not redraw.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, param, label, unit, size, theme, domKey, currentValue, liveR, liveX, shownHover, status]);

  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (n === 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const pw = size - MARGIN.l - MARGIN.r;
    const at = (e.clientX - rect.left - MARGIN.l) / pw;
    if (at < -0.05 || at > 1.05) {
      setHover(null);
      return;
    }
    const i = nearestIndex(xs, fx, at);
    setHover(i >= 0 ? i : null);
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
        data-ref-r={refAttr(rRef)}
        data-ref-x={refAttr(xRef)}
        data-z0={z0}
        data-extrap={
          extrap && extrap.re != null && extrap.im != null
            ? `${extrap.re.toFixed(3)},${extrap.im.toFixed(3)}`
            : ""
        }
        data-hover={shownHover ?? ""}
        data-status={status ?? ""}
        data-error={d?.error ?? ""}
        data-partial={d?.partial ? "1" : "0"}
        data-stale={d?.stale ? "1" : "0"}
        onPointerMove={onPointerMove}
        // A tap on a phone reads the nearest point too.
        onPointerDown={onPointerMove}
        onPointerLeave={() => setHover(null)}
      />
      {onAxisChange &&
        (["r", "x"] as const).map((a) => (
          <button
            key={a}
            type="button"
            className={`sweep-axis-btn zparam-axis-btn-${a}`}
            style={{ top: MARGIN.t, height: size - MARGIN.t - MARGIN.b }}
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
