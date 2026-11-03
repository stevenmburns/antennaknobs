// The polar far-field charts' shared drawing (FarFieldChart's one-cut plots
// and the combined Az + El plot, AK#1730). Pulled out of FarFieldChart so the
// two draw the grid, the traces and the cross-reference spoke the same way,
// and so the geometry can be tested without a canvas.
import { cutRings, type PolarRing } from "../../lib/refine";
import { CHART_FONT } from "./chartScale";
import { plotColors } from "./palette";

/** Where a plot sits on the canvas, and the radial map it uses. */
export type PolarGeom = {
  cx: number;
  cy: number;
  R: number;
  /** Absolute dBi → fraction of R (lib/refine.ts's cutDbiToFrac). */
  dbiToFrac: (db: number) => number;
  /** The labelled rings (lib/refine.ts's cutRings for the scale in use).
   *  Absent: the linear scale's fixed +6/0/−6/−12/−18 dBi. */
  rings?: readonly PolarRing[];
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

/** The labelled rings (`g.rings`, else +6/0/−6/−12/−18 dBi) and the two
 *  axis lines. */
export function drawDbiRings(
  ctx: CanvasRenderingContext2D,
  g: PolarGeom,
  PC: ReturnType<typeof plotColors>,
): void {
  const { cx, cy, R } = g;
  ctx.strokeStyle = PC.grid;
  ctx.lineWidth = 0.6;
  ctx.fillStyle = PC.labelDim;
  ctx.font = CHART_FONT.tick;
  for (const { dbi, label } of g.rings ?? cutRings(0)) {
    const f = g.dbiToFrac(dbi);
    ctx.beginPath();
    ctx.arc(cx, cy, R * f, 0, 2 * Math.PI);
    ctx.stroke();
    if (label) ctx.fillText(label, cx + 2, cy - R * f - 1);
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

/** One sample of the NEC exact-pattern overlay along a cut: polar parameter
 *  t (radians, as `polarPoint`) and the interpolated dBi. */
export type NecCutSample = { t: number; dbi: number };

/** The NEC rp_card pattern sampled along a cut, for FarFieldChart's dashed
 *  overlay. Taken before the radial scale is chosen, so the overlay's peak
 *  counts toward the top: on the ARRL scale the rim is the highest peak
 *  drawn, and an uncounted NEC lobe above the live one would be flattened
 *  onto the rim. Bilinear interpolation off the (θ, φ) grid; null marks a ray
 *  below the horizon, where the line breaks rather than wrapping.
 *
 *  xy: the cone at elevation `azElevDeg`. yz: the vertical great circle
 *  through bearing `elevAzDeg` (t = π/2 the zenith). */
export function necCutSamples(
  pattern: {
    theta_deg: readonly number[];
    phi_deg: readonly number[];
    gain_dbi: readonly (readonly number[])[];
  },
  cut: "xy" | "yz",
  azElevDeg: number,
  elevAzDeg: number,
  nDir = 180,
): (NecCutSample | null)[] {
  const azElevRad = (azElevDeg * Math.PI) / 180;
  const azSinT = Math.cos(azElevRad);
  const azCosT = Math.sin(azElevRad);
  const elevAzRad = (elevAzDeg * Math.PI) / 180;
  const elevAzCos = Math.cos(elevAzRad);
  const elevAzSin = Math.sin(elevAzRad);
  const nt = pattern.theta_deg.length;
  const np_ = pattern.phi_deg.length;
  const dTheta = pattern.theta_deg[1] - pattern.theta_deg[0];
  const dPhi = pattern.phi_deg[1] - pattern.phi_deg[0];
  const clip = (g: number) => (g < -100 ? -100 : g);
  const out: (NecCutSample | null)[] = [];
  for (let pi = 0; pi <= nDir; pi++) {
    const t = (2 * Math.PI * pi) / nDir;
    const ct = Math.cos(t);
    const st = Math.sin(t);
    const rx = cut === "xy" ? azSinT * ct : elevAzCos * ct;
    const ry = cut === "xy" ? azSinT * st : elevAzSin * ct;
    const rz = cut === "xy" ? azCosT : st;
    if (rz < -1e-9) {
      out.push(null);
      continue;
    }
    const thetaDeg = (Math.acos(Math.max(-1, Math.min(1, rz))) * 180) / Math.PI;
    let phiRad = Math.atan2(ry, rx);
    if (phiRad < 0) phiRad += 2 * Math.PI;
    const phiDeg = (phiRad * 180) / Math.PI;
    const tf = Math.max(0, Math.min(nt - 1, thetaDeg / dTheta));
    const pf = Math.max(0, Math.min(np_ - 1, phiDeg / dPhi));
    const t0 = Math.floor(tf),
      t1 = Math.min(nt - 1, t0 + 1);
    const p0 = Math.floor(pf),
      p1 = Math.min(np_ - 1, p0 + 1);
    const ft = tf - t0,
      fp = pf - p0;
    const g00 = clip(pattern.gain_dbi[t0][p0]);
    const g01 = clip(pattern.gain_dbi[t0][p1]);
    const g10 = clip(pattern.gain_dbi[t1][p0]);
    const g11 = clip(pattern.gain_dbi[t1][p1]);
    out.push({
      t,
      dbi:
        g00 * (1 - ft) * (1 - fp) +
        g01 * (1 - ft) * fp +
        g10 * ft * (1 - fp) +
        g11 * ft * fp,
    });
  }
  return out;
}
