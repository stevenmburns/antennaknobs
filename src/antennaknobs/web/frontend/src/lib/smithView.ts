// The Smith chart's own zoom and pan (see SmithChart.tsx). Pure math, kept
// out of the component so the invariants — the point under the cursor stays
// put, the zoom clamps, the grid refines with the zoom — are testable without
// a canvas.
//
// The view composes on top of the chart's fit framing the same way the
// antenna canvas's camera does: zoom = 1, pan = 0 IS the unzoomed chart, and
// a Γ-plane point lands at
//
//   x = cx + panX + zoom · gRe · R
//   y = cy + panY − zoom · gIm · R
//
// with (cx, cy) the canvas centre and R the unit circle's radius at fit.

export type SmithView = { zoom: number; panX: number; panY: number };

export const SMITH_ZOOM_MIN = 1;
/** 50× puts about 4 Ω of a 50 Ω chart's centre across the view: past that
 *  the solver's own noise is what you would be magnifying. */
export const SMITH_ZOOM_MAX = 50;

export const FIT_VIEW: SmithView = { zoom: 1, panX: 0, panY: 0 };

export function isZoomed(v: SmithView): boolean {
  return v.zoom > 1.001;
}

export function gammaToScreen(
  v: SmithView,
  gRe: number,
  gIm: number,
  cx: number,
  cy: number,
  R: number,
): { x: number; y: number } {
  return {
    x: cx + v.panX + v.zoom * gRe * R,
    y: cy + v.panY - v.zoom * gIm * R,
  };
}

export function screenToGamma(
  v: SmithView,
  x: number,
  y: number,
  cx: number,
  cy: number,
  R: number,
): { gRe: number; gIm: number } {
  return {
    gRe: (x - cx - v.panX) / (v.zoom * R),
    gIm: -(y - cy - v.panY) / (v.zoom * R),
  };
}

/** Keep the view's centre on the chart: the Γ point at the canvas centre may
 *  not leave the unit disc, so a drag cannot lose the chart off-screen. At
 *  zoom 1 the pan snaps to 0 — all the way out is exactly the fit view. */
export function clampView(v: SmithView, R: number): SmithView {
  const zoom = Math.min(SMITH_ZOOM_MAX, Math.max(SMITH_ZOOM_MIN, v.zoom));
  if (zoom <= SMITH_ZOOM_MIN) return { ...FIT_VIEW };
  let { panX, panY } = v;
  const lim = zoom * R;
  const d = Math.hypot(panX, panY);
  if (d > lim) {
    panX *= lim / d;
    panY *= lim / d;
  }
  return { zoom, panX, panY };
}

/** Zoom by `factor` about the canvas point (ax, ay), which stays fixed: the Γ
 *  point under the cursor before the wheel detent is under it after. The
 *  anchor formula is the antenna canvas's (CurrentCanvas applyZoom). */
export function zoomAbout(
  v: SmithView,
  factor: number,
  ax: number,
  ay: number,
  cx: number,
  cy: number,
  R: number,
): SmithView {
  const zoom = Math.min(SMITH_ZOOM_MAX, Math.max(SMITH_ZOOM_MIN, v.zoom * factor));
  const f = zoom / v.zoom;
  return clampView(
    {
      zoom,
      panX: ax - cx - (ax - cx - v.panX) * f,
      panY: ay - cy - (ay - cy - v.panY) * f,
    },
    R,
  );
}

export function panBy(v: SmithView, dx: number, dy: number, R: number): SmithView {
  return clampView({ zoom: v.zoom, panX: v.panX + dx, panY: v.panY + dy }, R);
}

// ---- grid ---------------------------------------------------------------

/** One constant-R circle or constant-X arc pair, in normalized units (Z/Z0),
 *  with the label to print on it when the chart is zoomed. */
export type SmithGridLine = { n: number; label?: string };

export type SmithGrid = {
  r: SmithGridLine[];
  x: SmithGridLine[];
  /** The fine grid's step in ohms, or null for the classic unzoomed grid. */
  stepOhms: number | null;
};

/** The unzoomed chart's grid, unchanged from before zoom existed. */
const CLASSIC = [0.2, 0.5, 1, 2, 5];
/** Below this zoom the classic grid stays: a 1.2× nudge is not a reading. */
const FINE_GRID_FROM = 1.5;
/** The fine grid runs to 4·Z0; past it the lines crowd the rim, and these
 *  coarse ones carry the outer chart. */
const FINE_SPAN = 4;
const COARSE = [5, 10, 20];

/** Largest 1/2/5 × 10^k not above `v`. */
export function niceFloor(v: number): number {
  const p = 10 ** Math.floor(Math.log10(v));
  const m = v / p;
  return (m >= 5 ? 5 : m >= 2 ? 2 : 1) * p;
}

const fmt = (ohms: number): string => String(Number(ohms.toPrecision(6)));

/** The grid for a zoom level. Zoomed in, R and X step in round ohms — about
 *  Z0/zoom, so a 50 Ω chart reads in 5 Ω steps at 10× and 1 Ω steps at 50×,
 *  which is a handful of labelled circles across the view wherever it is
 *  near the match point. */
export function smithGrid(zoom: number, z0: number): SmithGrid {
  if (zoom < FINE_GRID_FROM || !(z0 > 0)) {
    const lines = CLASSIC.map((n) => ({ n }));
    return { r: lines, x: lines, stepOhms: null };
  }
  const step = niceFloor(z0 / zoom);
  const nSteps = Math.floor((FINE_SPAN * z0) / step + 1e-9);
  const fine: SmithGridLine[] = [];
  for (let k = 1; k <= nSteps; k++) {
    const ohms = k * step;
    fine.push({ n: ohms / z0, label: fmt(ohms) });
  }
  const coarse = COARSE.filter((n) => n > FINE_SPAN).map((n) => ({
    n,
    label: fmt(n * z0),
  }));
  const lines = [...fine, ...coarse];
  return { r: lines, x: lines, stepOhms: step };
}
