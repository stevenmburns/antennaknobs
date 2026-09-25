// The polar far-field charts' shared drawing (FarFieldChart's one-cut plots
// and the combined Az + El plot, AK#1730). Pulled out of FarFieldChart so the
// two draw the grid, the traces and the cross-reference spoke the same way,
// and so the geometry can be tested without a canvas.
import { plotColors } from "./palette";

/** Where a plot sits on the canvas, and the radial map it uses. */
export type PolarGeom = {
  cx: number;
  cy: number;
  R: number;
  /** Absolute dBi → fraction of R (lib/refine.ts's cutDbiToFrac). */
  dbiToFrac: (db: number) => number;
};

/** Canvas point of a sample at polar parameter t (radians) and `dbi`.
 *
 *  t = 0 is the right-hand rim and t = π/2 the top, counter-clockwise: for
 *  the azimuth cut that is +x then +y; for the elevation cut it is the cut
 *  bearing's horizon then the zenith (the server's elevation parameter). The
 *  canvas's y runs down, so it is negated. */
export function polarPoint(
  g: PolarGeom,
  tRad: number,
  dbi: number,
): { x: number; y: number } {
  const frac = g.dbiToFrac(dbi);
  return {
    x: g.cx + Math.cos(tRad) * frac * g.R,
    y: g.cy - Math.sin(tRad) * frac * g.R,
  };
}

/** The polar parameter of sample i of an n-sample trace: its explicit angle
 *  when adaptive refinement (issue #744) made the cut non-uniform, else the
 *  server's default t = 2π·i/n. */
export function sampleAngleRad(
  i: number,
  n: number,
  anglesDeg: readonly number[] | undefined,
): number {
  return anglesDeg ? (anglesDeg[i % n] * Math.PI) / 180 : (2 * Math.PI * i) / n;
}

/** The labelled dB rings (+6/0/−6/−12/−18) and the two axis lines. */
export function drawDbiRings(
  ctx: CanvasRenderingContext2D,
  g: PolarGeom,
  PC: ReturnType<typeof plotColors>,
): void {
  const { cx, cy, R } = g;
  ctx.strokeStyle = PC.grid;
  ctx.lineWidth = 0.6;
  ctx.fillStyle = PC.labelDim;
  ctx.font = "9px ui-monospace, monospace";
  for (const db of [6, 0, -6, -12, -18]) {
    const f = g.dbiToFrac(db);
    ctx.beginPath();
    ctx.arc(cx, cy, R * f, 0, 2 * Math.PI);
    ctx.stroke();
    ctx.fillText(`${db > 0 ? "+" : ""}${db}`, cx + 2, cy - R * f - 1);
  }
  ctx.beginPath();
  ctx.moveTo(cx - R, cy);
  ctx.lineTo(cx + R, cy);
  ctx.moveTo(cx, cy - R);
  ctx.lineTo(cx, cy + R);
  ctx.stroke();
}

/** A single dashed spoke from the centre to the rim at `angleRad`. */
export function drawSpoke(
  ctx: CanvasRenderingContext2D,
  g: PolarGeom,
  angleRad: number,
  style: string,
): void {
  ctx.beginPath();
  ctx.moveTo(g.cx, g.cy);
  ctx.lineTo(g.cx + Math.cos(angleRad) * g.R, g.cy - Math.sin(angleRad) * g.R);
  ctx.strokeStyle = style;
  ctx.lineWidth = 0.8;
  ctx.setLineDash([3, 3]);
  ctx.stroke();
  ctx.setLineDash([]);
}

export type TraceStyle = {
  /** Null fills without stroking (the combined view's fill pass). */
  stroke: string | null;
  fill?: string;
  width: number;
  dash?: number[];
  anglesDeg?: number[] | undefined;
};

/** Draw one dBi trace around the polar cut, closed. Sample i sits at
 *  `sampleAngleRad` (uniform unless the trace carries explicit angles). A
 *  `fill` fills the closed path before it is stroked. */
export function strokeTrace(
  ctx: CanvasRenderingContext2D,
  g: PolarGeom,
  dbi: readonly number[],
  o: TraceStyle,
): void {
  const n = dbi.length;
  ctx.beginPath();
  for (let pi = 0; pi <= n; pi++) {
    const i = pi % n;
    // `pi` (not `i`) for the uniform case, so the closing sample lands at 2π.
    const t = o.anglesDeg
      ? sampleAngleRad(i, n, o.anglesDeg)
      : sampleAngleRad(pi, n, undefined);
    const p = polarPoint(g, t, dbi[i]);
    if (pi === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  }
  ctx.closePath();
  if (o.fill) {
    ctx.fillStyle = o.fill;
    ctx.fill();
  }
  if (o.stroke === null) return;
  if (o.dash) ctx.setLineDash(o.dash);
  ctx.strokeStyle = o.stroke;
  ctx.lineWidth = o.width;
  ctx.stroke();
  if (o.dash) ctx.setLineDash([]);
}
